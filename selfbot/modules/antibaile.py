import asyncio
import contextlib
import re

from pyrogram import filters
from pyrogram.raw.functions.channels import GetParticipant
from pyrogram.raw.functions.messages import ImportChatInvite
from pyrogram.raw.types import ChannelParticipantLeft, ChannelParticipantBanned
from pyrogram.types import Message

from selfbot.listener import handler
from selfbot.module import Module

AB_PATTERN = re.compile(
    r"^\.?(?:antibaile|ab)(?:\s+(on|off|add|del|list))?(?:\s+(\S+))?\s*$",
    re.IGNORECASE,
)


class Antibaile(Module):
    name = "Antibaile"
    cmds = "{antibaile|ab} {on|off|add|del|list}"
    desc = {
        "on/off": "Aktif/nonaktifkan auto-rejoin.",
        "add": "Daftarkan grup ini (opsional + link invite).",
        "del": "Hapus dari daftar.",
        "list": "Lihat daftar grup terproteksi.",
        "e.g.": "ab add",
    }

    async def on_starting(self) -> None:
        try:
            await self.client.db.antibaile.create_index([("chat_id", 1)], unique=True)
        except Exception:
            pass
        asyncio.create_task(self._watch())

    # --------------------------------------------------
    # Commands
    # --------------------------------------------------

    @handler(filters.regex(AB_PATTERN), 1)
    async def on_message_out(self, event: Message) -> None:
        text = str(event.content)
        m = AB_PATTERN.match(text)
        sub, arg = (m.group(1) or "").lower(), m.group(2)

        if sub == "on":
            await self.client.db.antibaile_settings.update_one(
                {"_id": "global"}, {"$set": {"enabled": True}}, upsert=True
            )
            await self.respond(event, "✅ <b>Antibaile ON</b>")
        elif sub == "off":
            await self.client.db.antibaile_settings.update_one(
                {"_id": "global"}, {"$set": {"enabled": False}}, upsert=True
            )
            await self.respond(event, "⛔ <b>Antibaile OFF</b>")
        elif sub == "add":
            await self._cmd_add(event, arg)
        elif sub == "del":
            await self._cmd_del(event, arg)
        elif sub == "list":
            await self._cmd_list(event)
        else:
            await self.respond(
                event,
                "<b>Antibaile</b>\n"
                "<code>ab on</code> — aktifkan\n"
                "<code>ab off</code> — matikan\n"
                "<code>ab add</code> — daftarkan grup ini\n"
                "<code>ab del</code> — hapus grup ini\n"
                "<code>ab list</code> — daftar grup",
            )

    async def _cmd_add(self, event: Message, arg: str) -> None:
        chat = event.chat
        if chat is None or chat.id > 0:
            await self.respond(event, "❌ Pakai di dalam grup yang mau diproteksi.")
            return

        link = arg
        if not link:
            link = await self._export_invite(event._client, chat.id)
            if not link:
                await self.respond(
                    event,
                    "❌ Gagal ambil link invite. Kirim manual: <code>ab add https://t.me/+</code>...",
                )
                return

        await self.client.db.antibaile.update_one(
            {"chat_id": chat.id},
            {"$set": {"chat_id": chat.id, "title": chat.title or "?", "link": link}},
            upsert=True,
        )
        await self.respond(event, f"✅ <b>{chat.title}</b> terdaftar antibaile.")

    async def _cmd_del(self, event: Message, arg: str) -> None:
        chat = event.chat
        cid = int(arg) if arg and arg.lstrip("-").isdigit() else (chat.id if chat else None)
        if cid is None:
            await self.respond(event, "❌ Reply di grup, atau <code>ab del &lt;chat_id&gt;</code>.")
            return
        res = await self.client.db.antibaile.delete_one({"chat_id": cid})
        await self.respond(event, "🗑️ Dihapus." if res.deleted_count else "❌ Gak ketemu.")

    async def _cmd_list(self, event: Message) -> None:
        docs = [d async for d in self.client.db.antibaile.find({})]
        if not docs:
            await self.respond(event, "📭 Belum ada grup terdaftar.")
            return
        lines = [f"• <b>{d.get('title', '?')}</b> <code>{d['chat_id']}</code>" for d in docs]
        cfg = await self.client.db.antibaile_settings.find_one({"_id": "global"})
        status = "ON ✅" if cfg and cfg.get("enabled") else "OFF ⛔"
        await self.respond(event, f"<b>Antibaile:</b> {status}\n\n" + "\n".join(lines))

    # --------------------------------------------------
    # Watcher: cek membership berkala
    # --------------------------------------------------

    async def _watch(self) -> None:
        while True:
            await asyncio.sleep(180)
            with contextlib.suppress(Exception):
                await self._check_all()

    async def _check_all(self) -> None:
        cfg = await self.client.db.antibaile_settings.find_one({"_id": "global"})
        if not cfg or not cfg.get("enabled"):
            return
        docs = [d async for d in self.client.db.antibaile.find({})]
        for d in docs:
            with contextlib.suppress(Exception):
                await self._check_chat(d)

    async def _check_chat(self, d: dict) -> None:
        app = self.client.app
        raw = app
        try:
            peer = await raw.resolve_peer(d["chat_id"])
            channel = peer.channel_id if hasattr(peer, "channel_id") else None
            from pyrogram.raw.types import InputChannel
            chan = InputChannel(channel_id=channel, access_hash=peer.access_hash)
            part = await raw.invoke(GetParticipant(
                channel=chan,
                participant=await raw.resolve_peer(app.me.id),
            ))
            p = part.participant
            # masih member normal → aman
            if not isinstance(p, (ChannelParticipantLeft, ChannelParticipantBanned)):
                return
        except Exception:
            # ParticipantAbsent = bukan member (kena kick)
            pass

        link = d.get("link") or ""
        if "t.me/+" in link:
            with contextlib.suppress(Exception):
                code = link.rsplit("/", 1)[-1]
                await raw.invoke(ImportChatInvite(hash=code))
                self.logger.info(f"Antibaile: rejoin {d.get('title')}")
        else:
            with contextlib.suppress(Exception):
                await app.join_chat(link.replace("https://t.me/", ""))
                self.logger.info(f"Antibaile: rejoin {d.get('title')}")

    async def _export_invite(self, client, chat_id: int) -> str | None:
        from pyrogram.raw.functions.messages import ExportChatInvite

        try:
            peer = await client.resolve_peer(chat_id)
            inv = await client.invoke(ExportChatInvite(peer=peer))
            return getattr(inv, "link", None)
        except Exception:
            return None
