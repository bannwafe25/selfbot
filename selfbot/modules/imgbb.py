import datetime
import html
import re

from pyrogram import filters
from pyrogram.types import Message

from selfbot.listener import handler
from selfbot.module import Module

DISPATCH_PATTERN = re.compile(r"^(?:imgbb|setimgbb_api)(?:\s+[\s\S]+)?$", re.IGNORECASE)
SETKEY_PATTERN = re.compile(r"^setimgbb_api(?:\s+([\s\S]+))?$", re.IGNORECASE)

BASE_URL = "https://api.imgbb.com/1/upload"
SUPPORTED_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
    "image/bmp",
    "image/x-icon",
}


class Imgbb(Module):
    name = "ImgBB"
    cmds = "{imgbb|setimgbb_api} ..."
    desc = {
        "imgbb": "Upload replied/sent image to ImgBB.",
        "setimgbb_api": "Set ImgBB API key.",
        "e.g.": "setimgbb_api your_key_here",
    }

    async def on_starting(self) -> None:
        try:
            await self.client.db.imgbb_meta.create_index([("_id", 1)], unique=True)
        except Exception:
            pass

    @handler(filters.regex(DISPATCH_PATTERN), 1)
    async def on_message_out(self, event: Message) -> None:
        text = str(event.content).strip()
        if SETKEY_PATTERN.match(text):
            await self._cmd_setkey(event, text)
            return

        await self._cmd_upload(event)

    async def _cmd_upload(self, event: Message) -> None:
        await self.respond(event, "<code>Uploading image...</code>")
        now = datetime.datetime.now(datetime.UTC)

        media = self._extract_media(event)
        if not media:
            await self.respond(
                event,
                (
                    "<code>Reply to an image or send image with command.</code>\n"
                    "<code>Supported: JPEG, PNG, GIF, WEBP, BMP, ICO</code>"
                ),
            )
            return

        api_key = await self._get_api_key()
        if not api_key:
            await self.respond(
                event,
                "<code>You need to set ImgBB API key first: setimgbb_api {key}</code>",
            )
            return

        try:
            data = await event._client.download_media(media, in_memory=True)
            if not data:
                await self.respond(event, "<code>Failed to download image.</code>")
                return

            raw = self.to_bytes(data)
            if not raw:
                await self.respond(event, "<code>Downloaded file is empty.</code>")
                return

            file_name, mime = self._file_meta(event, media)
            files = {"image": (file_name, raw, mime)}
            resp = await self.client.http.post(
                BASE_URL,
                params={"key": api_key},
                files=files,
                timeout=60,
            )
            if resp.status_code != 200:
                raise RuntimeError(f"Upload failed: HTTP {resp.status_code}")

            payload = resp.json()
            if not payload.get("success", True):
                err = (payload.get("error") or payload.get("data") or "Unknown error")
                raise RuntimeError(f"ImgBB error: {err}")

            data = payload.get("data") or {}
            image_url = str(data.get("url") or "").strip()
            delete_url = str(data.get("delete_url") or "").strip()
            thumb_url = str(((data.get("thumb") or {}).get("url")) or image_url).strip()

            if not image_url:
                raise RuntimeError("Upload succeeded but no image URL returned.")

            links = [f'<a href="{image_url}">Image</a>']
            if thumb_url and thumb_url != image_url:
                links.append(f'<a href="{thumb_url}">Thumbnail</a>')
            if delete_url:
                links.append(f'<a href="{delete_url}">Delete</a>')

            await self.respond(
                event,
                self.fmtmsg(
                    "ImgBB Upload",
                    {"Links": " · ".join(links)},
                    self.fmtsec(now),
                ),
            )
        except Exception as e:
            await self.respond(
                event,
                f"<b>ImgBB failed</b>\n\n<code>{html.escape(str(e)[:300])}</code>",
            )

    async def _cmd_setkey(self, event: Message, text: str) -> None:
        await self.respond(event, "<code>Updating API key...</code>")
        match = SETKEY_PATTERN.match(text)
        value = (match.group(1) or "").strip()

        if not value:
            current = await self._get_api_key()
            if current:
                masked = f"{current[:4]}...{current[-4:]}" if len(current) > 8 else "***"
                await self.respond(
                    event,
                    f"<code>Current IMGBB API key: {html.escape(masked)}</code>",
                )
            else:
                await self.respond(
                    event,
                    "<code>No IMGBB API key configured.</code>",
                )
            return

        low = value.lower()
        if low in {"off", "none", "null", "disable", "clear", "del", "delete"}:
            await self.delvar("IMGBB_API_KEY")
            await self.client.db.imgbb_meta.update_one(
                {"_id": "config"},
                {"$unset": {"api_key": True}},
                upsert=True,
            )
            await self.respond(event, "<code>ImgBB API key cleared.</code>")
            return

        await self.setvar("IMGBB_API_KEY", value)
        await self.client.db.imgbb_meta.update_one(
            {"_id": "config"},
            {
                "$set": {
                    "api_key": value,
                    "updated_at": datetime.datetime.now(datetime.UTC),
                }
            },
            upsert=True,
        )
        await self.respond(event, "<code>ImgBB API key set successfully.</code>")

    async def _get_api_key(self) -> str | None:
        key = await self.getvar("IMGBB_API_KEY")
        if key:
            return str(key).strip()

        row = await self.client.db.imgbb_meta.find_one({"_id": "config"})
        if row and row.get("api_key"):
            legacy = str(row["api_key"]).strip()
            await self.setvar("IMGBB_API_KEY", legacy)
            return legacy
        return None

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
    def _file_meta(event: Message, media) -> tuple[str, str]:
        if getattr(media, "file_name", None):
            name = media.file_name
        else:
            ext = "jpg"
            mime = (getattr(media, "mime_type", None) or "").lower()
            if mime == "image/png":
                ext = "png"
            elif mime == "image/gif":
                ext = "gif"
            elif mime == "image/webp":
                ext = "webp"
            elif mime == "image/bmp":
                ext = "bmp"
            elif mime == "image/x-icon":
                ext = "ico"
            name = f"imgbb_{event.id}.{ext}"

        mime = (getattr(media, "mime_type", None) or "").lower()
        if not mime:
            if name.lower().endswith(".png"):
                mime = "image/png"
            elif name.lower().endswith(".gif"):
                mime = "image/gif"
            elif name.lower().endswith(".webp"):
                mime = "image/webp"
            elif name.lower().endswith(".bmp"):
                mime = "image/bmp"
            elif name.lower().endswith(".ico"):
                mime = "image/x-icon"
            else:
                mime = "image/jpeg"
        return name, mime
