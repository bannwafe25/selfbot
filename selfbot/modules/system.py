import asyncio
import datetime
import os
import re
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
        data = await asyncio.to_thread(self.getid)
        if data:
            await self.client.bot.edit_inline_text(
                data[0],
                fmtstr(
                    "Selfbot Restarted",
                    {
                        "Version": __version__,
                        "Modules": len(self.client.modules),
                        "Handlers": len(self.client.handlers),
                        "Listeners": len(self.client.listeners),
                    },
                    fmtsec(datetime.datetime.fromtimestamp(float(data[1]))),
                ),
                reply_markup=ikm(("Close", b"0")),
            )

        self.remote = self.client.config.get(
            "remote", "https://github.com/DeltaUniverse/selfbot"
        )
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

    async def _pip_install_requirements(self) -> None:
        def work():
            try:
                from pip._internal.cli.main import main as pip_main
            except Exception:
                return

            try:
                pip_main(["install", "--upgrade", "pip", "setuptools", "wheel"])
            except Exception:
                pass

            if os.path.exists("requirements.txt"):
                try:
                    pip_main(["install", "-r", "requirements.txt"])
                except Exception:
                    pass
            elif os.path.exists("pyproject.toml"):

                try:
                    pip_main(["install", "."])
                except Exception:
                    pass

        await asyncio.to_thread(work)

    async def _git_fetch_and_detect(self) -> tuple[bool, str | None, str | None]:
        """
        Returns (deps_changed, old_commit_sha, new_commit_sha) without modifying the worktree.
        """

        def work():
            if os.path.isdir(".git"):
                repo = git.Repo(".")
            else:
                repo = git.Repo.init(".")

            origin = next((r for r in repo.remotes if r.name == "origin"), None)
            if origin is None:
                origin = repo.create_remote("origin", self.remote)
            else:

                try:
                    if getattr(origin, "url", None) != self.remote:
                        origin.set_url(self.remote)
                except Exception:
                    origin.set_url(self.remote)

            origin.fetch(prune=True)

            old_commit = (
                repo.head.commit.hexsha
                if not repo.head.is_detached
                else repo.head.commit.hexsha
            )

            target_ref = f"origin/{self.branch}"
            try:
                new_commit_obj = repo.commit(target_ref)
            except Exception:

                return False, old_commit, None

            new_commit = new_commit_obj.hexsha

            dep_files = {"requirements.txt", "pyproject.toml", "poetry.lock"}
            deps_changed = False
            try:
                diffs = repo.commit(old_commit).diff(new_commit)
                for d in diffs:
                    a = (d.a_path or "").lower()
                    b = (d.b_path or "").lower()
                    if a in dep_files or b in dep_files:
                        deps_changed = True
                        break
            except Exception:

                deps_changed = True

            return deps_changed, old_commit, new_commit

        return await asyncio.to_thread(work)

    async def _git_hard_reset_to_remote(self) -> None:
        def work():
            repo = git.Repo(".") if os.path.isdir(".git") else git.Repo.init(".")
            origin = next((r for r in repo.remotes if r.name == "origin"), None)
            if origin is None:
                origin = repo.create_remote("origin", self.remote)
            else:
                try:
                    if getattr(origin, "url", None) != self.remote:
                        origin.set_url(self.remote)
                except Exception:
                    origin.set_url(self.remote)

            origin.fetch(prune=True)
            target_ref = f"origin/{self.branch}"

            if self.branch in repo.heads:
                head = repo.heads[self.branch]
            else:
                head = repo.create_head(self.branch, target_ref)

            try:
                head.set_tracking_branch(repo.remotes.origin.refs[self.branch])
            except Exception:
                pass

            head.checkout()
            repo.git.reset("--hard", target_ref)

        await asyncio.to_thread(work)

    @listener.handler(filters.regex(pattern), 3)
    async def on_inline_result(self, event: ChosenInlineResult) -> None:
        if getattr(self.client, "restart", False) or os.path.exists(self.file):
            return await event.edit_message_text(
                "<code>Restart is Called</code>", reply_markup=ikm(("Close", b"0"))
            )

        setattr(self.client, "restart", True)

        if event.query.endswith("-f"):
            await event.edit_message_text("<code>Checking upstream...</code>")
            deps_changed, old_sha, new_sha = await self._git_fetch_and_detect()

            if new_sha and old_sha and new_sha == old_sha:
                await event.edit_message_text("<code>No updates found.</code>")
            else:
                await event.edit_message_text("<code>Applying update...</code>")
                await self._git_hard_reset_to_remote()

                if deps_changed:
                    await event.edit_message_text(
                        "<code>Dependencies changed. Updating...</code>"
                    )
                    await self._pip_install_requirements()
                else:
                    await event.edit_message_text("<code>No dependency changes.</code>")

        await asyncio.gather(
            event.edit_message_text("<code>Restarting...</code>"),
            asyncio.to_thread(
                self.putid,
                f"{event.inline_message_id}\n{datetime.datetime.now().timestamp()}",
            ),
        )

        try:
            self.client.__event__.set()
        finally:
            os.execv(sys.executable, (sys.executable, "-m", "selfbot"))

    def getid(self) -> tuple[str, float] | None:
        if os.path.exists(self.file):
            with open(self.file) as f:
                try:
                    data = f.readlines()
                    return data[0].strip(), float(data[1])
                finally:
                    os.remove(self.file)

        return None

    def putid(self, text: str) -> None:
        with open(self.file, "w") as f:
            f.write(text)
