import asyncio
import contextlib
import datetime
import html
import re

from pyrogram import filters
from pyrogram.enums import ChatType
from pyrogram.types import Message

from selfbot.listener import handler
from selfbot.module import Module

pattern = re.compile(
    r"^\.?(gcast|ucast|addbl|delbl|listbl)(?:\s+([\s\S]+))?$",
    re.IGNORECASE | re.DOTALL,
)

DELAY = 1  # jeda antar chat (detik), anti FloodWait
BL_KEY = "gcast_blacklist"


async def _load_bl(client) -> set[int]:
    """Blacklist grup (persist di MongoDB, diisi via .addbl)."""
    doc = await client.db[BL_KEY].find_one({"_id": "bl"})
    return set(doc["ids"]) if doc else set()


async def _save_bl(client, ids: set[int]) -> None:
    await client.db[BL_KEY].replace_one({"_id": "bl"}, {"ids": list(ids)}, upsert=True)


async def _upd(client, status, text: str) -> None:
    """Edit status — status bisa Message atau int (message_id)."""
    with contextlib.suppress(Exception):
        if hasattr(status, "edit"):
            await status.edit(text)
        else:
            await client.app.edit_message_text(client.app.me.id, status, text)


async def _collect(client, kind: str):
    """Kumpulkan target + skip blacklist. Return (targets, skipped)."""
    bl = await _load_bl(client)
    targets, skipped = [], 0
    async for dialog in client.app.get_dialogs(limit=None):
        chat = dialog.chat
        if not chat:
            continue
        if kind == "gcast":
            # grup & supergroup doang — channel/saved message dilewati
            if chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
                if chat.id in bl:
                    skipped += 1
                    continue
                targets.append(chat.id)
        else:  # ucast: private chat doang, bot dilewati
            if chat.type == ChatType.PRIVATE and not chat.bot:
                targets.append(chat.id)
    return targets, skipped


