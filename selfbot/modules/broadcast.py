import asyncio
import contextlib
import datetime

from pyrogram import enums, filters
from pyrogram.errors import FloodWait, RPCError
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
    cmds = "gcast {groups|all} (reply pesan)"
    desc = {
        "groups": "Kirim ke semua grup & channel tempat kamu member",
        "all": "Kirim ke semua grup + chat pribadi",
        "e.g.": "reply ke sebuah pesan, lalu ketik: gcast group",
    }

    @handler(filters.regex(r"^gcast\s(group|all)(\s[\s\S]+)?$") & ~reply, 1)
    async def on_message_out(self, event: Message) -> None:
        parts = (event.text or event.caption).split(None, 2)
        mode = parts[1]
        rep = None

        # Teks langsung: gcast group halo semua
        if len(parts) > 2 and parts[2].strip():
            rep_text = parts[2].strip()
            rep = await event.reply_text(rep_text)

        await self._run(event, mode, rep)

    @handler(filters.regex(r"^gcast\s(group|all)$") & reply, 2)
    async def on_message_reply(self, event: Message) -> None:
        await self._run(event, (event.text or event.caption).split()[-1], event.reply_to_message)

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

            if mode == "group":
                if dialog.chat.type in (
                    enums.ChatType.GROUP,
                    enums.ChatType.SUPERGROUP,
                ):
                    targets.append(dialog)
            else:
                if dialog.chat.type in (
                    enums.ChatType.GROUP,
                    enums.ChatType.SUPERGROUP,
                    enums.ChatType.PRIVATE,
                    enums.ChatType.BOT,
                ):
                    targets.append(dialog)

        total = len(targets)
        ok = 0
        fail = 0

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

            except RPCError:
                fail += 1

            if i % 10 == 0 or i == total:
                await msg.edit_text(
                    f"📢 <b>Broadcast</b>\n"
                    f"  <code>Progres</code> : <code>{i}/{total}</code>\n"
                    f"  <code>Sukses</code> : <code>{ok}</code>\n"
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
                [RichBlockTableCell(text="Parameter", is_header=True), RichBlockTableCell(text="Keterangan", is_header=True)],
                [RichBlockTableCell(text="Mode"), RichBlockTableCell(text=mode)],
                [RichBlockTableCell(text="Total Target"), RichBlockTableCell(text=str(total))],
                [RichBlockTableCell(text="Berhasil Terkirim"), RichBlockTableCell(text=f"✅ {ok}")],
                [RichBlockTableCell(text="Gagal Terkirim"), RichBlockTableCell(text=f"❌ {fail}")],
                [RichBlockTableCell(text="Total Waktu"), RichBlockTableCell(text=f"{dur:.2f}s")],
                [RichBlockTableCell(text="Status Akhir"), RichBlockTableCell(text="✅ Selesai")],
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

            # Daftarkan payload ke handler BERSAMA milik ping (group -2)
            self._rich_payload = (rich_raw, close_raw)
            route = None
            try:
                ping_mod = self.client.modules.get("Ping")
                route = getattr(ping_mod, "_rich_route", None) if ping_mod else None
            except Exception:
                route = None
            if route is not None:
                route["gcast"] = self._rich_payload
            handler_ready = route is not None

            res = None
            if handler_ready:
                res = await event._client.get_inline_bot_results(
                    bot.me.id, f"gcast{now.timestamp()}"
                )

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
            f"  <code>Gagal </code> : <code>{fail}</code>\n"
            f"  <code>Waktu </code> : <code>{dur:.1f}s</code>"
        )

