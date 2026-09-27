from __future__ import annotations

import contextlib
import os
import re
import urllib.parse

import httpx

from pyrogram import filters
from pyrogram.types import Message

from selfbot.listener import handler
from selfbot.module import Module

# link pin: pinterest.com/pin/xxx, pin.it/xxx, id.pinterest.com/..., pin short
url_pattern = re.compile(
    r"https?://(?:[a-z]{2}\.)?(?:pinterest\.com/pin/[\w\-]+"
    r"|pinterest\.com/pin/\d+"
    r"|pin\.it/[\w\-]+)/?\S*",
    re.IGNORECASE,
)

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


class Pinterest(Module):
    name = "Pinterest"
    cmds = ".pin {url}"
    desc = {
        "url": "Link pin Pinterest (pinterest.com/pin/... atau pin.it/...)",
        "note": "Kirim gambar kalau foto, kirim video kalau video.",
        "e.g.": ".pin https://pin.it/xxxx",
    }

    @handler(filters.regex(r"^\.?pin\b") & filters.outgoing, 1)
    async def on_cmd(self, event: Message) -> None:
        text = (event.text or "").strip()
        m = url_pattern.search(text)
        if not m:
            await self.respond(
                event,
                "<b>Cara pakai:</b>\n"
                "<code>.pin https://pin.it/xxxx</code>\n"
                "<code>.pin https://pinterest.com/pin/xxxx</code>",
            )
            return
        await self._download(event, m.group(0))

    @handler(filters.regex(url_pattern) & filters.outgoing, 2)
    async def on_url(self, event: Message) -> None:
        """Auto-detect: link pinterest dikirim tanpa command."""
        m = url_pattern.search(str(event.content or ""))
        if not m:
            return
        await self._download(event, m.group(0))

    # ---------- core ----------
    async def _download(self, event: Message, url: str) -> None:
        msg = await self.respond(event, "<code>Mengambil pin...</code>")

        # 1) coba yt-dlp (paling andal kalau jalan)
        res = await self._via_ytdlp(url)
        # 2) fallback scraping og / __PWS_INITIAL_PROPS__
        if not res:
            res = await self._via_scrape(url)

        if not res:
            await msg.edit_text(
                "❌ <b>Gagal mengambil pin</b>\n"
                "<blockquote>Pinterest kemungkinan blokir request dari server, "
                "atau pin-nya privat/ga ada.</blockquote>"
            )
            return

        media_url, is_video, title = res
        try:
            await msg.edit_text("<code>Mengunduh media...</code>")
            async with httpx.AsyncClient(
                timeout=90, follow_redirects=True, headers={"User-Agent": UA}
            ) as c:
                r = await c.get(media_url)
                r.raise_for_status()
                data = r.content

            ext = ".mp4" if is_video else self._ext(media_url)
            path = f"/tmp/pin_{abs(hash(media_url))}{ext}"
            with open(path, "wb") as f:
                f.write(data)

            cap = f"<b>📌 Pinterest</b>\n<blockquote>{title or '-'}</blockquote>"[:900]
            try:
                if is_video:
                    await event.reply_video(path, caption=cap)
                else:
                    await event.reply_photo(path, caption=cap)
            finally:
                with contextlib.suppress(Exception):
                    os.remove(path)
                    await msg.delete()
        except Exception as e:
            with contextlib.suppress(Exception):
                await msg.edit_text(
                    f"❌ <b>Gagal kirim media</b>\n<blockquote>{e}</blockquote>"
                )

    async def _via_ytdlp(self, url: str):
        import asyncio

        def _run():
            import yt_dlp

            opts = {
                "quiet": True,
                "no_warnings": True,
                "simulate": True,
                "noplaylist": True,
            }
            with yt_dlp.YoutubeDL(opts) as y:
                return y.extract_info(url, download=False)

        try:
            info = await asyncio.to_thread(_run)
        except Exception as e:
            self.logger.warning(f"pinterest ytdlp: {e!r}")
            return None
        if not info:
            return None

        # cari url terbaik
        media = info.get("url")
        if not media:
            for f in reversed(info.get("formats") or []):
                if f.get("url"):
                    media = f["url"]
                    break
        if not media:
            return None
        return (media, info.get("vcodec") not in (None, "none"), info.get("title"))

    async def _via_scrape(self, url: str):
        """Ambil gambar/video langsung dari HTML pin."""
        try:
            async with httpx.AsyncClient(
                timeout=40, follow_redirects=True, headers={"User-Agent": UA}
            ) as c:
                r = await c.get(url)
            if r.status_code != 200:
                return None
            t = r.text

            title = None
            for pat in (
                r'"og:title"\s*:\s*"([^"]+)"',
                r'property="og:title"\s+content="([^"]+)"',
                r"<title>([^<]+)</title>",
            ):
                m = re.search(pat, t)
                if m:
                    title = m.group(1)[:120]
                    break

            # video dulu (prioritas)
            for pat in (
                r"https://v\d*\.pinimg\.com/videos/[^\\\"\s]+?\.mp4",
                r'https://[^"\\ ]*\.mp4[^"\\ ]*',
            ):
                vids = re.findall(pat, t)
                if vids:
                    v = vids[0].replace("\\/", "/")
                    if "pinimg.com" in v:
                        return (v, True, title)

            # gambar: cari di __PWS_INITIAL_PROPS__ dulu (paling valid)
            m = re.search(
                r'<script[^>]+id="__PWS_INITIAL_PROPS__"[^>]*>(.*?)</script>',
                t,
                re.S,
            )
            blob = m.group(1) if m else t
            imgs = re.findall(
                r"https://i\.pinimg\.com/(?:originals|736x|564x)/"
                r"[a-f0-9]{2}/[a-f0-9]{2}/[a-f0-9]{2}/[a-f0-9]+\."
                r"(?:jpg|jpeg|png|webp|gif)",
                blob,
            )
            if imgs:
                return (imgs[0], False, title)

            # terakhir: og:image
            for pat in (
                r'property="og:image"\s+content="([^"]+)"',
                r'content="([^"]+)"\s+property="og:image"',
                r'"og:image"\s*:\s*"([^"]+)"',
            ):
                m = re.search(pat, t)
                if m and "pinimg" in m.group(1):
                    return (m.group(1), False, title)
            return None
        except Exception as e:
            self.logger.warning(f"pinterest scrape: {e!r}")
            return None

    @staticmethod
    def _ext(url: str) -> str:
        path = urllib.parse.urlparse(url).path.lower()
        for e in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".mp4"):
            if path.endswith(e):
                return ".jpg" if e == ".jpeg" else e
        return ".jpg"
