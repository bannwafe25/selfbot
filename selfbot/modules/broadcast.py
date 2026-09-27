from __future__ import annotations

import asyncio
import contextlib
import datetime
import html as _html

from pyrogram import enums, filters
from pyrogram.enums import ButtonStyle
from pyrogram.errors import (
    ChannelInvalid,
    ChannelPrivate,
    ChatSendPlainForbidden,
    ChatWriteForbidden,
    FloodPremiumWait,
    FloodWait,
    Forbidden,
    InputUserDeactivated,
    NotAcceptable,
    PeerFlood,
    PeerIdInvalid,
    RPCError,
    SlowmodeWait,
    UserBannedInChannel,
    UserIsBlocked,
)
from pyrogram.types import Message

from selfbot.listener import handler, reply
from selfbot.module import Module

pattern = r"^(gcast|ucast|bc|cancel)(?:\s+([\w\-]+))?$"


class _Task:
    """Task broadcast sederhana (bisa dibatalin pake .cancel <id>)."""

    def __init__(self) -> None:
        self._id = 0
        self._active: set[int] = set()

    def start(self) -> int:
        self._id += 1
        self._active.add(self._id)
        return self._id

    def is_active(self, tid: int) -> bool:
        return tid in self._active

    def end(self, tid: int) -> None:
        self._active.discard(tid)


