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

ucast_pattern = re.compile(r"^\.?ucast(?:\s+([\s\S]+))?$", re.IGNORECASE | re.DOTALL)
bl_pattern = re.compile(r"^\.?(addbl|delbl|listbl)(?:\s+(\S+))?$", re.IGNORECASE)

DELAY = 1  # detik antar chat, anti FloodWait

# ==== state blacklist (di-memory, persist via db) ====
BL_KEY = "gcast_blacklist"


def _load_bl(client) -> set[int]:
    doc = client.db[BL_KEY].find_one({"_id": "bl"})
    return set(doc["ids"]) if doc else set()


def _save_bl(client, ids: set[int]) -> None:
    client.db[BL_KEY].replace_one({"_id": "bl"}, {"ids": list(ids)}, upsert=True)


class Ucast(Module):
    name = "Ucast"
    cmds = ".ucast {pesan} | .addbl/.delbl {id|@user} | .listbl"
    desc = {
        "pesan": "Kirim teks ke semua private chat/kontak (DM massal).",
        "addbl": "Blacklist grup → dilewati .gcast.",
        "delbl": "Hapus grup dari blacklist.",
        "listbl": "Lihat daftar blacklist.",
        "Note": "Delay 1 detik per chat.",
        "e.g.": ".ucast halo bro",
    }

    @handler(filters.regex(ucast_pattern) & filters.outgoing, 1)
    async def on_ucast(self, event: Message) -> None:
        match = ucast_pattern.match(event.text or "")
        if not match:
            return
        text = (match.group(1) or "").strip()
        if not text:
            await self.respond(
                event, "<b>Cara pakai:</b> <code>.ucast {pesan}</code>"
            )
            return

        status = await self.respond(event, "<code>🔍 Mengumpulkan private chat...</code>")
        now = datetime.datetime.now(datetime.UTC)

        targets = []
        async for dialog in self.client.app.get_dialogs(limit=None):
            chat = dialog.chat
            # private chat + saved messages, bukan bot
            if chat and chat.type == ChatType.PRIVATE and not chat.bot:
                targets.append(chat.id)

        total = len(targets)
        if not total:
            with contextlib.suppress(Exception):
                await self._upd(status, "<b>Gagal:</b> gak ada private chat ditemukan.")
            return

        ok, fail = 0, []
        for i, chat_id in enumerate(targets, 1):
            try:
                await self.client.app.send_message(chat_id, text)
                ok += 1
            except Exception as e:
                fail.append(str(e)[:80])
            if i % 5 == 0 or i == total:
                with contextlib.suppress(Exception):
                    await self._upd(status, 
                        f"<b>📨 Ucast</b>\n\n"
                        f"Progress: <code>{i}/{total}</code> · ✅ {ok} · ❌ {len(fail)}"
                    )
            if DELAY:
                await asyncio.sleep(DELAY)

        # === Kartu rich ===
        rich_rows = [
            ("Target", f"{total} chat"),
            ("Berhasil", f"✅ {ok}"),
            ("Gagal", f"❌ {len(fail)}"),
        ]
        if fail:
            rich_rows.append(("Error (contoh)", fail[0][:60]))

        sum_lines = [
            f"✅ Berhasil: <b>{ok}</b>",
            f"❌ Gagal: <b>{len(fail)}</b>",
        ]
        if fail:
            shown = "\n".join(f"<code>{html.escape(f)}</code>" for f in fail[:5])
            sum_lines.append(f"\nDetail:\n{shown}")

        rich_ok = await self.send_rich(
            event,
            "📨 Ucast Selesai",
            rich_rows,
            note=self.fmtsec(now),
            query_prefix="ucast",
        )
        with contextlib.suppress(Exception):
            await self._upd(status, "<b>📨 Ucast selesai</b>")
        if not rich_ok:
            await self.respond(
                event, "<b>📨 Ucast selesai</b>\n\n" + "\n".join(sum_lines)
            )

    # --------------------------------------------------
    # Blacklist grup untuk gcast
    # --------------------------------------------------

    @handler(filters.regex(bl_pattern) & filters.outgoing, 1)
    async def on_bl(self, event: Message) -> None:
        match = bl_pattern.match(event.text or "")
        if not match:
            return
        cmd, arg = match.group(1).lower(), match.group(2)
        bl = _load_bl(self.client)

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

        # addbl/delbl: pakai argumen, atau reply ke chat grup
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
            _save_bl(self.client, bl)
            await self.respond(event, f"<b>🚫 Blacklisted:</b> <code>{target}</code>")
        else:
            bl.discard(target)
            _save_bl(self.client, bl)
            await self.respond(event, f"<b>✅ Unblacklisted:</b> <code>{target}</code>")

    async def _upd(self, status, text: str) -> None:
        """Edit status message — status bisa Message atau int (message_id)."""
        with contextlib.suppress(Exception):
            if hasattr(status, "edit"):
                await status.edit(text)
            else:
                await self.client.app.edit_message_text(
                    self.client.app.me.id, status, text
                )
