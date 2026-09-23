import asyncio
import base64
import html
import random
import re

import httpx
from pyrogram import filters
from pyrogram.types import Message

from selfbot.listener import handler
from selfbot.module import Module

QUOTE_APIS = [
    "https://quote.yuri.ly/generate",
    "https://bot.lyo.su/quote/generate",
]

COLOR_NAMES = {
    "red": "#ff2b2b", "blue": "#3b82f6", "green": "#22c55e", "yellow": "#facc15",
    "orange": "#f97316", "purple": "#a855f7", "pink": "#ec4899", "black": "#111111",
    "white": "#ffffff", "gray": "#6b7280", "grey": "#6b7280", "teal": "#14b8a6",
}

PATTERN = re.compile(
    r"^(?:q|quotly)(?:\s+(\S+))?(?:\s+(\d+))?\s*$", re.IGNORECASE
)


def _pick_color(arg: str | None) -> str:
    if not arg:
        return random.choice(
            ["#1b1429", "#2d1b3d", "#0f2027", "#3a1c71", "#16222a", "#41295a"]
        )
    arg = arg.lower().lstrip("#")
    if arg in COLOR_NAMES:
        return COLOR_NAMES[arg]
    if re.fullmatch(r"[0-9a-f]{6}", arg):
        return f"#{arg}"
    return random.choice(["#1b1429", "#2d1b3d", "#0f2027"])


class Quotly(Module):
    name = "Quotly"
    cmds = "q [color] [count]"
    desc = {
        "q": "Reply ke pesan — bikin quote stiker via quote-api (LyoSU).",
        "color": "Nama warna atau hex (opsional).",
        "count": "Jumlah pesan 1-10 (opsional).",
        "e.g.": "<Reply> q red 3",
    }

    async def _build_message_payload(self, msg: Message) -> dict | None:
        sender = msg.from_user
        if sender is None:
            chat = msg.chat
            sender_id = chat.id if chat else 1
            sender_name = chat.title if chat else "Unknown"
        else:
            sender_id = sender.id
            sender_name = " ".join(
                filter(None, [sender.first_name, sender.last_name])
            ) or "Unknown"

        avatar_url = None
        if sender is not None:
            try:
                photo = await self.client.app.download_memory(
                    sender_id, in_memory=True
                )
                import base64 as _b64
                avatar_url = (
                    "data:image/jpeg;base64,"
                    + _b64.b64encode(photo.getvalue()).decode()
                )
            except Exception:
                avatar_url = None

        text = (msg.text or msg.caption or "").strip()
        if not text and not (msg.photo or msg.sticker or msg.voice):
            return None

        payload = {
            "chatId": msg.chat.id if msg.chat else 1,
            "from": {"id": sender_id, "name": sender_name},
            "avatar": True,
        }
        if avatar_url:
            payload["from"]["photo"] = {"url": avatar_url}

        if msg.photo:
            try:
                file_path = await self.client.app.download_media(msg, in_memory=True)
                import base64 as _b64
                payload["media"] = {
                    "url": (
                        "data:image/jpeg;base64,"
                        + _b64.b64encode(file_path.getvalue()).decode()
                    )
                }
                payload["mediaType"] = "photo"
            except Exception:
                pass
            if text:
                payload["text"] = text
        elif msg.sticker:
            try:
                file_path = await self.client.app.download_media(msg, in_memory=True)
                import base64 as _b64
                payload["media"] = {
                    "url": (
                        "data:image/webp;base64,"
                        + _b64.b64encode(file_path.getvalue()).decode()
                    )
                }
                payload["mediaType"] = "sticker"
            except Exception:
                pass
        elif msg.voice:
            payload["mediaType"] = "voice"
            payload["text"] = text or "🎤 Voice message"
        else:
            payload["text"] = text

        if msg.reply_to_message:
            replied = msg.reply_to_message
            r_sender = replied.from_user
            r_name = (
                " ".join(filter(None, [r_sender.first_name, r_sender.last_name]))
                if r_sender and r_sender.first_name
                else (replied.chat.title if replied.chat else "Unknown")
            )
            payload["replyMessage"] = {
                "name": r_name,
                "text": (replied.text or replied.caption or "")[:300],
                "chatId": replied.chat.id if replied.chat else sender_id,
            }

        return payload

    async def _generate(self, payloads: list[dict], color: str, as_png: bool):
        body = {
            "type": "quote",
            "format": "png" if as_png else "webp",
            "backgroundColor": color,
            "messages": payloads,
        }
        last_err = None
        async with httpx.AsyncClient(timeout=60, follow_redirects=True) as c:
            for api in QUOTE_APIS:
                try:
                    r = await c.post(api, json=body)
                    if r.status_code != 200:
                        last_err = RuntimeError(f"HTTP {r.status_code}")
                        continue
                    data = r.json()
                    # Struktur respons beda antar instance:
                    # - quote-api resmi: {"image": "<base64>", "ext": "png"}
                    # - yuri.ly: {"ok": true, "result": {"image": "<base64>", ...}}
                    img_b64 = ""
                    ext = "png" if as_png else "webp"
                    if isinstance(data.get("result"), dict):
                        img_b64 = data["result"].get("image", "")
                    elif data.get("image"):
                        img_b64 = data["image"]
                        if data.get("ext"):
                            ext = data["ext"]
                    if not img_b64:
                        last_err = RuntimeError(
                            data.get("error", {}).get("message", "empty image")
                            if isinstance(data.get("error"), dict)
                            else "empty image"
                        )
                        continue
                    return base64.b64decode(img_b64), ext
                except Exception as e:
                    last_err = e
                    continue
        raise last_err or RuntimeError("quote api gagal semua")

    @handler(filters.regex(PATTERN), 1)
    async def on_message_out(self, event: Message) -> None:
        import asyncio as _asyncio

        m = PATTERN.match(str(event.content or "").strip())
        if not m:
            return
        color_arg, count_arg = m.group(1), m.group(2)

        if not event.reply_to_message:
            return await event.edit("<b>Reply ke pesan dulu.</b>")

        count = min(max(int(count_arg or 1), 1), 10)
        as_png = bool(color_arg and color_arg.lower() in ("png", "p"))
        if as_png and not count_arg:
            count_arg = color_arg if (color_arg or "").isdigit() else count_arg
        if (color_arg or "").lower() in ("png", "p"):
            color_arg = None
        color = _pick_color(color_arg)

        await event.edit("<code>Membuat quote...</code>")

        messages = await self.client.app.get_messages(
            event.chat.id, list(range(event.reply_to_message.id, event.reply_to_message.id + count))
        )

        payloads = []
        for msg in messages:
            if msg is None:
                continue
            p = await self._build_message_payload(msg)
            if p:
                payloads.append(p)

        if not payloads:
            return await event.edit("<b>Tidak ada pesan valid untuk di-quote.</b>")

        try:
            img_bytes, ext = await self._generate(payloads, color, as_png)
        except Exception as e:
            return await event.edit(f"<b>Quote gagal:</b> <code>{html.escape(str(e))}</code>")

        import tempfile
        from pathlib import Path

        with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as f:
            f.write(img_bytes)
            out_path = Path(f.name)

        try:
            if ext == "webp":
                await event.reply_sticker(out_path)
            else:
                await event.reply_photo(out_path)
            await event.delete()
        finally:
            out_path.unlink(missing_ok=True)
