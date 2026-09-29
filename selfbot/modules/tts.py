import asyncio
import html
import os
import re
import tempfile

import edge_tts
from pyrogram import filters
from pyrogram.types import Message, ReplyParameters

from selfbot.listener import handler
from selfbot.module import Module

TTS_PATTERN = re.compile(r"^tts(?:\s+([\s\S]+))?$", re.IGNORECASE)

# Suara populer: (alias, voice)
VOICES = {
    "ardi": "id-ID-ArdiNeural",      # ID cowok
    "gadis": "id-ID-GadisNeural",    # ID cewek
    "guy": "en-US-GuyNeural",        # EN cowok
    "aria": "en-US-AriaNeural",      # EN cewek
    "ana": "en-US-AnaNeural",        # EN anak kecil
    "jenny": "en-US-JennyNeural",    # EN cewek 2
    "osman": "tr-TR-OsmanNeural",    # Turki cowok
    "keita": "ja-JP-KeitaNeural",    # Jepang cowok
    "nanami": "ja-JP-NanamiNeural",  # Jepang cewek
    "injoon": "ko-KR-InJoonNeural",  # Korea cowok
    "sunhi": "ko-KR-SunHiNeural",    # Korea cewek
    "hamed": "ar-SA-HamedNeural",    # Arab cowok
    "salim": "ar-EG-SalimNeural",    # Mesir cowok
    "dmitry": "ru-RU-DmitryNeural",  # Rusia cowok
    "elsa": "it-IT-ElsaNeural",      # Italia cewek
    "carl": "de-DE-ConradNeural",    # Jerman cowok
    "henri": "fr-FR-HenriNeural",    # Perancis cowok
    "xiaoxiao": "zh-CN-XiaoxiaoNeural",  # Mandarin cewek
    "yunxi": "zh-CN-YunxiNeural",    # Mandarin cowok
}

DEFAULT_VOICE = "id-ID-GadisNeural"
HELP_LINES = ", ".join(f"`{k}`" for k in VOICES)


def _resolve(spec: str) -> str | None:
    spec = spec.strip().lower()
    if spec in VOICES:
        return VOICES[spec]
    for alias, voice in VOICES.items():
        if voice.lower().startswith(spec):
            return voice
    # full voice name e.g. id-ID-ArdiNeural
    if re.match(r"^[a-z]{2}-[a-z]{2}-\w+neural$", spec):
        return spec
    # bare language code e.g. "en" -> find any voice starting with it
    if re.match(r"^[a-z]{2}$", spec):
        for voice in VOICES.values():
            if voice.lower().startswith(spec + "-"):
                return voice
    return None


class TTS(Module):
    name = "Text To Speech"
    cmds = "tts [voice] <text>"
    desc = {
        "tts <text>": "Voice note (default Indonesian female).",
        "tts <voice> <text>": f"Pick a voice: {HELP_LINES}",
        "tts (reply)": "Convert the replied message text.",
        "e.g.": "tts ardi halo bro",
    }

    @handler(filters.regex(r"^tts(?:\s+.*)?$", re.IGNORECASE), 1)
    async def on_message_out(self, event: Message) -> None:
        text = str(event.content).strip()
        m = TTS_PATTERN.match(text)
        if not m:
            return

        arg = (m.group(1) or "").strip()
        voice = DEFAULT_VOICE
        body = arg

        if arg:
            first_word = arg.split()[0].strip("`").lower()
            resolved = _resolve(first_word)
            if resolved:
                voice = resolved
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

        status = await self.respond(event, f"<code>Generating voice ({voice})...</code>")
        tmp_path = None

        try:
            tmp_fd, tmp_path = tempfile.mkstemp(suffix=".mp3")
            os.close(tmp_fd)
            communicate = edge_tts.Communicate(body, voice)
            await asyncio.wait_for(communicate.save(tmp_path), timeout=60)

            if os.path.getsize(tmp_path) < 1000:
                raise RuntimeError("empty audio response")

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
