import asyncio
import contextlib
import datetime
import html
import os
import re
import tempfile

import httpx
from pyrogram import filters
from pyrogram.types import InputMediaPhoto, Message, ReplyParameters

from selfbot.listener import handler
from selfbot.module import Module

# .pin {query} — cari gambar Pinterest via api.siputzx.my.id
pattern = re.compile(r"^\.?(pin|pinterest|img)(?:\s+([\s\S]+))?$", re.IGNORECASE)

API = "https://api.siputzx.my.id/api/s/pinterest"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0 Safari/537.36"
)


async def _search(client: httpx.AsyncClient, query: str, limit: int = 6) -> list[dict]:
    r = await client.get(API, params={"query": query}, timeout=30)
    r.raise_for_status()
    data = r.json()
    if not data.get("status"):
        return []
    out = []
    for p in data.get("data", []):
        url = p.get("image_url") or ""
        if not url or url.endswith(".mp4"):
            continue
        out.append(
            {
                "img": url,
                "title": (p.get("grid_title") or p.get("description") or "").strip()[:120],
                "pin": p.get("pin") or "",
            }
        )
        if len(out) >= limit:
            break
    return out


async def _dl(client: httpx.AsyncClient, url: str):
    r = await client.get(url, headers={"User-Agent": UA}, timeout=25)
    if r.status_code == 200 and r.content:
        ext = ".png" if ".png" in url else ".jpg"
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as f:
            f.write(r.content)
            return f.name
    return None


class Pin(Module):
    name = "Pinterest"
    cmds = ".pin {query}"
    desc = {
        "query": "Cari foto Pinterest via api.siputzx.my.id, album 6 foto.",
        "e.g.": ".pin wallpaper anime 4k",
    }

    @handler(filters.regex(pattern) & filters.outgoing, 1)
    async def on_message_out(self, event: Message) -> None:
        match = pattern.match(event.text or "")
        if not match:
            return
        query = (match.group(2) or "").strip()
        if not query:
            await self.respond(event, "<b>Cara pakai:</b> <code>.pin {query}</code>")
            return

        status = await self.respond(event, "<code>📌 Mencari di Pinterest...</code>")
        now = datetime.datetime.now(datetime.UTC)

        try:
            async with httpx.AsyncClient(follow_redirects=True) as hc:
                results = await _search(hc, query)
        except Exception as e:
            await self.respond(event, f"<b>API gagal:</b> <code>{html.escape(str(e)[:150])}</code>")
            return
        if not results:
            with contextlib.suppress(Exception):
                await status.edit("<b>Gak ketemu.</b> Coba query lain.")
            return

        media = []
        async with httpx.AsyncClient(follow_redirects=True) as hc:
            for r in results:
                path = await _dl(hc, r["img"])
                if path:
                    media.append((path, r["title"]))

        if not media:
            with contextlib.suppress(Exception):
                await status.edit("<b>Gagal download gambar.</b>")
            return

        with contextlib.suppress(Exception):
            await status.delete()

        cap = (
            f"<b>📌 Pinterest — {html.escape(query[:80])}</b>\n"
            f"<i>{len(media)} hasil</i>\n\n"
            f"<b><blockquote>{now.strftime('%d %b %Y · %H:%M')}</blockquote></b>"
        )

        if len(media) == 1:
            path, _ = media[0]
            try:
                await event._client.send_photo(
                    event.chat.id, path, caption=cap,
                    reply_parameters=ReplyParameters(message_id=event.id),
                )
            finally:
                with contextlib.suppress(OSError):
                    os.remove(path)
            with contextlib.suppress(Exception):
                await event.delete()
            return

        group = [
            InputMediaPhoto(path, caption=cap if i == 0 else html.escape(title or "​"))
            for i, (path, title) in enumerate(media)
        ]
        try:
            await event._client.send_media_group(
                event.chat.id, group,
                reply_parameters=ReplyParameters(message_id=event.id),
            )
        except Exception:
            # fallback: kirim satu-satu kalau album ditolak
            for i, (path, title) in enumerate(media[:3]):
                with contextlib.suppress(Exception):
                    await event._client.send_photo(
                        event.chat.id, path,
                        caption=cap if i == 0 else html.escape(title or "​"),
                        reply_parameters=ReplyParameters(message_id=event.id),
                    )
                await asyncio.sleep(1)
        finally:
            for path, _ in media:
                with contextlib.suppress(OSError):
                    os.remove(path)
            with contextlib.suppress(Exception):
                await event.delete()