class Broadcast(Module):
    name = "Broadcast"
    cmds = ".gcast | .ucast | .addbl/.delbl/.listbl"
    desc = {
        "gcast": "Kirim ke semua grup (skip blacklist). Reply media → .gcast -r",
        "ucast": "Kirim ke semua private chat/kontak.",
        "addbl": "Blacklist grup → dilewati .gcast (by id/@user/reply/di grup itu).",
        "delbl": "Hapus grup dari blacklist.",
        "listbl": "Lihat daftar blacklist.",
        "Note": "Delay 1 detik per chat.",
        "e.g.": ".gcast Halo semua! · .ucast yo · .addbl -100123",
    }

    @handler(filters.regex(pattern) & filters.outgoing, 1)
    async def on_message_out(self, event: Message) -> None:
        match = pattern.match(event.text or "")
        if not match:
            return
        cmd = match.group(1).lower()
        arg = (match.group(2) or "").strip()

        # ---------- blacklist ----------
        if cmd in ("addbl", "delbl", "listbl"):
            await self._blacklist(event, cmd, arg)
            return

        # ---------- gcast / ucast ----------
        reply_msg = event.reply_to_message
        use_media = False
        text = arg
        if cmd == "gcast" and (arg in ("-r", "r") or (not arg and reply_msg)):
            if not reply_msg:
                await self.respond(event, "<b>Reply ke pesan dulu buat mode -r.</b>")
                return
            use_media = bool(reply_msg.media)
            text = (reply_msg.caption or reply_msg.text or "") if not use_media else (reply_msg.caption or "")
        elif not arg and not (reply_msg and cmd == "gcast"):
            hint = ".gcast {pesan} / reply → .gcast -r" if cmd == "gcast" else ".ucast {pesan}"
            await self.respond(event, f"<b>Cara pakai:</b> <code>{hint}</code>")
            return

        label = "📢 Gcast" if cmd == "gcast" else "📨 Ucast"
        icon = "📢" if cmd == "gcast" else "📨"
        noun = "grup" if cmd == "gcast" else "private chat"

        status = await self.respond(event, f"<code>🔍 Mengumpulkan {noun}...</code>")
        now = datetime.datetime.now(datetime.UTC)

        targets, skipped = await _collect(self.client, cmd)
        total = len(targets)
        if not total:
            with contextlib.suppress(Exception):
                await status.edit(f"<b>Gagal:</b> gak ada {noun} ditemukan.")
            return

        ok, fail = 0, []
        for i, chat_id in enumerate(targets, 1):
            try:
                if cmd == "gcast" and reply_msg:
                    if use_media:
                        await reply_msg.copy(chat_id)
                    else:
                        await self._resend(chat_id, reply_msg, text)
                else:
                    await self.client.app.send_message(chat_id, text)
                ok += 1
            except Exception as e:
                fail.append(str(e)[:80])
            if i % 5 == 0 or i == total:
                with contextlib.suppress(Exception):
                    await status.edit(
                        f"<b>{label}</b>\n\n"
                        f"Progress: <code>{i}/{total}</code> · ✅ {ok} · ❌ {len(fail)}"
                    )
            if DELAY:
                await asyncio.sleep(DELAY)

        # ---------- kartu rich ----------
        rich_rows = [
            ("Target", f"{total} {noun}"),
            ("Berhasil", f"✅ {ok}"),
            ("Gagal", f"❌ {len(fail)}"),
        ]
        if cmd == "gcast" and skipped:
            rich_rows.insert(0, ("Di-skip (blacklist)", f"🚫 {skipped}"))
        if fail:
            rich_rows.append(("Error (contoh)", fail[0][:60]))

        sum_lines = []
        if cmd == "gcast" and skipped:
            sum_lines.append(f"🚫 Di-skip (blacklist): <b>{skipped}</b>")
        sum_lines.append(f"✅ Berhasil: <b>{ok}</b>")
        sum_lines.append(f"❌ Gagal: <b>{len(fail)}</b>")
        if fail:
            shown = "\n".join(f"<code>{html.escape(f)}</code>" for f in fail[:5])
            sum_lines.append(f"\nDetail:\n{shown}")

        rich_ok = await self.send_rich(
            event,
            f"{icon} {'Gcast' if cmd == 'gcast' else 'Ucast'} Selesai",
            rich_rows,
            note=self.fmtsec(now),
            query_prefix=f"bcast_{cmd}",
        )
        with contextlib.suppress(Exception):
            if hasattr(status, "delete"):
                await status.delete()
            else:
                await self.client.app.delete_messages(
                    self.client.app.me.id, status
                )
        if not rich_ok:
            await self.respond(
                event, f"<b>{label} selesai</b>\n\n" + "\n".join(sum_lines)
            )
            return
        with contextlib.suppress(Exception):
            await event.delete()

    # --------------------------------------------------
    # Blacklist
    # --------------------------------------------------

    async def _blacklist(self, event: Message, cmd: str, arg: str) -> None:
        bl = await _load_bl(self.client)

        if cmd == "listbl":
            if not bl:
                await self.respond(event, "<b>Blacklist kosong.</b>")
                return
            names = []
            for cid in bl:
                with contextlib.suppress(Exception):
                    chat = await self.client.app.get_chat(cid)
                    names.append(f"<code>{cid}</code> — {html.escape(chat.title or '?')}")
            await self.respond(
                event,
                "<b>📋 Blacklist gcast</b>\n\n" + "\n".join(names or ["<i>(chat gak ketemu)</i>"]),
            )
            return

        target = None
        if arg:
            with contextlib.suppress(Exception):
                chat = await self.client.app.get_chat(arg)
                target = chat.id
        elif event.reply_to_message and event.reply_to_message.chat:
            target = event.reply_to_message.chat.id
        elif event.chat and event.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
            target = event.chat.id

        if target is None:
            await self.respond(
                event,
                "<b>Cara pakai:</b> <code>.addbl {id|@user}</code> atau kirim di grup yang mau di-blacklist / reply pesan grupnya.",
            )
            return

        if cmd == "addbl":
            bl.add(target)
            await _save_bl(self.client, bl)
            await self.respond(event, f"<b>🚫 Blacklisted:</b> <code>{target}</code>")
        else:
            bl.discard(target)
            await _save_bl(self.client, bl)
            await self.respond(event, f"<b>✅ Unblacklisted:</b> <code>{target}</code>")

    async def _resend(self, chat_id: int, reply: Message, caption: str) -> None:
        """Kirim ulang media tanpa forward header."""
        path = await reply.download()
        kind = reply.media.value if reply.media else "document"
        fn = getattr(self.client.app, f"send_{kind}", self.client.app.send_document)
        if path:
            await fn(chat_id, path, caption=caption or None)
        else:
            await reply.copy(chat_id)
