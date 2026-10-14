import asyncio
import contextlib
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
