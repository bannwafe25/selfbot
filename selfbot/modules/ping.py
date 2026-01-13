import asyncio
import datetime
import re

from pyrogram import Client, filters
from pyrogram.raw.functions import Ping as Latency
from pyrogram.types import (
    CallbackQuery,
    ChosenInlineResult,
    InlineQuery,
    Message,
    Update,
)

from selfbot.listener import fltrep, handler
from selfbot.module import Module

pattern = re.compile(r"^p(?:ing)?$")


class Ping(Module):
    name = "Selfbot Latency"
    cmds = "p(ing)?"
    desc = {"?": "Optional", "e.g.": "ping"}

    @handler(filters.regex(pattern) & ~fltrep, 1)
    async def on_message_out(self, event: Message) -> None:
        await self.execute(event)

    @handler(filters.regex(pattern), 2)
    async def on_inline_query(self, event: InlineQuery) -> None:
        await self.answer(event)

    @handler(filters.regex(pattern), 3)
    async def on_inline_result(self, event: ChosenInlineResult) -> None:
        await self.execute(event)

    @handler(filters.regex(pattern), 4)
    async def on_inline_callback(self, event: CallbackQuery) -> None:
        await self.execute(event)

    async def ping(self, client: Client) -> str:
        now = datetime.datetime.now(datetime.UTC)
        await client.invoke(Latency(ping_id=0))
        return self.fmtsec(now, 1)

    async def execute(self, event: Update) -> None:
        if isinstance(event, Message):
            await self.respond(event, "<code>...</code>")
        else:
            await event.edit_message_reply_markup(
                self.ikm(("...", "user_id", event._client.me.id))
            )

        now, (app, bot) = (
            datetime.datetime.now(datetime.UTC),
            await asyncio.gather(
                self.ping(self.client.app), self.ping(self.client.bot)
            ),
        )
        await self.respond(
            event,
            self.fmtmsg("Selfbot Latency", {"App": app, "Bot": bot}, self.fmtsec(now)),
            reply_markup=self.ikm([[("Ping!", b"ping")], [("Close", b"0")]]),
        )