class Broadcast(Module):
    name = "Broadcast"
    cmds = (
        "gcast (reply)\n"
        "ucast (reply)\n"
        "bc group|private|all (reply)\n"
        "cancel <task_id>"
    )
    desc = {
        "gcast": "Broadcast ke semua grup",
        "ucast": "Broadcast ke chat privat",
        "bc": "Broadcast per tipe: group/private/all",
        "cancel": "Batalkan broadcast yg jalan",
        "e.g.": "reply pesan, lalu ketik: gcast",
    }

    def __init__(self, client) -> None:
        super().__init__(client)
        self.tasks = _Task()
        # blacklist chat id (bisa diisi manual di sini)
        self.blacklist: set[int] = set()

    @staticmethod
    def _text(event: Message) -> str:
        """Ambil teks dari reply (kalo ga reply, pake sisa command)."""
        parts = (event.text or "").split(maxsplit=1)
        return parts[1].strip() if len(parts) > 1 else ""

    @handler(filters.regex(r"^cancel(?:\s+(\d+))?$"), 1)
    async def on_cancel(self, event: Message) -> None:
        parts = (event.text or "").split()
        if len(parts) < 2:
            await self.respond(event, "<b>Cara pakai:</b> <code>cancel <task_id></code>")
            return
        try:
            tid = int(parts[1])
        except ValueError:
            await self.respond(event, "<code>task_id</code> harus angka")
            return
        if not self.tasks.is_active(tid):
            await self.respond(
                event, f"<b>Task</b> <code>#{tid}</code> tidak aktif / sudah selesai"
            )
            return
        self.tasks.end(tid)
        await self.respond(event, f"🛑 Broadcast <code>#{tid}</code> dibatalkan")

    @handler(filters.regex(pattern) & reply, 1)
    async def on_message_out(self, event: Message) -> None:
        cmd = (event.text or "").strip().split()[0].lstrip(".").lower()
        arg = ""
        if cmd == "bc":
            parts = (event.text or "").split(maxsplit=1)
            arg = parts[1].strip().lower() if len(parts) > 1 else "all"
            mode = arg if arg in ("group", "private", "all") else "all"
            if arg not in ("group", "private", "all"):
                await self.respond(
                    event,
                    "<b>Pilihan:</b> <code>bc group</code> / <code>bc private</code> "
                    "/ <code>bc all</code>",
                )
                return
        elif cmd == "gcast":
            mode = "group"
        else:
            mode = "private"

        await self._run(event, mode, event.reply_to_message)

    async def _run(self, event: Message, mode: str, rep: Message) -> None:
        task_id = self.tasks.start()
        msg = await self.respond(
            event,
            f"<code>Menghitung target...</code>\n"
            f"<b>Task</b> <code>#{task_id}</code> — ketik "
            f"<code>cancel {task_id}</code> buat berhenti",
        )

        now = datetime.datetime.now(datetime.UTC)
        targets = []
        async for dialog in event._client.get_dialogs():
            if dialog.chat.id == event._client.me.id:
                continue
            if dialog.chat.id in self.blacklist:
                continue
            t = dialog.chat.type
            if mode == "group" and t in (
                enums.ChatType.GROUP,
                enums.ChatType.SUPERGROUP,
            ):
                targets.append(dialog)
            elif mode == "private" and t in (
                enums.ChatType.PRIVATE,
                enums.ChatType.BOT,
            ):
                targets.append(dialog)
            elif mode == "all":
                targets.append(dialog)

        total = len(targets)
        ok = fail = blocked = 0
        errs: list[str] = []

        for i, dialog in enumerate(targets, 1):
            if not self.tasks.is_active(task_id):
                await msg.edit_text(
                    f"🛑 <b>Broadcast dibatalkan</b>\n"
                    f"  <code>Terkirim</code> : <code>{ok}/{total}</code>"
                )
                return
            try:
                if rep is not None:
                    await rep.copy(dialog.chat.id)
                ok += 1

            except FloodWait as e:
                wait = min(int(e.value), 60)
                await asyncio.sleep(wait)
                try:
                    if rep is not None:
                        await rep.copy(dialog.chat.id)
                    ok += 1
                except RPCError as e2:
                    fail += 1
                    errs.append(f"FloodWait ulang: {dialog.chat.id} ({e2})")

            except (FloodPremiumWait, SlowmodeWait):
                fail += 1
                errs.append(f"Grup timer/slowmode: {dialog.chat.id}")

            except ChatWriteForbidden:
                fail += 1
                errs.append(f"Dimute / ga bisa nulis: {dialog.chat.id}")

            except ChatSendPlainForbidden:
                fail += 1
                errs.append(f"Teks polos dilarang: {dialog.chat.id}")

            except Forbidden:
                fail += 1
                errs.append(f"AntiSpam aktif: {dialog.chat.id}")

            except UserBannedInChannel:
                fail += 1
                errs.append(f"Akun di-ban di channel: {dialog.chat.id}")

            except UserIsBlocked:
                blocked += 1

            except InputUserDeactivated:
                blocked += 1

            except (ChannelPrivate, ChannelInvalid):
                errs.append(f"Channel privat/invalid: {dialog.chat.id}")

            except PeerIdInvalid:
                errs.append(f"Grup invalid: {dialog.chat.id}")

            except NotAcceptable:
                errs.append(f"Grup berbayar (stars): {dialog.chat.id}")

            except PeerFlood:
                fail += 1
                errs.append(f"Akun kena limit (PeerFlood): {dialog.chat.id}")

            except RPCError as e:
                fail += 1
                errs.append(f"{dialog.chat.id}: {e}")

            except Exception as e:
                fail += 1
                errs.append(f"{dialog.chat.id}: {e!r}")

            if i % 10 == 0 or i == total:
                with contextlib.suppress(Exception):
                    await msg.edit_text(
                        f"📢 <b>Broadcast</b>\n"
                        f"  <code>Progres</code> : <code>{i}/{total}</code>\n"
                        f"  <code>Sukses</code> : <code>{ok}</code>\n"
                        f"  <code>Diblokir</code> : <code>{blocked}</code>\n"
                        f"  <code>Gagal </code> : <code>{fail}</code>"
                    )

            await asyncio.sleep(2)

        self.tasks.end(task_id)
        dur = (datetime.datetime.now(datetime.UTC) - now).total_seconds()

        rows = [
            ("Mode", mode),
            ("Total Target", str(total)),
            ("Berhasil", f"✅ {ok}"),
            ("Diblokir", f"🚫 {blocked}"),
            ("Gagal", f"❌ {fail}"),
            ("Total Waktu", f"{dur:.1f}s"),
            ("Task ID", f"#{task_id}"),
        ]

        ok_rich = False
        with contextlib.suppress(Exception):
            ok_rich = await self.send_rich(
                event,
                title="✨ Broadcast Selesai",
                rows=rows,
                note=(
                    "Semua pesan broadcast telah selesai dikirim."
                    + (f"\n{len(errs)} error — ketik bc-error" if errs else "")
                ),
                query_prefix="gcast",
                buttons=(
                    [
                        (
                            "📋 Error",
                            b"bcerr",
                            ButtonStyle.PRIMARY,
                        )
                    ]
                    if errs
                    else None
                ),
            )

        if ok_rich:
            with contextlib.suppress(Exception):
                await msg.delete()
            self._last_errs = errs
            return

        self._last_errs = errs
        teks = (
            f"📢 <b>Broadcast Selesai</b>\n"
            f"  <code>Mode   </code> : <code>{mode}</code>\n"
            f"  <code>Target </code> : <code>{total}</code>\n"
            f"  <code>Sukses </code> : <code>{ok}</code>\n"
            f"  <code>Diblok </code> : <code>{blocked}</code>\n"
            f"  <code>Gagal  </code> : <code>{fail}</code>\n"
            f"  <code>Waktu  </code> : <code>{dur:.1f}s</code>\n"
            f"  <code>Task   </code> : <code>#{task_id}</code>"
        )
        if errs:
            teks += f"\n\n<i>{len(errs)} error — ketik</i> <code>bc-error</code>"
        await msg.edit_text(teks)

    @handler(filters.regex(r"^bc-?error$") & filters.outgoing, 1)
    async def on_error(self, event: Message) -> None:
        errs = getattr(self, "_last_errs", None) or []
        if not errs:
            await self.respond(event, "✅ <b>Tidak ada error</b> di broadcast terakhir")
            return
        body = "\n".join(f"  <code>{_html.escape(e[:120])}</code>" for e in errs[:30])
        more = f"\n\n<i>...dan {len(errs) - 30} lagi</i>" if len(errs) > 30 else ""
        await self.respond(
            event,
            f"⚠️ <b>Error Broadcast ({len(errs)})</b>\n{body}{more}",
        )
