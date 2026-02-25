import datetime
import html
import re
from io import BytesIO

from pyrogram import filters
from pyrogram.types import Message, ReplyParameters

from selfbot.listener import handler
from selfbot.module import Module
from selfbot.apis import DELINE_BRAT, DELINE_BRATVID, DELINE_CEWEKBRAT

pattern = re.compile(r"^brat(?:\s+([\s\S]+))?$", re.IGNORECASE)


class Brat(Module):
    name = "Brat"
    cmds = "brat (-v|-c)? {text}"
    desc = {
        "text": "Text to render as brat image/video.",
        "-v": "Send as video.",
        "-c": "Use cewekbrat style.",
        "e.g.": "brat -c hello world",
    }

    @handler(filters.regex(pattern), 1)
    async def on_message_out(self, event: Message) -> None:
        await self.respond(event, "<code>Generating...</code>")
        now = datetime.datetime.now(datetime.UTC)

        raw = (pattern.match(str(event.content).strip()).group(1) or "").strip()
        text, mode = self._parse_args(raw)

        if not text and event.reply_to_message:
            text = self.message_text(event.reply_to_message).strip()

        if not text:
            await self.respond(
                event,
                "<code>Usage: brat (-v|-c) {text} or reply to a message.</code>",
            )
            return

        try:
            if mode == "video":
                api_url = DELINE_BRATVID
            elif mode == "cewek":
                api_url = DELINE_CEWEKBRAT
            else:
                api_url = DELINE_BRAT

            resp = await self.client.http.get(
                api_url,
                params={"text": text},
                timeout=60,
            )
            if resp.status_code != 200:
                raise RuntimeError(f"API error: HTTP {resp.status_code}")

            reply_id = event.reply_to_message_id or event.id
            reply_params = ReplyParameters(message_id=reply_id)

            if mode == "video":
                import tempfile
                import asyncio
                import os
                
                with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp_mp4:
                    tmp_mp4.write(resp.content)
                    in_path = tmp_mp4.name
                out_path = in_path.replace(".mp4", ".webm")
                
                try:
                    proc = await asyncio.create_subprocess_exec(
                        "ffmpeg", "-y", "-i", in_path,
                        "-c:v", "libvpx-vp9", "-b:v", "256k", "-an",
                        "-vf", "scale=512:512,fps=30",
                        out_path,
                        stdout=asyncio.subprocess.DEVNULL,
                        stderr=asyncio.subprocess.DEVNULL,
                    )
                    await proc.wait()
                    
                    if proc.returncode == 0 and os.path.exists(out_path):
                        await event._client.send_sticker(
                            chat_id=event.chat.id,
                            sticker=out_path,
                            reply_parameters=reply_params,
                        )
                    else:
                        raise RuntimeError("Failed to convert video to WebM sticker")
                finally:
                    if os.path.exists(in_path):
                        os.remove(in_path)
                    if os.path.exists(out_path):
                        os.remove(out_path)
            else:
                image = BytesIO(resp.content)
                image.name = "brat.webp"
                image.seek(0)
                await event._client.send_sticker(
                    chat_id=event.chat.id,
                    sticker=image,
                    reply_parameters=reply_params,
                )

            await event.delete()
        except Exception as e:
            await self.respond(
                event,
                f"<b>Brat failed</b>\n\n<code>{html.escape(str(e)[:300])}</code>",
            )

    @staticmethod
    def _parse_args(raw: str) -> tuple[str, str]:
        mode = "image"
        words = []
        for token in raw.split():
            low = token.lower()
            if low in ("-v", "--video"):
                mode = "video"
            elif low in ("-c", "--cewek"):
                mode = "cewek"
            else:
                words.append(token)
        return " ".join(words).strip(), mode
