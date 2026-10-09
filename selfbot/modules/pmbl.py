import asyncio
import contextlib
import datetime
import re

from pyrogram import filters
from pyrogram.types import InlineQuery, Message

from selfbot.listener import handler
from selfbot.module import Module

# Deteksi awal command; isi argumen di-parse manual (biar gampang dibaca).
pattern = re.compile(r"^\.?pmbl(?:\s.*)?$", re.IGNORECASE | re.DOTALL)


class PMBL(Module):
    name = "PM Block"
    cmds = ".pmbl (ok|no|list {id})? (-{msg|url} {value})?"
    desc = {
        "pmbl": "Toggle on/off",
        "ok": "Approve user (id)",
        "no": "Cabut approve user (id)",
        "list": "Daftar approved + tombol cabut",
        "msg": "Set pesan kartu",
        "url": "Set URL tombol kartu",
        "e.g.": ".pmbl ok 123456",
    }
    status, msg, url = False, "Jangan PM!", "t.me/wass4pbruh"

    # ── storage ──────────────────────────────────────────────────────
    async def _appr_all(self) -> dict:
        row = await self.client.db.pmbl_meta.find_one({"_id": "approved"})
        return {k: v for k, v in (row or {}).items() if k != "_id"}

    async def _appr_add(self, user_id: int, name: str = "") -> None:
        if not name:
            with contextlib.suppress(Exception):
                u = await self.client.app.get_users(int(user_id))
                name = u.first_name or ""
                if getattr(u, "last_name", None):
                    name += f" {u.last_name}"
        await self.client.db.pmbl_meta.update_one(
            {"_id": "approved"},
            {"$set": {str(user_id): name or str(user_id)}},
            upsert=True,
        )

    async def _appr_del(self, user_id: int) -> None:
        await self.client.db.pmbl_meta.update_one(
            {"_id": "approved"}, {"$unset": {str(user_id): ""}}
        )

    async def _appr_clear(self) -> None:
        await self.client.db.pmbl_meta.delete_one({"_id": "approved"})

    def _card(self, now) -> str:
        return self.fmtmsg(
            "PM Block",
            {
                "Status": self.status,
                "Message": self.msg,
                "Button URL": self.url,
            },
            self.fmtsec(now),
        )

    async def _list_view(self) -> tuple[str, object]:
        """Teks + keyboard daftar approved (dipakai inline & refresh callback)."""
        appr = await self._appr_all()
        if not appr:
            return "<b>Approved</b>\n\n<i>Belum ada yang disetujui.</i>", None

        rows, lines = [], []
        for i, (uid, name) in enumerate(appr.items(), 1):
            lines.append(f"{i}. {name} — <code>{uid}</code>")
            label = (name or uid)[:40]
            rows.append([(f"🗑 {label}", "data", f"pmbl_rev:{uid}", "R")])
        rows.append([("🗑 Bersihkan semua", "data", "pmbl_rev_all", "R")])
        rows.append([("✖️ Tutup", "data", "pmbl_close", "D")])
        text = "<b>Approved</b>\n\n" + "\n".join(lines)
        return text, self.ikm(rows)

    async def on_started(self) -> None:
        row = await self.client.db.pmbl_meta.find_one({"_id": "meta"})
        if not row:
            await self.client.db.pmbl_meta.update_one(
                {"_id": "meta"},
                {"$set": {"status": self.status, "msg": self.msg, "url": self.url}},
                upsert=True,
            )
            return
        self.status = row.get("status", self.status)
        self.msg = row.get("msg", self.msg)
        self.url = row.get("url", self.url)

    # ── command ──────────────────────────────────────────────────────
    @handler(filters.regex(pattern), 1)
    async def on_message_out(self, event: Message) -> None:
        text = (self.message_text(event) or "").strip()
        now = datetime.datetime.now(datetime.UTC)
        args = text.lstrip(".").split()
        args = args[1:]  # buang "pmbl"

        # tanpa argumen → toggle
        if not args:
            self.status = not self.status
            await self.client.db.pmbl_meta.update_one(
                {"_id": "meta"}, {"$set": {"status": self.status}}, upsert=True
            )
            await self.respond(event, self._card(now))
            return

        head = args[0].lower()

        if head == "list":
            with contextlib.suppress(Exception):
                await event.delete()
            res = await self.client.app.get_inline_bot_results(
                self.client.bot.me.id, f"pmbl_list{now.timestamp()}"
            )
            if res.results:
                with contextlib.suppress(Exception):
                    await event.reply_inline_bot_result(
                        res.query_id, res.results[0].id
                    )
            return

        if head in ("ok", "no"):
            if len(args) < 2 or not args[1].isdigit():
                await self.respond(event, "<code>.pmbl ok &lt;id&gt;</code>")
                return
            uid = int(args[1])
            if head == "ok":
                await self._appr_add(uid)
                await self.respond(event, f"<b>PMBL</b>: ✅ <code>{uid}</code> boleh PM")
            else:
                await self._appr_del(uid)
                with contextlib.suppress(Exception):
                    await self.client.app.unblock_user(uid)
                await self.respond(
                    event, f"<b>PMBL</b>: 🚫 <code>{uid}</code> dicabut"
                )
            return

        if head in ("-msg", "-url"):
            value = text.lstrip(".").split(None, 2)
            value = value[2].strip() if len(value) > 2 else ""
            if not value:
                await self.respond(event, "<code>Kasih teksnya.</code>")
                return
            field = "msg" if head == "-msg" else "url"
            setattr(self, field, value)
            await self.client.db.pmbl_meta.update_one(
                {"_id": "meta"}, {"$set": {field: value}}, upsert=True
            )
            await self.respond(event, self._card(now))
            return

        await self.respond(
            event,
            "<b>PMBL</b>\n\n"
            "<code>.pmbl</code> on/off · <code>.pmbl ok/no &lt;id&gt;</code> · "
            "<code>.pmbl list</code> · <code>.pmbl -msg/-url &lt;teks&gt;</code>",
        )

    # ── PM masuk ─────────────────────────────────────────────────────
    @handler(filters.incoming & filters.private, 2)
    async def on_app(self, event: Message) -> None:
        user = event.from_user
        if not user or user.is_self or user.is_bot or not self.status:
            return

        if user.is_verified or user.is_support:
            return

        # udah di-approve → biarkan (bisa dibaca & dibales normal)
        if str(user.id) in await self._appr_all():
            return

        await self.client.app.read_chat_history(event.chat.id, max_id=event.id)

        # Inline dulu (harus cepat, Telegram timeout ~10s), sisanya belakangan.
        # Retry sekali kalau bot lambat jawab.
        res = None
        for _ in range(2):
            try:
                res = await self.client.app.get_inline_bot_results(
                    self.client.bot.me.id, f"pmbl {user.id}"
                )
                break
            except Exception:
                await asyncio.sleep(1)
        if res and res.results:
            with contextlib.suppress(Exception):
                await event.reply_inline_bot_result(
                    res.query_id, res.results[0].id
                )

        # bersihin kartu warning LAMA doang (yang udah kedaluwarsa),
        # kartu terbaru yang barusan dikirim jangan ikut kehapus.
        latest_id = None
        with contextlib.suppress(Exception):
            async for old in self.client.app.get_chat_history(
                event.chat.id, limit=6
            ):
                if old.reply_markup:
                    if latest_id is None:
                        latest_id = old.id  # kartu barusan → biarkan
                        continue
                    with contextlib.suppress(Exception):
                        await old.delete()

        # PM-nya dihapus paling akhir, SETELAH kartu baru pasti kekirim.
        await self.client.app.delete_messages(
            event.chat.id, [event.id], revoke=True
        )

    @handler(filters.incoming & filters.private, 2)
    async def on_bot(self, event: Message) -> None:
        """PM ke bot → abaikan."""
        return

    # ── inline: kartu PM & daftar approved (event = "inline_query") ──
    @handler(filters.regex(r"^pmbl"), 3)
    async def on_inline_query(self, event: InlineQuery) -> None:
        query = (event.query or "").strip()

        if query.startswith("pmbl_list"):
            text, markup = await self._list_view()
            await self.answer(event, markup, text)
            return

        uid = query.split()[-1]
        await self.answer(
            event,
            self.ikm([
                [("✅", "data", f"pmbl_ok:{uid}", "G"),
                 ("🚫", "data", f"pmbl_no:{uid}", "R")],
            ]),
            f"<blockquote><b>{self.msg}</b></blockquote>",
        )

    # ── callbacks ────────────────────────────────────────────────────
    @handler(filters.regex(r"^pmbl_"), 4)
    async def on_inline_callback(self, event) -> None:
        data = event.data or ""
        if isinstance(data, bytes):
            data = data.decode(errors="ignore")
        act, _, uid = data.partition(":")

        if act == "pmbl_ok":
            if uid.isdigit():
                await self._appr_add(int(uid))
            with contextlib.suppress(Exception):
                await event.edit_message_text(
                    "<b>✅ PM lu disetujui.</b>"
                )
            await event.answer("Disetujui 👍", show_alert=True)
            return

        if act == "pmbl_no":
            if uid.isdigit():
                with contextlib.suppress(Exception):
                    await self.client.app.block_user(int(uid))
            with contextlib.suppress(Exception):
                await event.edit_message_text(f"<b>🚫 {self.msg}</b>")
            await event.answer("Ditolak — diblok 🚫", show_alert=True)
            return

        if act == "pmbl_rev":
            if uid.isdigit():
                await self._appr_del(int(uid))
            text, markup = await self._list_view()
            with contextlib.suppress(Exception):
                await event.edit_message_text(text, reply_markup=markup)
            await event.answer("Dicabut — orang ini kena PMBL lagi 🚫")
            return

        if act == "pmbl_rev_all":
            await self._appr_clear()
            text, markup = await self._list_view()
            with contextlib.suppress(Exception):
                await event.edit_message_text(text, reply_markup=markup)
            await event.answer("Semua approve dicabut 🚫")
            return

        if act == "pmbl_close":
            with contextlib.suppress(Exception):
                await event.edit_message_text("<i>Tertutup.</i>", reply_markup=None)
            await event.answer()
            return

        await event.answer()
