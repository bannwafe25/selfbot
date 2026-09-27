from __future__ import annotations

import contextlib
import os
import re

from pyrogram import filters
from pyrogram.types import LinkPreviewOptions, Message

from selfbot.listener import handler
from selfbot.module import Module

pattern = re.compile(r"^\.?toss(?:\s+(.+))?$", re.IGNORECASE | re.DOTALL)

MIME = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "gif": "image/gif",
    "mp4": "video/mp4",
}


class Toss(Module):
    name = "Image Upload"
    cmds = ".toss (reply media)"
    desc = {"reply": "Balas media buat upload ke qu.ax", "e.g.": ".toss"}

    @handler(filters.regex(pattern) & filters.outgoing, 1)
    async def on_message_out(self, event: Message) -> None:
        if not (event.reply_to_message and event.reply_to_message.media):
            await self.respond(
                event, "<b>Cara pakai:</b> balas foto/video → <code>.toss</code>"
            )
            return

        with contextlib.suppress(Exception):
            await event.edit("<code>Uploading...</code>")

        ext = self._guess_ext(event.reply_to_message)
        path = await event.reply_to_message.download()
        if not isinstance(path, str):
            with contextlib.suppress(Exception):
                await event.edit("<b>Upload gagal</b>\n<blockquote>file kosong</blockquote>")
            return

        tmp = f"{path}.{ext}"
        try:
            os.replace(path, tmp)
            url = await self._upload(tmp, ext)
        except Exception as e:
            with contextlib.suppress(Exception):
                await event.edit(f"<b>Upload gagal</b>\n<blockquote>{e}</blockquote>")
            return
        finally:
            with contextlib.suppress(Exception):
                os.remove(tmp)

        await self._reply(event, url)

    async def _reply(self, event: Message, url: str) -> None:
        """Kasih link halaman + direct (qu.ax butuh /x/<id>.<ext> buat file)."""
        direct = self._direct_url(url)
        teks = f"<b>🔗 Uploaded</b>\n\n{url}"
        if direct:
            teks += f"\n\n<b>Direct</b>\n<code>{direct}</code>"
        with contextlib.suppress(Exception):
            await event.edit(
                teks,
                link_preview_options=LinkPreviewOptions(is_disabled=False),
            )

    @staticmethod
    def _direct_url(url: str) -> str | None:
        """Ubah https://qu.ax/<id> jadi https://qu.ax/x/<id>.jpg."""
        m = re.match(r"^https?://qu\.ax/([A-Za-z0-9]+)/?$", url or "")
        if not m:
            return None
        return f"https://qu.ax/x/{m.group(1)}.jpg"

    async def _upload(self, path: str, ext: str) -> str:
        import httpx

        mime = MIME.get(ext, "application/octet-stream")
        with open(path, "rb") as f:
            files = {"file": (f"upload.{ext}", f.read(), mime)}

        async with httpx.AsyncClient(timeout=90, follow_redirects=True) as c:
            resp = await c.post("https://qu.ax/upload.php", files=files)
        resp.raise_for_status()

        data = resp.json()
        files_list = data.get("files") or []
        if not files_list:
            raise RuntimeError(str(data)[:200])
        url = files_list[0].get("url")
        if not url:
            raise RuntimeError(str(data)[:200])
        return url

    @staticmethod
    def _guess_ext(msg: Message) -> str:
        for obj in (msg.photo, msg.video, msg.animation, msg.document):
            if not obj:
                continue
            mime = getattr(obj, "mime_type", "") or ""
            if "/" in mime:
                sub = mime.split("/")[-1].lower()
                if sub in MIME:
                    return "jpg" if sub == "jpeg" else sub
            # nama file dokumen juga bisa jadi patokan
            fname = getattr(obj, "file_name", "") or ""
            if "." in fname:
                cand = fname.rsplit(".", 1)[-1].lower()
                if cand in MIME:
                    return cand
        if msg.photo:
            return "jpg"
        if msg.video or msg.animation:
            return "mp4"
        return "png"
