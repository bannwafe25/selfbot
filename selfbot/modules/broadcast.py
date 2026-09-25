import asyncio
import contextlib
import datetime

from pyrogram import enums, filters
from pyrogram.errors import FloodWait, InputUserDeactivated, RPCError, UserIsBlocked
from pyrogram.types import (
    InputRichBlockParagraph,
    InputRichBlockTable,
    InputRichBlockButtons,
    RichMessageButton,
    InputRichMessage,
    Message,
    RichBlockTableCell,
    RichTextBold,
    RichTextItalic,
)
from pyrogram.enums import ButtonStyle as _BS

from selfbot.listener import handler, reply
from selfbot.module import Module


class Broadcast(Module):
    name = "Broadcast"
    cmds = "gcast / ucast (reply pesan)"
    desc = {
        "gcast": "Broadcast ke semua grup",
        "ucast": "Broadcast ke chat privat",
        "e.g.": "reply ke sebuah pesan, lalu ketik: gcast",
    }

    @handler(filters.regex(r"^(gcast|ucast)$") & reply, 1)
    async def on_message_out(self, event: Message) -> None:
        mode = (event.text or "").strip()
        await self._run(event, mode, event.reply_to_message)

    async def _run(self, event: Message, mode: str, rep) -> None:
        msg = await self.respond(
            event,
            "<code>Menghitung target...</code>",
        )

        now = datetime.datetime.now(datetime.UTC)
        targets = []

        async for dialog in event._client.get_dialogs():
            # ID user sendiri berada di dialog.chat.id
            if dialog.chat.id == event._client.me.id:
                continue

            if mode == "gcast":
                if dialog.chat.type in (
                    enums.ChatType.GROUP,
                    enums.ChatType.SUPERGROUP,
                ):
                    targets.append(dialog)
            else:
                if dialog.chat.type in (
                    enums.ChatType.PRIVATE,
                    enums.ChatType.BOT,
                ):
                    targets.append(dialog)

        total = len(targets)
        ok = 0
        fail = 0

        blocked = 0
        for i, dialog in enumerate(targets, 1):
            try:
                await rep.copy(dialog.chat.id)
                ok += 1

            except FloodWait as e:
                await asyncio.sleep(e.value)

                try:
                    await rep.copy(dialog.chat.id)
                    ok += 1
                except RPCError:
                    fail += 1

            except (UserIsBlocked, InputUserDeactivated):
                blocked += 1

            except RPCError:
                fail += 1

            if i % 10 == 0 or i == total:
                await msg.edit_text(
                    f"📢 <b>Broadcast</b>\n"
                    f"  <code>Progres</code> : <code>{i}/{total}</code>\n"
                    f"  <code>Sukses</code> : <code>{ok}</code>\n"
                    f"  <code>Diblokir</code> : <code>{blocked}</code>\n"
                    f"  <code>Gagal </code> : <code>{fail}</code>"
                )

            await asyncio.sleep(2)

        dur = (
            datetime.datetime.now(datetime.UTC) - now
        ).total_seconds()

        # Coba rich table via inline bot (pola ping — fallback: HTML biasa)
        try:
            bot = self.client.bot
            from pyrogram.raw import functions as rawfn
            from pyrogram.raw.types import (
                InputBotInlineMessageRichMessage,
                InputBotInlineResult,
                UpdateBotInlineQuery,
            )

            rows = [
                [RichBlockTableCell(text="Parameter", is_header=True, align="center"), RichBlockTableCell(text="Keterangan", is_header=True, align="center")],
                [RichBlockTableCell(text="Mode", align="center"), RichBlockTableCell(text=mode, align="center")],
                [RichBlockTableCell(text="Total Target", align="center"), RichBlockTableCell(text=str(total))],
                [RichBlockTableCell(text="Berhasil", align="center"), RichBlockTableCell(text=f"✅ {ok}", align="center")],
                [RichBlockTableCell(text="Diblokir", align="center"), RichBlockTableCell(text=f"🚫 {blocked}", align="center")],
                [RichBlockTableCell(text="Gagal", align="center"), RichBlockTableCell(text=f"❌ {fail}", align="center")],
                [RichBlockTableCell(text="Total Waktu", align="center"), RichBlockTableCell(text=f"{dur:.2f}s", align="center")],
                [RichBlockTableCell(text="Status Akhir", align="center"), RichBlockTableCell(text="✅ Selesai", align="center")],
            ]
            blocks = [
                InputRichBlockParagraph(
                    text=RichTextBold("✨ Broadcast Selesai")
                ),
                InputRichBlockTable(
                    rows, is_bordered=True, is_striped=True, is_compact=True
                ),
                InputRichBlockParagraph(
                    text=RichTextItalic(
                        "Semua pesan broadcast telah selesai dikirim ke target."
                    )
                ),
            ]
            blocks.append(
                InputRichBlockButtons(
                    [
                        RichMessageButton(
                            text=RichTextBold("🗑 Close"),
                            style=_BS.DANGER,
                            callback_data=b"0",
                        )
                    ]
                )
            )
            rich_raw = await InputRichMessage(blocks=blocks).write(client=bot)
            close_raw = None

            # Payload TERBARU utk handler permanen (bug: output lama terpakai ulang)
            self._rich_payload = (rich_raw, close_raw)

            async def _h(_c, update, users, chats):
                if not isinstance(update, UpdateBotInlineQuery):
                    return
                # Hanya jawab query gcast (jangan query ping/help/call)
                if not str(update.query).startswith("gcast"):
                    return
                with contextlib.suppress(Exception):
                    p_rich, p_close = self._rich_payload
                    await bot.invoke(
                        rawfn.messages.SetInlineBotResults(
                            query_id=update.query_id,
                            results=[
                                InputBotInlineResult(
                                    id=str(update.query_id),
                                    type="article",
                                    title="Broadcast Selesai",
                                    send_message=InputBotInlineMessageRichMessage(
                                        rich_message=p_rich,
                                        reply_markup=p_close,
                                    ),
                                )
                            ],
                            cache_time=0,
                        )
                    )

            # Pasang handler BERSAMA (group -2) — lazy, sama pola ping
            from pyrogram.handlers import RawUpdateHandler

            ping_mod = self.client.modules.get("Ping")
            route = getattr(ping_mod, "_rich_route", None) if ping_mod else None
            if route is None:
                # Buat route + handler sendiri di broadcast
                route = {}
                if ping_mod is not None:
                    ping_mod._rich_route = route

            if getattr(self, "_rich_handler", None) is None:
                from pyrogram.raw.types import UpdateBotInlineQuery as _UBIQ

                async def _shared_answer(_c, update, users, chats):
                    if not isinstance(update, _UBIQ):
                        return
                    q = str(update.query)
                    for mod, payload in route.items():
                        if q.startswith(mod):
                            p_rich, p_close = payload
                            with contextlib.suppress(Exception):
                                await bot.invoke(
                                    rawfn.messages.SetInlineBotResults(
                                        query_id=update.query_id,
                                        results=[
                                            InputBotInlineResult(
                                                id=str(update.query_id),
                                                type="article",
                                                title="Result",
                                                send_message=InputBotInlineMessageRichMessage(
                                                    rich_message=p_rich,
                                                    reply_markup=p_close,
                                                ),
                                            )
                                        ],
                                        cache_time=0,
                                    )
                                )
                            return

                self._rich_handler = RawUpdateHandler(_shared_answer)
                disp = bot.dispatcher
                if -2 not in disp.groups:
                    disp.groups[-2] = []
                    disp.groups = dict(sorted(disp.groups.items()))
                disp.groups[-2].append(self._rich_handler)

            route["gcast"] = (rich_raw, close_raw)

            res = None
            if ping_mod is not None:
                ping_mod._rich_mode = True
            try:
                res = await event._client.get_inline_bot_results(
                    bot.me.id, f"gcast{now.timestamp()}"
                )
            finally:
                if ping_mod is not None:
                    ping_mod._rich_mode = False

            if res.results:
                await asyncio.gather(
                    event.reply_inline_bot_result(res.query_id, res.results[0].id),
                    msg.delete(),
                )
                return
        except Exception as e:
            with contextlib.suppress(Exception):
                self.logger.warning(f"gcast rich failed, fallback html: {e!r}")

        await msg.edit_text(
            f"📢 <b>Broadcast Selesai</b>\n"
            f"  <code>Target</code> : <code>{total}</code>\n"
            f"  <code>Sukses</code> : <code>{ok}</code>\n"
            f"  <code>Diblokir</code> : <code>{blocked}</code>\n"
            f"  <code>Gagal </code> : <code>{fail}</code>\n"
            f"  <code>Waktu </code> : <code>{dur:.1f}s</code>"
        )

