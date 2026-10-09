import html
import re
import xml.etree.ElementTree as ET

import httpx
from pyrogram import filters
from pyrogram.types import Message

from selfbot.listener import handler
from selfbot.module import Module

pattern = re.compile(
    r"^news(?:\s+(cnn|cnbc|kumparan))?(?:\s+(\d+))?\s*$",
    re.IGNORECASE,
)

FEEDS = {
    "cnn": "https://www.cnnindonesia.com/rss",
    "cnbc": "https://www.cnbcindonesia.com/rss",
    "kumparan": "https://lapi.kumparan.com/v2.0/rss/",
}


class News(Module):
    name = "News"
    cmds = "news {cnn|cnbc|kumparan}? {jumlah}?"
    desc = {
        "sumber": "cnn / cnbc / kumparan (default: cnn)",
        "jumlah": "berapa berita (default 5, max 10)",
        "e.g.": "news cnbc 5",
    }

    @handler(filters.regex(pattern), 1)
    async def on_message_out(self, event: Message) -> None:
        m = pattern.match(str(event.content).strip())
        source, count = m.group(2) or "cnn", int(m.group(3) or 5)
        count = min(count, 10)

        await self.respond(event, "<code>Mengambil berita...</code>")
        try:
            items = await self._fetch(FEEDS[source])
        except Exception as e:
            await self.respond(
                event, f"<b>News gagal</b>\n\n<code>{html.escape(str(e)[:200])}</code>"
            )
            return

        if not items:
            await self.respond(event, "<code>Feed kosong.</code>")
            return

        lines = [
            f"📰 <b>{html.escape(t)}</b>\n{link}"
            for t, link in items[:count]
        ]
        await self.respond(
            event,
            f"<b>📱 {source.upper()} — Terbaru</b>\n\n" + "\n\n".join(lines),
        )

    async def _fetch(self, url: str) -> list[tuple[str, str]]:
        async with httpx.AsyncClient(
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
            timeout=15,
            follow_redirects=True,
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()

        root = ET.fromstring(resp.text)
        items = []
        for item in root.iter("item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            if title and link:
                items.append((title, link))
        return items
