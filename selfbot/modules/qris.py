import contextlib
import os
import re

from pyrogram import filters
from pyrogram.types import Message

from selfbot.listener import handler, reply
from selfbot.module import Module

pattern = re.compile(r"^(?:qris|trakteer|sawer)(?:\s+(-d|--doc))?$", re.IGNORECASE)

ASSET = os.path.join(os.path.dirname(__file__), "..", "assets", "qris.png")


class Qris(Module):
    """Kirim poster QRIS pembayaran kedai zp."""

    name = "QRIS Payment"
    cmds = "qris (-d)?"
    desc = {
        "?": "-d kirim sebagai dokumen",
        "e.g.": "qris",
    }

    @handler(filters.regex(pattern) & ~reply, 0)
    async def on_message_out(self, event: Message) -> None:
        await self.execute(event)

    @handler(filters.regex(pattern), 1)
    async def on_message_in(self, event: Message) -> None:
        await self.execute(event)

    async def execute(self, event: Message) -> None:
        m = pattern.match(event.text or "")
        as_doc = bool(m and m.group(1))
        if not os.path.isfile(ASSET):
            await self.respond(event, "<code>File QRIS gak ketemu.</code>")
            return
        with contextlib.suppress(Exception):
            await event.delete()
        if as_doc:
            await self.client.app.send_document(
                event.chat.id, ASSET,
                caption=" <b>QRIS kedai zp</b> — satu QRIS untuk semua",
            )
        else:
            await self.client.app.send_photo(
                event.chat.id, ASSET,
                caption=" <b>QRIS kedai zp</b> — satu QRIS untuk semua",
            )
