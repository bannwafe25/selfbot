import base64
import datetime
import html
import re

from pyrogram import filters
from pyrogram.types import Message

from selfbot.listener import handler
from selfbot.module import Module

pattern = re.compile(r"^imgur(?:\s+)?$", re.IGNORECASE)
IMGUR_API_URL = "https://api.imgur.com/3/image"
DEFAULT_CLIENT_ID = "a10ad04550b0648"


class Imgur(Module):
    name = "Imgur"
    cmds = "<Reply to Photo/GIF> imgur"
    desc = {
        "Info": "Upload replied photo or GIF to Imgur.",
        "e.g.": "<Reply to Photo> imgur",
    }

    @handler(filters.regex(pattern), 1)
    async def on_message_out(self, event: Message) -> None:
        await self.respond(event, "<code>Uploading to Imgur...</code>")
        now = datetime.datetime.now(datetime.UTC)

        replied = event.reply_to_message
        if not replied:
            await self.respond(
                event,
                "<code>Please reply to a photo or animation (GIF).</code>",
            )
            return

        media = replied.photo or replied.animation
        if not media:
            await self.respond(
                event,
                "<code>Please reply to a photo or animation (GIF).</code>",
            )
            return

        try:
            data = await replied.download(in_memory=True)
            if not data:
                await self.respond(event, "<code>Failed to download media.</code>")
                return

            raw = self.to_bytes(data)
            if not raw:
                await self.respond(event, "<code>Downloaded media is empty.</code>")
                return

            image_b64 = base64.b64encode(raw).decode()
            client_id = await self.getvar("IMGUR_CLIENT_ID", DEFAULT_CLIENT_ID)
            headers = {"Authorization": f"Client-ID {client_id}"}

            resp = await self.client.http.post(
                IMGUR_API_URL,
                headers=headers,
                data={"image": image_b64},
                timeout=60,
            )
            if resp.status_code != 200:
                raise RuntimeError(f"Imgur API error: HTTP {resp.status_code}")

            payload = resp.json()
            if not payload.get("success"):
                msg = payload.get("data", {}).get("error") or payload.get("status") or "Unknown error"
                raise RuntimeError(f"Imgur upload failed: {msg}")

            link = ((payload.get("data") or {}).get("link") or "").strip()
            if not link:
                raise RuntimeError("Imgur upload succeeded but no link returned.")

            await self.respond(
                event,
                (
                    "<b>Imgur Upload</b>\n\n"
                    f"<a href=\"{html.escape(link)}\">{html.escape(link)}</a>\n\n"
                    f"<b><blockquote>{self.fmtsec(now)}</blockquote></b>"
                ),
            )
        except Exception as e:
            await self.respond(
                event,
                f"<b>Imgur failed</b>\n\n<code>{html.escape(str(e)[:300])}</code>",
            )
