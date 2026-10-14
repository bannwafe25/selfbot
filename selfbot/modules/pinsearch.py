import asyncio
import io
import re
import urllib.parse
import urllib.request

from pyrogram import filters
from pyrogram.enums import ChatAction
from pyrogram.types import InputMediaPhoto, InputMediaVideo, Message

from selfbot.listener import handler
from selfbot.module import Module

PIN_PATTERN = re.compile(
    r"^(?:[.,?!]?)?(?:(?:r)?pin|pinterest|pinslide)(?:\s+([\s\S]+))?$", re.IGNORECASE
)
PIN_API = "https://api.siputzx.my.id/api/s/pinterest?query={}"
MAX_MEDIA = 50  # batas media per request


def _fetch_json(query: str) -> list:
    url = PIN_API.format(urllib.parse.quote(query))
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        d = json.loads(r.read().decode("utf-8", "ignore"))
    return d.get("data", []) or []


def _download(url: str) -> bytes | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.read(30 * 1024 * 1024)
    except Exception:
        return None


import json


class PinSearch(Module):
    name = "PinSearch"
    cmds = ".pin <query> | .pin <query> <jumlah>"
    desc = {
        "info": "Cari gambar/video dari Pinterest (via API)",
        "cara_pakai": (
            "<code>.pin naruto wallpaper</code> — kirim 10 media\n"
            "<code>.pin kucing 15</code> — kirim 15 media\n"
            "Maksimal 20 media per request. Bisa dipakai di mana aja."
        ),
    }

    @handler(filters.regex(PIN_PATTERN), 1)
    async def on_message_out(self, event: Message) -> None:
        content = str(event.content).strip()
        # Rich slideshow: .rpin <query>
        rm = self.RPIN_PATTERN.match(content)
        if rm:
            return await self._rich_cmd(event, (rm.group(1) or "").strip())
        m = PIN_PATTERN.match(content)
        if not m or not m.group(1):
            return await event.edit("<b>Format:</b> <code>.pin &lt;query&gt; [jumlah]</code>")
        parts = m.group(1).rsplit(maxsplit=1)
        limit = 20
        query = m.group(1).strip()
        if len(parts) == 2 and parts[1].isdigit():
            query, limit = parts[0], min(int(parts[1]), MAX_MEDIA)

        status = await event.edit(f"<code>Mencari Pinterest: {query}…</code>")
        await self.client.app.send_chat_action(event.chat.id, ChatAction.UPLOAD_PHOTO)

        try:
            items = await asyncio.get_event_loop().run_in_executor(
                None, _fetch_json, query
            )
        except Exception as e:
            return await status.edit(f"<b>Pinterest API gagal:</b> <code>{e}</code>")

        if not items:
            return await status.edit("<b>Gak ada hasil.</b>")

        media_group = []
        foto = video = 0
        for v in items[:limit]:
            vurl = v.get("video_url")
            iurl = v.get("image_url")
            if vurl:
                data = await asyncio.get_event_loop().run_in_executor(None, _download, vurl)
                if data:
                    media_group.append(InputMediaVideo(media=io.BytesIO(data)))
                    video += 1
            elif iurl:
                data = await asyncio.get_event_loop().run_in_executor(None, _download, iurl)
                if data:
                    media_group.append(InputMediaPhoto(media=io.BytesIO(data)))
                    foto += 1

        if not media_group:
            return await status.edit("<b>Gak ada media yang bisa di-download.</b>")

        await status.delete()
        err = ""
        # Telegram max 10 media per album
        for i in range(0, len(media_group), 10):
            chunk = media_group[i:i + 10]
            try:
                await self.client.app.send_media_group(
                    event.chat.id, media=chunk,
                    reply_parameters=getattr(event, "id", None) and
                        {"message_id": event.id} if event.reply_to_message else None,
                )
            except Exception as e:
                err += f"\n❌ chunk {i//10+1}: <code>{str(e)[:80]}</code>"
        await event.reply(
            f"<b>✅ {len(media_group)} media terkirim</b>\n"
            f"📸 Foto: <code>{foto}</code> | 🎥 Video: <code>{video}</code>"
            f"{err}"
        )

    # ------------------------------------------------------
    # Rich slideshow: .rpin <query> → kartu geser + tombol
    # ------------------------------------------------------

    async def _rich_cmd(self, event: Message, query: str) -> None:
        if not query:
            return await event.edit("<b>Format:</b> <code>.rpin &lt;query&gt;</code>")
        status = await event.edit(f"<code>Membuat slideshow: {query}…</code>")
        try:
            items = await asyncio.get_event_loop().run_in_executor(
                None, _fetch_json, query
            )
        except Exception as e:
            return await status.edit(f"<b>API gagal:</b> <code>{e}</code>")
        urls = []
        for v in items:
            u = v.get("image_url")
            if u and u.lower().endswith((".jpg", ".jpeg", ".png")) and "i.pinimg.com" in u:
                urls.append(u)
        urls = urls[:10]
        if len(urls) < 2:
            return await status.edit("<b>Hasil foto terlalu sedikit buat slideshow.</b>")
        await status.delete()
        await self._send_rich_slideshow(event, query, urls)

    RPIN_PATTERN = re.compile(r"^(?:[.,?!]?)?(?:rpin|pinslide)(?:\s+([\s\S]+))?$", re.IGNORECASE)

    async def _send_rich_slideshow(self, event: Message, query: str, urls: list) -> None:
        import datetime as _dt
        try:
            bot = self.client.bot
            from pyrogram.raw import functions as rawfn
            from pyrogram.raw.types import (
                InputBotInlineMessageRichMessage,
                InputBotInlineResult,
                InputBotInlineMessageMediaAuto,
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
            from pyrogram.enums import ButtonStyle
            import richpyro as rp

            def build_rich(u: list) -> InputRichMessage:
                return InputRichMessage(
                    blocks=[
                        InputRichBlockSlideshow(
                            blocks=[InputRichBlockPhoto(photo=InputMediaPhoto(x)) for x in u]
                        ),
                        InputRichBlockParagraph(
                            text=[RichTextBold(f"📌 Pinterest — {query}")]
                        ),
                        InputRichBlockButtons(
                            [
                                RichMessageButton(
                                    text=RichTextBold(" Refresh"),
                                    style=ButtonStyle.SUCCESS,
                                    callback_data=f"pinsearch/next/{query}".encode(),
                                ),
                                RichMessageButton(
                                    text=RichTextBold(" Tutup"),
                                    style=ButtonStyle.DANGER,
                                    callback_data=b"0",
                                ),
                            ]
                        ),
                    ]
                )

            # Jawab inline query asli dari userbot
            res = await self.client.app.get_inline_bot_results(
                bot.me.id, f"rpin{_dt.datetime.now(_dt.UTC).timestamp()}"
            )
            # Register rich payload via bot SetInlineBotResults gak bisa tanpa query_id asli;
            # gunakan mekanisme Music rich route (shared handler) bila tersedia, else fallback HTML.
            ping_mod = None
            try:
                ping_mod = self.client.modules.get("Ping")
            except Exception:
                pass
            if ping_mod is None:
                raise RuntimeError("rich route (Ping) gak tersedia")
            rich_raw = await build_rich(urls).write(client=bot, chat_id=bot.me.id)
            self._ensure_rich_handler(
                ping_mod, rawfn, InputBotInlineMessageRichMessage, InputBotInlineResult
            )
            if getattr(ping_mod, "_rich_route", None) is None:
                ping_mod._rich_route = {}
            self._pin_route = {"query": query, "urls": urls}
            ping_mod._rich_route["rpin"] = (rich_raw, None)
            msg = await self.client.app.send_inline_bot_result(
                event.chat.id, res.query_id, res.results[0].id
            )
            if msg:
                self.np_msg = msg
        except Exception as e:
            self.logger.warning(f"rpin rich gagal: {e!r}")
            with contextlib.suppress(Exception):
                await event.reply(f"<b>Slideshow gagal:</b> <code>{str(e)[:100]}</code>\nFallback: <code>.pin {query}</code>")

    @handler(filters.regex(r"^pinsearch/next/(.+)$"), 4)
    async def on_inline_callback(self, event) -> None:
        (query,) = event.matches[0].groups()
        try:
            await event.answer("Refresh…")
            items = await asyncio.get_event_loop().run_in_executor(
                None, _fetch_json, query
            )
            urls = []
            for v in items:
                u = v.get("image_url")
                if u and u.lower().endswith((".jpg", ".jpeg", ".png")) and "i.pinimg.com" in u:
                    urls.append(u)
            import random
            urls = random.sample(urls, min(10, len(urls))) if len(urls) > 10 else urls
            await self._send_rich_slideshow(event.message if hasattr(event, "message") else event, query, urls)
        except Exception as e:
            self.logger.warning(f"rpin refresh gagal: {e!r}")
