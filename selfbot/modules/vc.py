import asyncio
import contextlib
import os
import re
import tempfile

from pyrogram import filters
from pyrogram.types import Message

from selfbot.listener import handler
from selfbot.module import Module

pattern = re.compile(r"^vc(?:\s+([\s\S]+))?$", re.IGNORECASE)

# Preset pitch: faktor atempo & asetrate
PRESETS = {
    "chipmunk": (1.5, 1.5),   # tinggi kayak tupai
    "dale": (0.7, 0.75),      # berat & pelan
    "deep": (1.0, 0.7),       # dalam
    "fast": (1.6, 1.0),       # cepet
    "slow": (0.6, 1.0),       # lambat
}


class VoiceChanger(Module):
    name = "Voice Changer"
    cmds = "vc {chipmunk|dale|deep|fast|slow} (reply voice)"
    desc = {
        "chipmunk": "Suara tinggi kayak tupai.",
        "dale": "Suara berat & pelan.",
        "deep": "Suara dalam.",
        "fast": "Percepat voice.",
        "slow": "Perlambat voice.",
        "e.g.": "reply voice note → vc chipmunk",
    }

    @handler(filters.regex(pattern), 1)
    async def on_message_out(self, event: Message) -> None:
        arg = (pattern.match(str(event.content).strip()).group(1) or "").strip().lower()
        if arg not in PRESETS:
            await self.respond(
                event,
                "<code>Usage: vc {chipmunk|dale|deep|fast|slow} — reply ke voice note.</code>",
            )
            return

        reply = event.reply_to_message
        src = None
        if reply:
            if reply.voice:
                src = await self.client.app.download_media(reply, file_name=tempfile.mkdtemp(prefix="vc_") + "/in.ogg")
            elif reply.audio or reply.video:
                src = await self.client.app.download_media(reply, file_name=tempfile.mkdtemp(prefix="vc_") + "/in.m4a")
        if not src:
            await self.respond(event, "<code>Reply ke voice/audio/video dulu.</code>")
            return

        status = await self.respond(event, f"<code>Memproses {arg}...</code>")

        atempo, asetrate = PRESETS[arg]
        tmp_dir = os.path.dirname(src)
        out = os.path.join(tmp_dir, "out.ogg")

        # asetrate mengubah pitch + tempo; atempo mengkompensasi tempo
        speed_correction = 1.0 / asetrate
        cmd = [
            "ffmpeg", "-y", "-i", src,
            "-filter:a", f"asetrate=48000*{asetrate},atempo={speed_correction * atempo:.4f}",
            "-c:a", "libopus", "-b:a", "64k", out,
        ]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL
            )
            await asyncio.wait_for(proc.communicate(), timeout=120)
            if not os.path.exists(out) or os.path.getsize(out) < 1000:
                raise RuntimeError("ffmpeg gagal")
        except Exception as e:
            with contextlib.suppress(Exception):
                await status.edit(f"<code>Gagal: {e}</code>")
            with contextlib.suppress(Exception):
                import shutil
                shutil.rmtree(tmp_dir, True)
            return

        with contextlib.suppress(Exception):
            await status.delete()
        with contextlib.suppress(Exception):
            await self.client.app.send_voice(event.chat.id, out)
        with contextlib.suppress(Exception):
            import shutil
            shutil.rmtree(tmp_dir, True)
            with contextlib.suppress(Exception):
                os.remove(src)
            with contextlib.suppress(Exception):
                await event.delete()
