import asyncio
import html
import os
import re
import tempfile
import urllib.parse
import urllib.request

from pyrogram import filters
from pyrogram.types import Message, ReplyParameters

from selfbot.listener import handler
from selfbot.module import Module

TTS_PATTERN = re.compile(r"^tts(?:\s+([\s\S]+))?$", re.IGNORECASE)

# Kode bahasa Google Translate TTS (gratis, tanpa API key)
LANGS = ["id", "en", "ja", "ko", "ar", "tr", "ru", "it", "de", "fr", "zh-CN", "es", "hi", "th"]

DEFAULT_VOICE = "id"
HELP_LINES = ", ".join(f"`{k}`" for k in LANGS)

GOOGLE_TTS_URL = "https://translate.google.com/translate_tts"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120 Safari/537.36")


def _resolve(spec: str) -> str | None:
    spec = spec.strip().lower()
    if spec in LANGS:
        return spec
    # kode bahasa langsung: id, en, ja, zh-CN, dll
    if re.match(r"^[a-z]{2}(-[a-z]{2})?$", spec):
        return spec
    return None


def _google_tts_download(text: str, lang: str, dest: str, idx: int) -> None:
    """Unduh satu chunk TTS dari Google Translate (max ~200 char)."""
    q = urllib.parse.urlencode({
        "ie": "UTF-8", "q": text, "tl": lang, "total": "1",
        "idx": str(idx), "textlen": str(len(text)),
        "client": "tw-ob", "ttsspeed": "1",
    })
    req = urllib.request.Request(
        f"{GOOGLE_TTS_URL}?{q}",
        headers={"User-Agent": UA, "Referer": "https://translate.google.com/"},
    )
    with urllib.request.urlopen(req, timeout=30) as r, open(dest, "wb") as f:
        f.write(r.read())


def _split_text(text: str, limit: int = 190) -> list[str]:
    """Pecah teks per kalimat/kata agar <= limit char (batas Google TTS)."""
    parts = []
    cur = ""
    for word in text.split():
        if len(cur) + len(word) + 1 > limit:
            if cur:
                parts.append(cur)
            cur = word
        else:
            cur = f"{cur} {word}".strip()
    if cur:
        parts.append(cur)
    return parts or [""]


class TTS(Module):
    name = "Text To Speech"
    cmds = "tts [bahasa] <text>"
    desc = {
        "tts <text>": "Voice note (default Indonesia).",
        "tts <voice> <text>": f"Bahasa: {HELP_LINES}",
        "tts (reply)": "Convert the replied message text.",
        "e.g.": "tts halo bro",
    }

    @handler(filters.regex(r"^tts(?:\s+.*)?$", re.IGNORECASE), 1)
    async def on_message_out(self, event: Message) -> None:
        text = str(event.content).strip()
        m = TTS_PATTERN.match(text)
        if not m:
            return

        arg = (m.group(1) or "").strip()
        lang = DEFAULT_VOICE
        body = arg

        if arg:
            first_word = arg.split()[0].strip("`").lower()
            resolved = _resolve(first_word)
            if resolved:
                lang = resolved
                body = arg[len(arg.split()[0]):].strip()

        if not body and event.reply_to_message:
            body = (event.reply_to_message.text or event.reply_to_message.caption or "").strip()

        if not body:
            await self.respond(
                event,
                "<b>Usage:</b> <code>tts [voice] &lt;text&gt;</code> atau reply pesan\n"
                f"<b>Voices:</b> {HELP_LINES}",
            )
            return

        status = await self.respond(event, f"<code>Generating voice ({lang})...</code>")
        tmp_path = None

        try:
            loop = asyncio.get_event_loop()
            parts = _split_text(body[:1000])
            chunks = []
            tmp_dir = tempfile.mkdtemp(prefix="tts_")
            for i, part in enumerate(parts):
                p = os.path.join(tmp_dir, f"c{i}.mp3")
                await loop.run_in_executor(
                    None, _google_tts_download, part, lang, p, i
                )
                if os.path.getsize(p) > 500:
                    chunks.append(p)
            if not chunks:
                raise RuntimeError("empty audio response")

            # Gabung chunk dengan ffmpeg concat
            tmp_path = os.path.join(tmp_dir, "out.mp3")
            if len(chunks) == 1:
                os.replace(chunks[0], tmp_path)
            else:
                list_file = os.path.join(tmp_dir, "list.txt")
                with open(list_file, "w") as f:
                    for c in chunks:
                        f.write(f"file '{c}'\n")
                proc = await asyncio.create_subprocess_exec(
                    "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                    "-i", list_file, "-c", "copy", tmp_path,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                await asyncio.wait_for(proc.communicate(), timeout=60)
                if not os.path.exists(tmp_path) or os.path.getsize(tmp_path) < 1000:
                    raise RuntimeError("ffmpeg concat gagal")

            reply_parameters = ReplyParameters(message_id=event.reply_to_message_id or event.id)
            await event._client.send_voice(
                chat_id=event.chat.id,
                voice=tmp_path,
                reply_parameters=reply_parameters,
            )

            try:
                await status.delete()
            except Exception:
                pass
        except Exception as e:
            await self.respond(event, f"<b>TTS failed:</b> <code>{html.escape(str(e))}</code>")
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass
