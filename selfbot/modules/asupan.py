import datetime
import html
import re
from io import BytesIO

from pyrogram import filters
from pyrogram.types import Message

from selfbot.listener import handler
from selfbot.module import Module
from selfbot.apis import DELINE_ASUPAN

pattern = re.compile(r"^asupan(?:\s+)?$", re.IGNORECASE)


class Asupan(Module):
    name = "Asupan"
    cmds = "asupan"
    desc = {
        "Info": "Get random asupan video.",
        "e.g.": "asupan",
    }

    @handler(filters.regex(pattern), 1)
    async def on_message_out(self, event: Message) -> None:
        await self.respond(event, "<code>Fetching asupan...</code>")
        now = datetime.datetime.now(datetime.UTC)

        try:
            resp = await self.client.http.get(DELINE_ASUPAN, timeout=60)
            if resp.status_code != 200:
                raise RuntimeError(f"API error: HTTP {resp.status_code}")

            disposition = resp.headers.get("content-disposition", "")
            filename = "asupan.mp4"
            if 'filename="' in disposition:
                filename = disposition.split('filename="')[1].split('"')[0]

            video = BytesIO(resp.content)
            video.name = filename
            video.seek(0)

            await event.reply_video(
                video=video,
                caption=f"<b><blockquote>{self.fmtsec(now)}</blockquote></b>",
            )
            await event.delete()
        except Exception as e:
            await self.respond(
                event,
                f"<b>Asupan failed</b>\n\n<code>{html.escape(str(e)[:300])}</code>",
            )
