import asyncio
import datetime
import re

from pyrogram import filters
from pyrogram.types import (
    InlineQuery,
    InlineQueryResultCachedSticker,
    InputTextMessageContent,
    Message,
)

from selfbot import listener
from selfbot.module import Module
from selfbot.utils import fmtsec, fmtstr, ikm

pattern = re.compile(r"pmbl(?:\s(msg|url)\s(.+))?$")


class PMBL(Module):
    name = "PMBL"
    cmds = "pmbl ({key} {value})?"
    desc = {
        "pmbl": "Toggle (Standalone)",
        "key": "(msg|url)",
        "value": "Message or URL",
        "?": "Optional",
        "e.g.": "pmbl msg No PMs!",
    }
    status, msg, url = False, "Sorry, No PMs!", "t.me/resolveUsername"

    async def on_starting(self) -> None:
        row = await self.client.db.fetchrow("SELECT status, msg, url FROM pmbl.meta;")
        if not row:
            await self.client.db.execute(
                "INSERT INTO pmbl.meta (status, msg, url) VALUES ($1, $2, $3);",
                self.status,
                self.msg,
                self.url,
            )
            return

        self.status, self.msg, self.url = row["status"], row["msg"], row["url"]

    @listener.handler(filters.regex(pattern), 1)
    async def on_message_out(self, event: Message) -> None:
        now, (key, value) = (
            datetime.datetime.now(datetime.UTC),
            pattern.match(event.content).groups(),
        )
        if not key:
            self.status = not self.status
            key, value = "status", self.status
        else:
            if key == "msg":
                self.msg = value
            else:
                self.url = value

        await asyncio.gather(
            self.client.db.execute(f"UPDATE pmbl.meta SET {key} = $1;", value),
            event.edit_text(
                fmtstr(
                    "PM Block",
                    {
                        "Status": self.status,
                        "Message": self.msg,
                        "Button URL": self.url,
                    },
                    fmtsec(now),
                )
            ),
        )

    @listener.handler(filters.private & ~listener.fltusr, 2)
    async def on_message_in(self, event: Message) -> None:
        if not self.status:
            return

        _, res = await asyncio.gather(
            event._client.read_chat_history(event.chat.id, event.id),
            event._client.get_inline_bot_results(self.client.bot.me.id, "pmbl"),
        )
        await event.reply_inline_bot_result(res.query_id, res.results[0].id)
        await asyncio.gather(event.from_user.archive(), event.from_user.block())

    @listener.handler(filters.regex(pattern), 3)
    async def on_inline_query(self, event: InlineQuery) -> None:
        await event.answer(
            [
                InlineQueryResultCachedSticker(
                    sticker_file_id=self.client.config["sticker_file_id"],
                    reply_markup=ikm(("Feedback", "url", self.url)),
                    input_message_content=InputTextMessageContent(
                        f"<blockquote><b>{self.msg}</b></blockquote>"
                    ),
                )
            ]
        )
