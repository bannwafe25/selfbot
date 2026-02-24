import datetime
import html
import re
from io import BytesIO

from pyrogram import filters
from pyrogram.types import Message

from selfbot.listener import handler
from selfbot.module import Module
from selfbot.apis import DELINE_REMOVEBG, UPLOAD_0X0, UPLOAD_TMPFILES, UPLOAD_CATBOX

pattern = re.compile(r"^removebg(?:\s+)?$", re.IGNORECASE)

SUPPORTED_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/bmp",
}


class RemoveBG(Module):
    name = "Remove Background"
    cmds = "removebg"
    desc = {
        "Info": "Remove background from replied image.",
        "e.g.": "removebg (reply to image)",
    }

    @handler(filters.regex(pattern), 1)
    async def on_message_out(self, event: Message) -> None:
        await self.respond(event, "<code>Processing image...</code>")
        now = datetime.datetime.now(datetime.UTC)

        media = self._extract_media(event)
        if not media:
            await self.respond(
                event,
                "<code>Reply to an image first. Supported: JPEG, PNG, WEBP, BMP</code>",
            )
            return

        try:
            await self.respond(event, "<code>Downloading image...</code>")
            target = event.reply_to_message or event
            data = await event._client.download_media(media, in_memory=True)
            if not data:
                await self.respond(event, "<code>Failed to download image.</code>")
                return

            raw = self.to_bytes(data)
            if not raw:
                await self.respond(event, "<code>Downloaded file is empty.</code>")
                return

            await self.respond(event, "<code>Uploading image...</code>")
            mime = self._detect_mime(target)
            image_url = await self._upload_image(raw, mime)
            if not image_url:
                await self.respond(
                    event, "<code>Failed to upload image for processing.</code>"
                )
                return

            await self.respond(event, "<code>Removing background...</code>")
            resp = await self.client.http.get(
                DELINE_REMOVEBG,
                params={"url": image_url},
                timeout=60,
            )
            if resp.status_code != 200:
                raise RuntimeError(f"API error: HTTP {resp.status_code}")

            result = BytesIO(resp.content)
            result.name = "removebg.png"
            result.seek(0)

            await event.reply_document(
                document=result,
                caption=f"<b><blockquote>{self.fmtsec(now)}</blockquote></b>",
            )
            await event.delete()
        except Exception as e:
            await self.respond(
                event,
                f"<b>RemoveBG failed</b>\n\n<code>{html.escape(str(e)[:300])}</code>",
            )

    def _extract_media(self, event: Message):
        replied = event.reply_to_message
        target = replied if replied else event

        if target.photo:
            return target.photo
        doc = target.document
        if doc:
            mime = (doc.mime_type or "").lower()
            if mime in SUPPORTED_MIME_TYPES:
                return doc
        return None

    @staticmethod
    def _detect_mime(message: Message) -> str:
        if message.photo:
            return "image/jpeg"
        if message.document and message.document.mime_type:
            return message.document.mime_type
        return "image/jpeg"

    async def _upload_image(self, raw: bytes, mime: str) -> str | None:
        uploaders = [self._upload_0x0, self._upload_tmpfiles, self._upload_catbox]
        for uploader in uploaders:
            try:
                url = await uploader(raw, mime)
                if url:
                    return url
            except Exception:
                continue
        return None

    async def _upload_0x0(self, raw: bytes, mime: str) -> str | None:
        resp = await self.client.http.post(
            UPLOAD_0X0, files={"file": ("image", raw, mime)}, timeout=60
        )
        if resp.status_code == 200:
            url = resp.text.strip()
            if url.startswith("http"):
                return url
        return None

    async def _upload_tmpfiles(self, raw: bytes, mime: str) -> str | None:
        resp = await self.client.http.post(
            UPLOAD_TMPFILES, files={"file": ("image", raw, mime)}, timeout=60
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        url = (((data.get("data") or {}).get("url")) or "").strip()
        if not url:
            return None
        if "tmpfiles.org/" in url and "/dl/" not in url:
            return url.replace("tmpfiles.org/", "tmpfiles.org/dl/")
        return url

    async def _upload_catbox(self, raw: bytes, mime: str) -> str | None:
        resp = await self.client.http.post(
            UPLOAD_CATBOX,
            data={"reqtype": "fileupload"},
            files={"fileToUpload": ("image", raw, mime)},
            timeout=60,
        )
        if resp.status_code == 200:
            url = resp.text.strip()
            if url.startswith("http"):
                return url
        return None
