import datetime
import html
import random
import re

from pyrogram import filters
from pyrogram.types import Message

from selfbot.listener import handler
from selfbot.module import Module
from selfbot.apis import FERDEV_ANIMEQUOTE, FERDEV_APIKEY

pattern = re.compile(r"^animequote(?:\s+)?$", re.IGNORECASE)


class AnimeQuote(Module):
    name = "Anime Quote"
    cmds = "animequote"
    desc = {
        "Info": "Get random anime quote.",
        "e.g.": "animequote",
    }

    @handler(filters.regex(pattern), 1)
    async def on_message_out(self, event: Message) -> None:
        await self.respond(event, "<code>Fetching quote...</code>")
        now = datetime.datetime.now(datetime.UTC)

        try:
            resp = await self.client.http.get(
                FERDEV_ANIMEQUOTE,
                params={"apikey": FERDEV_APIKEY},
                timeout=15,
            )
            if resp.status_code != 200:
                raise RuntimeError(f"API error: HTTP {resp.status_code}")

            data = resp.json()
            results = data.get("result", [])
            if not results:
                raise RuntimeError("No quotes returned.")

            q = random.choice(results)
            quote = html.escape(q.get("quote", ""))
            char = html.escape(q.get("character", "Unknown"))
            anime = html.escape(q.get("anime", "Unknown"))
            episode = html.escape(q.get("episode", ""))

            ep_text = f" • {episode}" if episode else ""
            text = (
                f"<b>Anime Quote</b>\n\n"
                f"<blockquote><i>\"{quote}\"</i></blockquote>\n\n"
                f"— <b>{char}</b>\n"
                f"<code>{anime}{ep_text}</code>\n\n"
                f"<b><blockquote>{self.fmtsec(now)}</blockquote></b>"
            )

            await self.respond(event, text)
        except Exception as e:
            await self.respond(
                event,
                f"<b>AnimeQuote failed</b>\n\n<code>{html.escape(str(e)[:300])}</code>",
            )
