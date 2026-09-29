import asyncio
import contextlib
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

from selfbot.listener import handler, reply
from selfbot.module import Module

pattern = re.compile(r"^p(?:ing)?$")


class Ping(Module):
    name = "Selfbot Latency"
    cmds = "p(ing)?"
    desc = {"?": "Optional", "e.g.": "ping"}

    @handler(filters.regex(pattern) & ~reply, 1)
    async def on_message_out(self, event: Message) -> None:
        await self.execute(event)

    @handler(filters.regex(pattern), 2)
    async def on_inline_query(self, event: InlineQuery) -> None:
        # Query ping dari userbot tidak perlu dijawab framework;
        # raw handler di execute() yang menjawab dengan rich result.
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
        if isinstance(event, Message) and getattr(event, "_from_rich", False):
            return
        if isinstance(event, Message):
            await self.respond(event, "<code>...</code>")
        else:
            await event.edit_message_reply_markup(
                self.ikm(("...", "user", event._client.me.id))
            )

        now, (app, bot) = (
            datetime.datetime.now(datetime.UTC),
            await asyncio.gather(
                self.ping(self.client.app), self.ping(self.client.bot)
            ),
        )
        markup = self.ikm(
            [[("Ping!", "data", b"ping")], [("🗑 Tutup", "data", b"0")]]
        )
        # Rich table via INLINE bot — helper bersama send_rich_blocks (format.py)
        if isinstance(event, Message):
            try:
                import richpyro as rp

                app_ms = re.sub(r"[^0-9.]", "", str(app)) or app
                bot_ms = re.sub(r"[^0-9.]", "", str(bot)) or bot

                trows = [
                    [rp.table_cell(rp.bold("🏓 Pong!"), is_header=True, colspan=2, align="center")],
                    [rp.table_cell(rp.bold("⭐ Owner"), align="center"),
                     rp.table_cell(event._client.me.first_name or "Userbot", align="center")],
                    [rp.table_cell(rp.bold("📱 App"), align="center"),
                     rp.table_cell(f"{app_ms} ms", align="center")],
                    [rp.table_cell(rp.bold("🤖 Bot"), align="center"),
                     rp.table_cell(f"{bot_ms} ms", align="center")],
                    [rp.table_cell(rp.bold("🆔 User ID"), align="center"),
                     rp.table_cell(str(event._client.me.id), align="center")],
                    [rp.table_cell(rp.bold("📶 Status"), align="center"),
                     rp.table_cell("✅ Terhubung Normal", align="center")],
                ]
                blocks = [
                    rp.table(trows, bordered=True, striped=True, compact=False),
                ]

                if await self.send_rich_blocks(event, blocks, query_prefix="ping"):
                    with contextlib.suppress(Exception):
                        await event.delete()
                    return
                # Markup tanpa tombol — kosongkan
                markup = None
            except Exception as e:
                with contextlib.suppress(Exception):
                    self.logger.warning(f"ping rich failed, fallback html: {e!r}")

        await self.respond(
            event,
            self.fmtmsg("Selfbot Latency", {"App": app, "Bot": bot}, self.fmtsec(now)),
            reply_markup=markup,
        )
