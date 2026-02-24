import datetime
import html
import re
from io import BytesIO

from pyrogram import filters
from pyrogram.types import Message

from selfbot.listener import handler
from selfbot.module import Module
from selfbot.apis import DELINE_SCREENSHOT

pattern = re.compile(r"^ss(?:\s+([\s\S]+))?$", re.IGNORECASE)


class Screenshot(Module):
    name = "Web Screenshot"
    cmds = "ss {url}"
    desc = {
        "url": "Website URL to screenshot.",
        "e.g.": "ss https://google.com",
    }

    @handler(filters.regex(pattern), 1)
    async def on_message_out(self, event: Message) -> None:
        await self.respond(event, "<code>Processing...</code>")
        now = datetime.datetime.now(datetime.UTC)

        url = (pattern.match(str(event.content).strip()).group(1) or "").strip()
        if not url:
            if event.reply_to_message:
                url = self.message_text(event.reply_to_message).strip()

        if not url:
            await self.respond(
                event, "<code>Usage: ss {url} or reply to a message with a URL.</code>"
            )
            return

        # Auto-prepend https if no scheme
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"

        try:
            await self.respond(
                event, f"<code>Screenshotting {html.escape(url[:80])}...</code>"
            )
            resp = await self.client.http.get(
                DELINE_SCREENSHOT,
                params={"url": url},
                timeout=30,
            )
            if resp.status_code != 200:
                raise RuntimeError(f"API error: HTTP {resp.status_code}")

            content_type = resp.headers.get("content-type", "")
            if "image" not in content_type:
                raise RuntimeError("API did not return an image.")

            buf = BytesIO(resp.content)
            buf.name = "screenshot.png"
            buf.seek(0)

            await event.reply_photo(
                photo=buf,
                caption=(
                    f"<b>Screenshot</b>\n"
                    f"<blockquote>{html.escape(url[:200])}</blockquote>\n\n"
                    f"<b><blockquote>{self.fmtsec(now)}</blockquote></b>"
                ),
            )
            await event.delete()
        except Exception as e:
            await self.respond(
                event,
                f"<b>Screenshot failed</b>\n\n<code>{html.escape(str(e)[:300])}</code>",
            )
