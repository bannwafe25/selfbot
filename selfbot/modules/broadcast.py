import asyncio
import datetime

from pyrogram import enums, filters
from pyrogram.errors import FloodWait, RPCError
from pyrogram.types import Message

from selfbot.listener import handler, reply
from selfbot.module import Module


class Broadcast(Module):
    name = "Broadcast"
    cmds = "bc {groups|all} | addbl [chat_id] | delbl [chat_id|all]"
    desc = {
        "groups": "Kirim ke semua grup & channel tempat kamu member",
        "all": "Kirim ke semua grup + chat pribadi",
        "addbl": "Tambahkan chat ke blacklist broadcast",
        "delbl": "Hapus chat dari blacklist broadcast",
        "e.g.": "reply pesan, lalu ketik: bc groups",
    }

    # =========================
    # DATABASE BLACKLIST
    # =========================

    async def get_blacklist(self):
        doc = await self.client.db.broadcast_blacklist.find_one(
            {"_id": self.client.me.id}
        )

        if not doc:
            return set()

        return set(doc.get("chat_ids", []))

    async def save_blacklist(self, blacklist):
        await self.client.db.broadcast_blacklist.update_one(
            {"_id": self.client.me.id},
            {
                "$set": {
                    "chat_ids": list(blacklist),
                }
            },
            upsert=True,
        )

    # =========================
    # BROADCAST
    # =========================

    @handler(
        filters.regex(r"^bc\s+(groups|all)$") & reply,
        1,
    )
    async def on_message_out(self, event: Message) -> None:
        text = event.text or event.caption or ""
        mode = text.strip().split()[-1].lower()
        rep = event.reply_to_message

        msg = await self.respond(
            event,
            "<code>Menghitung target...</code>",
        )

        now = datetime.datetime.now(datetime.UTC)

        blacklist = await self.get_blacklist()
        targets = []

        async for dialog in event._client.get_dialogs():
            chat = dialog.chat
            chat_id = chat.id

            # Skip akun sendiri
            if chat_id == event._client.me.id:
                continue

            # Skip blacklist
            if chat_id in blacklist:
                continue

            if mode == "groups":
                if chat.type in (
                    enums.ChatType.GROUP,
                    enums.ChatType.SUPERGROUP,
                    enums.ChatType.CHANNEL,
                ):
                    targets.append(dialog)
            else:
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
                    f"  <code>Gagal </code> : <code>{fail}</code>\n"
                    f"  <code>Blacklist</code> : <code>{len(blacklist)}</code>"
                )

            await asyncio.sleep(2)

        dur = (
            datetime.datetime.now(datetime.UTC) - now
        ).total_seconds()

        await msg.edit_text(
            f"📢 <b>Broadcast Selesai</b>\n"
            f"  <code>Target</code> : <code>{total}</code>\n"
            f"  <code>Sukses</code> : <code>{ok}</code>\n"
            f"  <code>Gagal </code> : <code>{fail}</code>\n"
            f"  <code>Blacklist</code> : <code>{len(blacklist)}</code>\n"
            f"  <code>Waktu </code> : <code>{dur:.1f}s</code>"
        )

    # =========================
    # ADD / DELETE BLACKLIST
    # =========================

    @handler(
        filters.regex(r"^(?:addbl|delbl)(?:\s+(?:-?\d+|all))?$"),
        1,
    )
    async def blacklist_cmd(self, event: Message) -> None:
        text = event.text or event.caption or ""

        # Normalisasi
        parts = text.strip().split()

        if not parts:
            return

        command = parts[0].lower()

        # =========================
        # ADD BLACKLIST
        # =========================

        if command == "addbl":
            if len(parts) > 1:
                try:
                    chat_id = int(parts[1])
                except ValueError:
                    await self.respond(
                        event,
                        "<code>ID chat tidak valid.</code>",
                        revoke=3,
                    )
                    return
            else:
                chat_id = event.chat.id

            blacklist = await self.get_blacklist()

            if chat_id in blacklist:
                await self.respond(
                    event,
                    f"🚫 <code>{chat_id}</code> sudah ada di blacklist.",
                    revoke=3,
                )
                return

            blacklist.add(chat_id)
            await self.save_blacklist(blacklist)

            await self.respond(
                event,
                f"🚫 <b>Blacklist ditambahkan</b>\n"
                f"<code>{chat_id}</code>\n\n"
                f"Total blacklist: <code>{len(blacklist)}</code>",
                revoke=3,
            )
            return

        # =========================
        # DELETE BLACKLIST
        # =========================

        if command == "delbl":
            blacklist = await self.get_blacklist()

            # delbl all
            if len(parts) > 1 and parts[1].lower() == "all":
                total = len(blacklist)

                await self.save_blacklist(set())

                await self.respond(
                    event,
                    f"✅ <b>Semua blacklist dihapus</b>\n"
                    f"<code>{total}</code> chat",
                    revoke=3,
                )
                return

            # delbl <id>
            if len(parts) > 1:
                try:
                    chat_id = int(parts[1])
                except ValueError:
                    await self.respond(
                        event,
                        "<code>ID chat tidak valid.</code>",
                        revoke=3,
                    )
                    return
            else:
                # delbl tanpa ID = chat sekarang
                chat_id = event.chat.id

            if chat_id not in blacklist:
                await self.respond(
                    event,
                    f"<code>{chat_id}</code> tidak ada di blacklist.",
                    revoke=3,
                )
                return

            blacklist.remove(chat_id)
            await self.save_blacklist(blacklist)

            await self.respond(
                event,
                f"✅ <b>Blacklist dihapus</b>\n"
                f"<code>{chat_id}</code>\n\n"
                f"Sisa blacklist: <code>{len(blacklist)}</code>",
                revoke=3,
            )
