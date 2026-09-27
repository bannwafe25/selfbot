from __future__ import annotations

import contextlib
import re

from pyrogram import filters
from pyrogram.types import Message
from telegraph import Telegraph
from telegraph.exceptions import TelegraphException

from selfbot.listener import handler
from selfbot.module import Module

pattern = re.compile(
    r"^\.?t(?:ele)?graph(?:\s+(.+))?$",
    re.IGNORECASE | re.DOTALL,
)

# simpan account biar token konsisten antar restart
_TOKEN_FILE = "storage/telegraph.txt"


class TelegraPh(Module):
    name = "Telegra.ph"
    cmds = (
        ".telegraph <reply photo/video/file>\n"
        ".telegraph <text>  (buat halaman)"
    )
    desc = {
        "reply": "Balas media buat upload ke telegra.ph",
        "text": "Bikin halaman dari teks",
        "e.g.": ".telegraph halo dunia",
    }

    def __init__(self, client) -> None:
        super().__init__(client)
        self.tph: Telegraph | None = None

    async def on_starting(self) -> None:
        import os

        token = None
        if os.path.exists(_TOKEN_FILE):
            with open(_TOKEN_FILE) as f:
                token = f.read().strip() or None

        self.tph = Telegraph(access_token=token)
        if not token:
            try:
                me = self.tph.create_account(
                    short_name="selfbot", author_name="Selfbot"
                )
                token = me["access_token"]
                os.makedirs(os.path.dirname(_TOKEN_FILE), exist_ok=True)
                with open(_TOKEN_FILE, "w") as f:
                    f.write(token)
            except TelegraphException as e:
                self.logger.error(f"telegraph create_account: {e}")
                return

        self.tph = Telegraph(access_token=token)

    async def _upload_media(self, event: Message, reply) -> None:
        with contextlib.suppress(Exception):
            await event.edit("<code>Uploading...</code>")
        try:
            path = await reply.download(in_memory=True)
            with open(path, "rb") as f:
                files = self.tph.upload_file(f)
            url = "https://telegra.ph" + files[0]
        except Exception as e:
            await event.edit(f"<b>Upload gagal</b>\n<blockquote>{e}</blockquote>")
            return
        await event.edit(
            f"<b>🔗 Uploaded</b>\n\n{url}",
            disable_web_page_preview=False,
        )

    async def _create_page(self, event: Message, text: str) -> None:
        try:
            page = self.tph.create_page(
                title=(text[:40] or "Selfbot Note"),
                content=[{"tag": "p", "children": [text]}],
            )
        except TelegraphException as e:
            await event.edit(f"<b>Gagal bikin halaman</b>\n<blockquote>{e}</blockquote>")
            return
        await event.edit(
            f"<b>📄 Page dibuat</b>\n\n{page['url']}",
            disable_web_page_preview=False,
        )

    @handler(filters.regex(pattern) & filters.outgoing, 1)
    async def on_message_out(self, event: Message) -> None:
        m = pattern.match((event.text or "").strip())
        text = (m.group(1) or "").strip() if m else ""

        # kalau nge-reply media → upload
        if event.reply_to_message and event.reply_to_message.media:
            await self._upload_media(event, event.reply_to_message)
            return

        if not self.tph:
            await event.edit("<code>Telegraph belum siap, coba lagi...</code>")
            return

        if text:
            await self._create_page(event, text)
        else:
            await event.edit(
                "<b>Cara pakai:</b>\n"
                "• Balas foto/video → <code>.telegraph</code>\n"
                "• Bikin halaman → <code>.telegraph &lt;teks&gt;</code>"
            )
