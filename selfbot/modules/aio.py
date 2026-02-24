import contextlib
import datetime
import html
import re
from io import BytesIO
from pathlib import Path

from pyrogram import filters
from pyrogram.types import Message, ReplyParameters

from selfbot.listener import handler
from selfbot.module import Module
from selfbot.apis import CHOCOMILK_AIO

pattern = re.compile(r"^aio(?:\s+([\s\S]+))?$", re.IGNORECASE)


class AIO(Module):
    name = "AIO Downloader"
    cmds = "aio {url}"
    desc = {
        "url": "Link from TikTok, Instagram, Facebook, Twitter, etc.",
        "e.g.": "aio https://vt.tiktok.com/...",
    }

    @handler(filters.regex(pattern), 1)
    async def on_message_out(self, event: Message) -> None:
        await self.respond(event, "<code>Processing...</code>")
        now = datetime.datetime.now(datetime.UTC)

        url = (pattern.match(str(event.content).strip()).group(1) or "").strip()
        if not url:
            if event.reply_to_message:
                url = self.message_text(event.reply_to_message).strip()

        if not url or not url.startswith("http"):
            await self.respond(
                event,
                "<code>Usage: aio {url} or reply to a message with a link.</code>",
            )
            return

        try:
            await self.respond(event, "<code>Fetching media...</code>")
            resp = await self.client.http.get(
                CHOCOMILK_AIO,
                params={"url": url},
                timeout=60,
            )
            if resp.status_code != 200:
                raise RuntimeError(f"API error: HTTP {resp.status_code}")

            data = resp.json()
            if not data.get("success"):
                err = data.get("error") or "API returned an error."
                raise RuntimeError(str(err))

            result = data.get("data") or {}
            medias = result.get("medias") or []
            if not medias:
                raise RuntimeError("No downloadable media found.")

            source = html.escape(str(result.get("source", "unknown")))
            title = html.escape(str(result.get("title", ""))[:100])

            # Pick the best media: prefer HD video, fallback to first video, then first anything
            media = self._pick_best(medias)
            media_url = media["url"]
            media_type = media.get("type", "video")
            ext = media.get("extension", "mp4")
            quality = media.get("quality", "")

            await self.respond(event, f"<code>Downloading {source} media...</code>")
            dl_resp = await self.client.http.get(media_url, timeout=300)
            if dl_resp.status_code != 200:
                raise RuntimeError(f"Download failed: HTTP {dl_resp.status_code}")

            buf = BytesIO(dl_resp.content)
            buf.name = f"aio.{ext}"
            buf.seek(0)

            caption = f"<b>{source}</b>"
            if title and title != "Unknown":
                caption += f"\n<blockquote>{title}</blockquote>"
            if quality:
                caption += f"\n<code>{html.escape(quality)}</code>"
            caption += f"\n\n<b><blockquote>{self.fmtsec(now)}</blockquote></b>"

            reply_id = event.reply_to_message_id or event.id
            reply_params = ReplyParameters(message_id=reply_id)

            if media_type == "audio":
                await event._client.send_audio(
                    chat_id=event.chat.id,
                    audio=buf,
                    caption=caption,
                    reply_parameters=reply_params,
                )
            elif media_type == "image":
                await event._client.send_photo(
                    chat_id=event.chat.id,
                    photo=buf,
                    caption=caption,
                    reply_parameters=reply_params,
                )
            else:
                await event._client.send_video(
                    chat_id=event.chat.id,
                    video=buf,
                    caption=caption,
                    reply_parameters=reply_params,
                )

            await event.delete()
        except Exception as e:
            await self.respond(
                event,
                f"<b>AIO failed</b>\n\n<code>{html.escape(str(e)[:300])}</code>",
            )

    @staticmethod
    def _pick_best(medias: list[dict]) -> dict:
        # Prefer HD no-watermark video
        for m in medias:
            q = (m.get("quality") or "").lower()
            if m.get("type") == "video" and "hd" in q and "watermark" not in q:
                return m

        # Then any no-watermark video
        for m in medias:
            q = (m.get("quality") or "").lower()
            if m.get("type") == "video" and "watermark" not in q:
                return m

        # Then any video
        for m in medias:
            if m.get("type") == "video":
                return m

        # Fallback: first media
        return medias[0]
