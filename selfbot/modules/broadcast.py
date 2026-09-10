import asyncio
import datetime

from pyrogram import enums, filters
from pyrogram.errors import FloodWait, RPCError
from pyrogram.types import Message

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

    @handler(filters.regex(r"^gcast\s( group| all)$".replace(" ", "")) & reply, 1)
    async def on_message_out(self, event: Message) -> None:
        mode = (event.text or event.caption).split()[-1]
        rep = event.reply_to_message

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
                    f"  <code>Gagal </code> : <code>{fail}</code>"
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
            f"  <code>Waktu </code> : <code>{dur:.1f}s</code>"
        )

