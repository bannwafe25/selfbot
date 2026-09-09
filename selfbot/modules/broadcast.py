import asyncio
import datetime

from pyrogram import enums, filters
from pyrogram.errors import FloodWait, RPCError
from pyrogram.types import Message

from selfbot.listener import handler, reply
from selfbot.module import Module
from selfbot.database import dB


class Broadcast(Module):
    name = "Broadcast"
    cmds = "bc {groups|all} (reply pesan)"
    desc = {
        "groups": "Kirim ke semua grup & channel tempat kamu member",
        "all": "Kirim ke semua grup + chat pribadi",
        "addbl": "Tambahkan chat ke blacklist broadcast",
        "delbl": "Hapus chat dari blacklist broadcast",
        "e.g.": "reply pesan, lalu ketik: bc groups",
    }

    # =========================
    # BROADCAST
    # =========================

    @handler(filters.regex(r"^bc\s( groups| all)$".replace(" ", "")) & reply, 1)
    async def on_message_out(self, event: Message) -> None:
        mode = (event.text or event.caption).split()[-1]
        rep = event.reply_to_message

        msg = await self.respond(
            event,
            "<code>Menghitung target...</code>",
        )

        now = datetime.datetime.now(datetime.UTC)

        # Ambil blacklist
        blacklist = await dB.get_list_from_var(
            event._client.me.id,
            "BLACKLIST_GCAST",
        )

        # Pastikan blacklist berupa set agar pengecekan cepat
        blacklist = set(map(str, blacklist))

        targets = []

        async for dialog in event._client.get_dialogs():
            chat_id = dialog.chat.id

            # Skip akun sendiri
            if chat_id == event._client.me.id:
                continue

            # Skip blacklist
            if str(chat_id) in blacklist:
                continue

            if mode == "groups":
                if dialog.chat.type in (
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
    # ADD BLACKLIST
    # =========================

    @handler(filters.regex(r"^addbl(?:\s(-?\d+))?$"), 1)
    async def addbl_cmd(self, event: Message) -> None:
        parts = (event.text or event.caption or "").split()

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

        blacklist = await dB.get_list_from_var(
            event._client.me.id,
            "BLACKLIST_GCAST",
        )

        if str(chat_id) in map(str, blacklist):
            await self.respond(
                event,
                f"<code>{chat_id}</code> sudah ada di blacklist.",
                revoke=3,
            )
            return

        await dB.add_to_var(
            event._client.me.id,
            "BLACKLIST_GCAST",
            chat_id,
        )

        await self.respond(
            event,
            f"🚫 <b>Blacklist ditambahkan</b>\n"
            f"<code>{chat_id}</code>",
            revoke=3,
        )

    # =========================
    # DELETE BLACKLIST
    # =========================

    @handler(filters.regex(r"^delbl(?:\s(-?\d+|all))?$"), 1)
    async def delbl_cmd(self, event: Message) -> None:
        parts = (event.text or event.caption or "").split()

        blacklist = await dB.get_list_from_var(
            event._client.me.id,
            "BLACKLIST_GCAST",
        )

        if not parts or len(parts) == 1:
            chat_id = event.chat.id

            if str(chat_id) not in map(str, blacklist):
                await self.respond(
                    event,
                    f"<code>{chat_id}</code> tidak ada di blacklist.",
                    revoke=3,
                )
                return

            await dB.remove_from_var(
                event._client.me.id,
                "BLACKLIST_GCAST",
                chat_id,
            )

            await self.respond(
                event,
                f"✅ <b>Blacklist dihapus</b>\n"
                f"<code>{chat_id}</code>",
                revoke=3,
            )
            return

        target = parts[1].lower()

        # Hapus semua
        if target == "all":
            for chat_id in list(blacklist):
                await dB.remove_from_var(
                    event._client.me.id,
                    "BLACKLIST_GCAST",
                    chat_id,
                )

            await self.respond(
                event,
                f"✅ <b>Semua blacklist dihapus</b>\n"
                f"<code>{len(blacklist)}</code> chat",
                revoke=3,
            )
            return

        try:
            chat_id = int(target)
        except ValueError:
            await self.respond(
                event,
                "<code>ID chat tidak valid.</code>",
                revoke=3,
            )
            return

        if str(chat_id) not in map(str, blacklist):
            await self.respond(
                event,
                f"<code>{chat_id}</code> tidak ada di blacklist.",
                revoke=3,
            )
            return

        await dB.remove_from_var(
            event._client.me.id,
            "BLACKLIST_GCAST",
            chat_id,
        )

        await self.respond(
            event,
            f"✅ <b>Blacklist dihapus</b>\n"
            f"<code>{chat_id}</code>",
            revoke=3,
        )
