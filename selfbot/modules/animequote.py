import datetime
import html
import random
import re

from pyrogram import filters
from pyrogram.types import Message

from selfbot.listener import handler
from selfbot.module import Module

ANIMECHAN_RANDOM = "https://api.animechan.io/v1/quotes/random"

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
            resp = await self.client.http.get(ANIMECHAN_RANDOM, timeout=15)
            if resp.status_code != 200:
                raise RuntimeError(f"API error: HTTP {resp.status_code}")

            data = (resp.json() or {}).get("data") or {}
            quote = html.unescape(data.get("content", ""))
            char = html.unescape((data.get("character") or {}).get("name", "Unknown"))
            anime = html.unescape((data.get("anime") or {}).get("name", "Unknown"))
            episode = ""

            ep_text = f" • {episode}" if episode else ""
            rich_rows = [
                ("Karakter", f"— {char}"),
                ("Anime", f"{anime}{ep_text}"),
                ("Waktu", self.fmtsec(now)),
            ]
            if await self.send_rich(
                event,
                "📖 Anime Quote",
                rich_rows,
                note=f"“{quote}”",
                query_prefix="animequote",
            ):
                return

            text = (
                f"<b>Anime Quote</b>\n\n"
                f"<blockquote><i>\"{html.escape(quote)}\"</i></blockquote>\n\n"
                f"— <b>{char}</b>\n"
                f"<code>{html.escape(anime)}{html.escape(ep_text)}</code>\n\n"
                f"<b><blockquote>{self.fmtsec(now)}</blockquote></b>"
            )

            await self.respond(event, text)
        except Exception as e:
            await self.respond(
                event,
                f"<b>AnimeQuote failed</b>\n\n<code>{html.escape(str(e)[:300])}</code>",
            )
