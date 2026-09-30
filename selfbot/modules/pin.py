import asyncio
import contextlib
import datetime
import html
import io
import json
import os
import re
import tempfile

import httpx
from pyrogram import filters
from pyrogram.types import InputMediaPhoto, Message, ReplyParameters

from selfbot.listener import handler
from selfbot.module import Module

# .pin {query} — cari gambar via Bing Images (Pinterest diblok 403)
pattern = re.compile(r"^\.?(pin|pinterest|img)(?:\s+([\s\S]+))?$", re.IGNORECASE)

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0 Safari/537.36"
)


def _search(query: str, limit: int = 6) -> list[dict]:
    """Scrape Bing Images → [{murl, turl, t, purl}] — sync, jalankan di executor."""
    with httpx.Client(
        headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"},
        follow_redirects=True,
        timeout=25,
    ) as c:
        r = c.get(
            "https://www.bing.com/images/search",
            params={"q": query, "form": "HDRSC2", "first": "1"},
        )
        items = re.findall(r'm="({.*?})"', r.text)
        out = []
        for it in items:
            try:
                j = json.loads(
                    it.replace("&quot;", '"').replace("&amp;", "&")
                )
            except Exception:
                continue
            if j.get("murl") and j.get("turl"):
                out.append(
                    {
                        "murl": j["murl"],  # full image
                        "turl": j["turl"],  # thumbnail
                        "t": (j.get("t") or "")[:120],
                        "purl": j.get("purl", ""),
                    }
                )
            if len(out) >= limit:
                break
        return out


async def _fetch_bytes(client: httpx.AsyncClient, url: str, *, thumb=False):
    headers = {"User-Agent": UA}
    if thumb:
        headers["Referer"] = "https://www.bing.com/"
    r = await client.get(url, headers=headers, timeout=20)
    if r.status_code == 200 and r.content:
        return r.content
    return None


class Pin(Module):
    name = "Image Search"
    cmds = ".pin {query}"
    desc = {
        "query": "Cari gambar di web via Bing Images (pengganti Pinterest, 403).",
        "Note": "Kirim 1-6 foto sebagai album + judul. .img = alias.",
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

        status = await self.respond(event, "<code>🔍 Mencari gambar...</code>")
        now = datetime.datetime.now(datetime.UTC)
        loop = asyncio.get_running_loop()

        try:
            results = await loop.run_in_executor(None, _search, query)
        except Exception as e:
            await self.respond(event, f"<b>Search gagal:</b> <code>{html.escape(str(e)[:150])}</code>")
            return
        if not results:
            with contextlib.suppress(Exception):
                await status.edit("<b>Gak ketemu.</b> Coba query lain.")
            return

        # download foto (murl dulu, fallback turl)
        media = []
        async with httpx.AsyncClient(follow_redirects=True) as hc:
            for r in results[:6]:
                data = await _fetch_bytes(hc, r["murl"]) or await _fetch_bytes(
                    hc, r["turl"], thumb=True
                )
                if not data:
                    continue
                with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
                    f.write(data)
                    media.append((f.name, r["t"]))

        if not media:
            with contextlib.suppress(Exception):
                await status.edit("<b>Gagal download gambar.</b>")
            return

        with contextlib.suppress(Exception):
            await status.delete()

        cap = (
            f"<b>🖼 {html.escape(query[:80])}</b>\n"
            f"<i>{len(media)} hasil · Bing Images</i>\n\n"
            f"<b><blockquote>{self.fmtsec(now)}</blockquote></b>"
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

        # album — tiap foto caption judul, foto pertama caption header
        group = []
        for i, (path, title) in enumerate(media):
            group.append(
                InputMediaPhoto(
                    path,
                    caption=cap if i == 0 else html.escape(title or "​"),
                )
            )
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
