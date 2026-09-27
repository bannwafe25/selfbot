from __future__ import annotations

import asyncio
import contextlib
import html
import os
import re
import urllib.parse
from io import BytesIO

import httpx

from pyrogram import filters
from pyrogram.types import InlineQuery, Message

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
    async def on_message_out(self, event: Message) -> None:
        text = (event.text or "").strip()
        m = url_pattern.search(text)
        if m:
            await self._download(event, m.group(0))
            return
        # bukan link → search via siputzx API
        m2 = re.match(r"^\.?pin\s+(?:(-d|--doc)\s+)?(.+)$", text, re.IGNORECASE)
        if not m2:
            await self.respond(
                event,
                "<b>Cara pakai:</b>\n"
                "<code>.pin https://pin.it/xxxx</code>\n"
                "<code>.pin &lt;query&gt;</code> — cari pin\n"
                "<code>.pin -d &lt;query&gt;</code> — kirim sebagai dokumen",
            )
            return
        await self._search(event, m2.group(2).strip(), as_doc=bool(m2.group(1)))

    @handler(filters.regex(r"^pinterest\b"), 2)
    async def on_inline_query(self, event) -> None:
        """Jawab inline query dengan slideshow rich (pola AnimePic)."""
        query = re.sub(r"^pinterest\s*", "", str(event.query or ""), flags=re.I).strip()
        try:
            if not query:
                await event.answer([], cache_time=0)
                return

            data = await self._api_search(query)
            pins = [x for x in (data.get("data") or []) if x.get("image_url")][:10]
            if not pins:
                await event.answer([], cache_time=0)
                return

            from pyrogram.enums import ButtonStyle
            from pyrogram.raw import functions as rawfn
            from pyrogram.raw.types import (
                InputBotInlineMessageRichMessage,
                InputBotInlineResult,
            )
            from pyrogram.types import (
                InputMediaPhoto,
                InputRichBlockButtons,
                InputRichBlockParagraph,
                InputRichBlockPhoto,
                InputRichBlockSlideshow,
                InputRichMessage,
                RichMessageButton,
                RichTextBold,
            )

            blobs = [b for b in await asyncio.gather(*(self._fetch_bytes(p["image_url"]) for p in pins)) if b]
            if not blobs:
                blobs = [BytesIO()]
            if len(blobs) > 1:
                media_block = InputRichBlockSlideshow(
                    blocks=[
                        InputRichBlockPhoto(photo=InputMediaPhoto(b)) for b in blobs
                    ]
                )
            else:
                media_block = InputRichBlockPhoto(
                    photo=InputMediaPhoto(blobs[0])
                )

            rich = InputRichMessage(
                blocks=[
                    media_block,
                    InputRichBlockParagraph(
                        text=self._build_caption_rich(pins[0])
                    ),
                    InputRichBlockButtons(
                        [
                            RichMessageButton(
                                text=RichTextBold("🔄 Cari Ulang"),
                                style=ButtonStyle.SUCCESS,
                                callback_data=b"pinterest/again",
                            ),
                            RichMessageButton(
                                text=RichTextBold("🗑 Close"),
                                style=ButtonStyle.DANGER,
                                callback_data=b"0",
                            ),
                        ]
                    ),
                ]
            )
            bot = self.client.bot
            rich_raw = await rich.write(client=bot, chat_id=bot.me.id)
            await bot.invoke(
                rawfn.messages.SetInlineBotResults(
                    query_id=int(event.id),
                    results=[
                        InputBotInlineResult(
                            id=str(event.id),
                            type="article",
                            title=f"Pinterest — {query[:30]}",
                            send_message=InputBotInlineMessageRichMessage(
                                rich_message=rich_raw,
                            ),
                        )
                    ],
                    cache_time=0,
                )
            )
        except Exception as e:
            self.logger.warning(f"pinterest inline failed: {e!r}")
            with contextlib.suppress(Exception):
                await event.answer([], cache_time=0)

    async def _search(self, event: Message, query: str, as_doc: bool = False) -> None:
        await self.respond(event, "<code>Mencari pin...</code>")
        try:
            data = await self._api_search(query)
        except Exception as e:
            self.logger.warning(f"pinterest search: {e!r}")
            await self.respond(event, "❌ <b>Gagal request API Pinterest.</b>")
            return

        pins = (data.get("data") or []) if data.get("status") else []
        pins = [x for x in pins if x.get("image_url")][:10]
        if not pins:
            await self.respond(
                event,
                "<blockquote>Tidak ada hasil untuk "
                f"<b>{html.escape(query[:60])}</b>.</blockquote>",
            )
            return

        await self.respond(
            event,
            f"<code>Menyiapkan {len(pins)} pin untuk "
            f"'{html.escape(query[:60])}'...</code>",
        )

        # ── Rich slideshow via bot (mirip AnimePic) ──
        try:
            await self._send_rich(event, pins, query)
            return
        except Exception as e:
            self.logger.warning(f"pinterest rich failed, fallback: {e!r}")

        # ── Fallback: kirim album foto biasa ──
        await self._send_album(event, pins)

    async def _fetch_bytes(self, url: str) -> BytesIO | None:
        """Download gambar ke memory (UploadMedia external URL sering ditolak)."""
        try:
            resp = await self.client.http.get(url, timeout=30)
            if resp.status_code != 200 or not resp.content:
                return None
            bio = BytesIO(resp.content)
            ext = ".png" if ".png" in url.lower().split("?")[0] else ".jpg"
            bio.name = f"pinterest_{abs(hash(url))}{ext}"
            bio.seek(0)
            return bio
        except Exception as e:
            self.logger.warning(f"pinterest download {url}: {e!r}")
            return None

    async def _api_search(self, query: str) -> dict:
        resp = await self.client.http.get(
            "https://api.siputzx.my.id/api/s/pinterest",
            params={"query": query},
            timeout=30,
        )
        return resp.json()

    def _build_caption_rich(self, pin: dict, query: str = "") -> list:
        from pyrogram.types.messages_and_media.rich_text import RichTextUrl

        parts: list = []
        title = (pin.get("grid_title") or "").strip()[:80]
        if title:
            parts.append(title)
            parts.append("\n")
        username = ((pin.get("pinner") or {}).get("username") or "").strip()
        if username:
            parts.append("Oleh: ")
            parts.append(username)
            parts.append(" | ")
        if pin.get("pin"):
            parts.append(RichTextUrl("Buka Pin", pin["pin"]))
            parts.append(" | ")
        return parts or [query]

    def _build_caption_html(self, pin: dict) -> str:
        title = (pin.get("grid_title") or "").strip()[:100]
        username = ((pin.get("pinner") or {}).get("username") or "").strip()
        out = "<b>📌 Pinterest</b>\n"
        if title:
            out += f"<blockquote>{html.escape(title)}</blockquote>\n"
        if username:
            out += f"<i>@{html.escape(username)}</i>\n"
        if pin.get("pin"):
            out += f'<a href="{html.escape(pin["pin"])}">Buka Pin</a>'
        return out

    async def _send_rich(self, event: Message, pins: list, query: str) -> None:
        """Kirim slideshow rich lewat inline bot, lalu hapus pesan asli."""
        res = await event._client.get_inline_bot_results(
            self.client.bot.me.id, f"pinterest {query}"[:64]
        )
        if not res.results:
            raise RuntimeError("bot returned no inline results")

        await event.reply_inline_bot_result(res.query_id, res.results[0].id)
        with contextlib.suppress(Exception):
            await event.delete()

    async def _send_album(self, event: Message, pins: list) -> None:
        from pyrogram.types import InputMediaPhoto

        blobs = await asyncio.gather(*(self._fetch_bytes(p["image_url"]) for p in pins))
        media = []
        i = 0
        for pin, blob in zip(pins, blobs):
            if not blob:
                continue
            media.append(
                InputMediaPhoto(
                    blob,
                    caption=self._build_caption_html(pin) if i == 0 else None,
                )
            )
            i += 1
        if not media:
            await self.respond(event, "<code>Gagal mengunduh semua pin.</code>")
            return
        await event.reply_media_group(media)
        with contextlib.suppress(Exception):
            await event.delete()

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
