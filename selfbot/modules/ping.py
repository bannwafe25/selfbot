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
    InputRichBlockParagraph,
    InputRichBlockSectionHeading,
    InputRichBlockTable,
    InputRichMessage,
    Message,
    RichBlockTableCell,
    RichTextBold,
    RichTextItalic,
    InputRichBlockButtons,
    RichMessageButton,
    Update,
)
from pyrogram.enums import ButtonStyle

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
            [[("Ping!", "data", b"ping")], [("Close", "data", b"0")]]
        )
        # Rich table via INLINE bot — raw handler dipasang di group -2
        # (dieksekusi sebelum framework handler di group -1)
        if isinstance(event, Message):
            try:
                app_ms = re.sub(r"[^0-9.]", "", str(app)) or app
                blocks = [
                    InputRichBlockTable(
                        [
                            [
                                RichBlockTableCell(text="🚀 Pong!", is_header=True, colspan=2, align="center"),
                            ],
                            [
                                RichBlockTableCell(text="Parameter", is_header=True, align="center"),
                                RichBlockTableCell(text="Keterangan", is_header=True, align="center"),
                            ],
                            [
                                RichBlockTableCell(text="Klien Aktif", align="center"),
                                RichBlockTableCell(text=event._client.me.first_name or "Userbot", align="center"),
                            ],
                            [
                                RichBlockTableCell(text="User ID", align="center"),
                                RichBlockTableCell(text=str(event._client.me.id), align="center"),
                            ],
                            [
                                RichBlockTableCell(text="Kecepatan Respons", align="center"),
                                RichBlockTableCell(text=f"{app_ms} ms", align="center"),
                            ],
                            [
                                RichBlockTableCell(text="Status Jaringan", align="center"),
                                RichBlockTableCell(text="✅ Terhubung Normal", align="center"),
                            ],
                        ],
                        is_bordered=True,
                        is_striped=True,
                        is_compact=False,
                    ),
                    InputRichBlockParagraph(
                        text=RichTextItalic("Pengujian latensi berhasil dilakukan.")
                    ),
                    # Tombol rich: Close saja (Refresh dihapus atas request)
                    InputRichBlockButtons(
                        [
                            RichMessageButton(
                                text=RichTextBold("🗑 Close"),
                                style=ButtonStyle.DANGER,
                                callback_data=b"0",
                            ),
                        ]
                    ),
                ]
                botc = self.client.bot
                from pyrogram.raw import functions as rawfn
                from pyrogram.raw.types import (
                    InputBotInlineMessageRichMessage,
                    InputBotInlineResult,
                )

                rich_raw = await InputRichMessage(blocks=blocks).write(client=bot)
                # Tanpa reply_markup bawah — Close sudah sebagai tombol rich
                close_raw = None

                from pyrogram.handlers import RawUpdateHandler

                # Pastikan handler BERSAMA + route siap (mungkin modul lain
                # seperti alive/sysinfo lebih dulu butuh rich).
                if getattr(self, "_rich_route", None) is None:
                    self._rich_route = {}
                if getattr(self, "_rich_handler", None) is None:
                    from pyrogram.raw.types import UpdateBotInlineQuery as _UBIQ

                    async def _shared_answer(_c, update, users, chats):
                        if not isinstance(update, _UBIQ):
                            return
                        q = str(update.query)
                        for mod, payload in getattr(self, "_rich_route", {}).items():
                            if q.startswith(mod):
                                p_rich, p_close = payload
                                try:
                                    await botc.invoke(
                                        rawfn.messages.SetInlineBotResults(
                                            query_id=update.query_id,
                                            results=[
                                                InputBotInlineResult(
                                                    id=str(update.query_id),
                                                    type="article",
                                                    title="Result",
                                                    send_message=InputBotInlineMessageRichMessage(
                                                        rich_message=p_rich,
                                                    ),
                                                )
                                            ],
                                            cache_time=0,
                                        ),
                                    )
                                except Exception as exc:
                                    self.logger.warning(f"shared rich {mod} failed: {exc!r}")
                                return

                    self._rich_handler = RawUpdateHandler(_shared_answer)
                    disp = botc.dispatcher
                    if -2 not in disp.groups:
                        disp.groups[-2] = []
                        disp.groups = dict(sorted(disp.groups.items()))
                    disp.groups[-2].append(self._rich_handler)
                self._rich_route["ping"] = (rich_raw, None)
                self._rich_mode = True
                try:
                    res = await event._client.get_inline_bot_results(
                        botc.me.id, f"ping{now.timestamp()}"
                    )
                finally:
                    self._rich_mode = False
                if res.results:
                    await asyncio.gather(
                        event.reply_inline_bot_result(
                            res.query_id, res.results[0].id
                        ),
                        event.delete(),
                    )
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
