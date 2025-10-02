import asyncio
import datetime
import os
import re
import subprocess
import sys

import git
from pyrogram import filters
from pyrogram.types import (
    ChosenInlineResult,
    InlineQuery,
    InlineQueryResultCachedSticker,
    InputTextMessageContent,
    Message,
    ReplyParameters,
)

from selfbot import __version__, listener
from selfbot.module import Module
from selfbot.utils import fmtsec, fmtstr, ikm

pattern = re.compile(r"^r(?:\s-f)?$")


class System(Module):
    name = "System"
    cmds = "r (-f)?"

    desc = {
        "r": "Restart Selfbot",
        "-f": "Fetch Upstream",
        "?": "Optional",
        "e.g.": "r -f",
    }

    file = "r.txt"

    async def on_starting(self) -> None:
        data = await asyncio.to_thread(self.getraw)
        if data:
            inline_id, timestamp = data
            ikb = [("Close", b"0")]
            if len(data) == 4:
                inline_id, timestamp, sha, url = data
                ikb.insert(0, (sha, "url", url))

            await self.client.bot.edit_inline_text(
                inline_id,
                fmtstr(
                    "Selfbot Restarted",
                    {
                        "Version": __version__,
                        "Modules": len(self.client.modules),
                        "Handlers": len(self.client.handlers),
                        "Listeners": len(self.client.listeners),
                    },
                    fmtsec(datetime.datetime.fromtimestamp(float(timestamp))),
                ),
                reply_markup=ikm(ikb),
            )

        self.remote = self.client.config.get(
            "remote", "https://github.com/DeltaUniverse/selfbot"
        ).removesuffix(".git")
        self.branch = self.client.config.get("branch", "staging")

    @listener.handler(filters.regex(pattern), 1)
    async def on_message_out(self, event: Message) -> None:
        res = await event._client.get_inline_bot_results(
            self.client.bot.me.id, event.content
        )
        await asyncio.gather(
            event.reply_inline_bot_result(
                res.query_id,
                res.results[0].id,
                reply_parameters=ReplyParameters(
                    message_id=event.reply_to_message_id or event.id
                ),
            ),
            event.delete(True),
        )

    @listener.handler(filters.regex(pattern), 2)
    async def on_inline_query(self, event: InlineQuery) -> None:
        await event.answer(
            [
                InlineQueryResultCachedSticker(
                    sticker_file_id=self.client.config["sticker_file_id"],
                    reply_markup=ikm((">_", "user_id", event._client.me.id)),
                    input_message_content=InputTextMessageContent("<code>...</code>"),
                )
            ],
            cache_time=0,
        )

    @listener.handler(filters.regex(pattern), 3)
    async def on_inline_result(self, event: ChosenInlineResult) -> None:
        if getattr(self.client, "restart", False) or os.path.exists(self.file):
            return await event.edit_message_text("<code>Restart is Called</code>")

        setattr(self.client, "restart", True)

        fetch = None
        if event.query.endswith("-f"):
            _, fetch = await asyncio.gather(
                event.edit_message_text("<code>Fetch Upstream...</code>"),
                asyncio.to_thread(self.reset),
            )
            await asyncio.gather(
                event.edit_message_text("<code>Update Dependencies...</code>"),
                asyncio.to_thread(
                    subprocess.check_call,
                    [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"],
                ),
            )

        raw = [event.inline_message_id, str(datetime.datetime.now().timestamp())]
        if fetch:
            raw.extend(fetch)

        await asyncio.gather(
            event.edit_message_text("<code>Restarting...</code>"),
            asyncio.to_thread(self.putraw, "\n".join(raw)),
        )
        try:
            self.client.__event__.set()
        finally:
            os.execv(sys.executable, (sys.executable, "-m", "selfbot"))

    def getraw(self) -> tuple:
        if not os.path.exists(self.file):
            return None

        with open(self.file) as f:
            try:
                return f.readlines()
            finally:
                try:
                    os.remove(self.file)
                except OSError:
                    pass

    def putraw(self, text: str) -> None:
        with open(self.file, "w") as f:
            f.write(text)

    def reset(self):
        repo = git.Repo(".") if os.path.isdir(".git") else git.Repo.init(".")

        if "origin" in repo.remotes:
            origin = repo.remotes.origin
            origin.set_url(self.remote)
        else:
            origin = repo.create_remote("origin", self.remote)

        origin.fetch(prune=True)

        remote_ref = f"origin/{self.branch}"
        if self.branch in repo.heads:
            head = repo.heads[self.branch]
        else:
            head = repo.create_head(self.branch, origin.refs[self.branch])

        head.set_tracking_branch(origin.refs[self.branch])
        repo.git.clean("-fd")

        head.checkout()
        repo.git.reset("--hard", remote_ref)

        hexsha = repo.head.commit.hexsha
        return hexsha[:7], f"{self.remote}/commit/{hexsha}"
