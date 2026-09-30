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

pattern = re.compile(r"^\.?gcast(?:\s+([\s\S]+))?$", re.IGNORECASE | re.DOTALL)

# Chat yang dilewati (id chat_id lo sendiri / saved messages ditangani terpisah)
DELAY = 1  # jeda antar chat (detik), anti FloodWait

BL_KEY = "gcast_blacklist"


async def _load_bl(client) -> set[int]:
    """Blacklist grup (persist di MongoDB, diisi via .addbl)."""
    doc = await client.db[BL_KEY].find_one({"_id": "bl"})
    return set(doc["ids"]) if doc else set()


class Gcast(Module):
    name = "Gcast"
    cmds = ".gcast {pesan} | .gcast -r (reply pesan)"
    desc = {
        "pesan": "Teks yang dikirim ke semua grup & channel tempat akun lo ada.",
        "-r": "Reply pesan (media/text) → diteruskan ke semua grup.",
        "Note": "Jeda 3 detik per chat (anti FloodWait). Grup yang gagal dilaporkan.",
        "e.g.": ".gcast Halo semua! / reply pesan → .gcast -r",
    }

    @handler(filters.regex(pattern) & filters.outgoing, 1)
    async def on_message_out(self, event: Message) -> None:
        match = pattern.match(event.text or "")
        if not match:
            return
        arg = (match.group(1) or "").strip()

        # mode reply: teruskan pesan yang direply
        reply = event.reply_to_message
        if arg in ("-r", "r") or (not arg and reply):
            if not reply:
                await self.respond(event, "<b>Reply ke pesan dulu buat mode -r.</b>")
                return
            if reply.media:
                send_media = True
                text = reply.caption or ""
            else:
                send_media = False
                text = reply.text or ""
        elif arg:
            send_media = False
            text = arg
        else:
            await self.respond(
                event,
                "<b>Cara pakai:</b> <code>.gcast {pesan}</code> atau reply pesan → <code>.gcast -r</code>",
            )
            return

        status = await self.respond(event, "<code>🔍 Mengumpulkan chat...</code>")
        now = datetime.datetime.now(datetime.UTC)

        targets = []
        bl = await _load_bl(self.client)
        skipped = 0
        async for dialog in self.client.app.get_dialogs(limit=None):
            chat = dialog.chat
            # grup & supergroup doang — channel/saved message dilewati
            if chat and chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
                if chat.id in bl:
                    skipped += 1
                    continue
                targets.append(chat.id)

        total = len(targets)
        if not total:
            with contextlib.suppress(Exception):
                await status.edit("<b>Gagal:</b> gak ada grup ditemukan.")
            return

        ok, fail = 0, []
        for i, chat_id in enumerate(targets, 1):
            try:
                if send_media and reply:
                    await reply.copy(chat_id)
                elif send_media:
                    await self._resend(chat_id, reply, text)
                else:
                    await self.client.app.send_message(chat_id, text)
                ok += 1
            except Exception as e:
                fail.append(str(e)[:80])
            if i % 5 == 0 or i == total:
                with contextlib.suppress(Exception):
                    await status.edit(
                        f"<b>📢 Gcast</b>\n\n"
                        f"Progress: <code>{i}/{total}</code> · ✅ {ok} · ❌ {len(fail)}"
                    )
            if DELAY:
                await asyncio.sleep(DELAY)

        # === Kartu rich: ringkasan hasil ===
        rich_rows = [
            ("Target", f"{total} grup"),
            ("Berhasil", f"✅ {ok}"),
            ("Gagal", f"❌ {len(fail)}"),
        ]
        if skipped:
            rich_rows.insert(0, ("Di-skip (blacklist)", f"🚫 {skipped}"))
        if fail:
            rich_rows.append(("Error (contoh)", fail[0][:60]))

        sum_lines = []
        if skipped:
            sum_lines.append(f"🚫 Di-skip (blacklist): <b>{skipped}</b>")
        sum_lines.append(f"✅ Berhasil: <b>{ok}</b>")
        sum_lines.append(f"❌ Gagal: <b>{len(fail)}</b>")
        if fail:
            shown = "\n".join(f"<code>{html.escape(f)}</code>" for f in fail[:5])
            sum_lines.append(f"\nDetail:\n{shown}")

        rich_ok = await self.send_rich(
            event,
            "📢 Gcast Selesai",
            rich_rows,
            note=self.fmtsec(now),
            query_prefix="gcast",
        )
        with contextlib.suppress(Exception):
            await status.delete()
        if not rich_ok:
            await self.respond(
                event, "<b>📢 Gcast selesai</b>\n\n" + "\n".join(sum_lines)
            )
            return
        with contextlib.suppress(Exception):
            await event.delete()

    async def _resend(self, chat_id: int, reply: Message, caption: str) -> None:
        """Kirim ulang media tanpa forward header."""
        path = await reply.download()
        kind = reply.media.value if reply.media else "document"
        fn = getattr(self.client.app, f"send_{kind}", self.client.app.send_document)
        if path:
            await fn(chat_id, path, caption=caption or None)
        else:
            await reply.copy(chat_id)
