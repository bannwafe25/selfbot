import asyncio
import datetime
import html
import io
import re

from pyrogram import filters
from pyrogram.types import Message, InputMediaDocument

from selfbot.listener import handler
from selfbot.module import Module
from selfbot.utils import fmtsec

pattern = re.compile(r"^(?:sh|term|cmd)\s+(.+)$", re.IGNORECASE | re.DOTALL)

class Terminal(Module):
    name = "Terminal"
    cmds = "sh|term|cmd {command}"
    desc = {
        "Info": "Execute shell commands on the host directly from Telegram.",
        "command": "The shell command to execute.",
        "e.g.": "sh uname -a",
    }

    @handler(filters.regex(pattern), 1)
    async def on_message_out(self, event: Message) -> None:
        match = pattern.match(event.text or event.caption or "")
        if not match:
            return

        command = match.group(1).strip()
        if not command:
            await self.respond(event, "<code>Usage: sh {command}</code>")
            return

        await self.respond(event, f"<code>$ {html.escape(command)}\n\nProcessing...</code>")
        now = datetime.datetime.now(datetime.UTC)

        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            stdout, stderr = await process.communicate()
            
            out = stdout.decode(errors="replace").strip()
            err = stderr.decode(errors="replace").strip()
            
            result_text = ""
            if out:
                result_text += f"{out}\n"
            if err:
                result_text += f"[stderr]\n{err}\n"
                
            if not result_text:
                result_text = "[No Output]"
                
            elapsed = fmtsec(now)

            if len(result_text) > 3000:
                with io.BytesIO(result_text.encode()) as doc:
                    doc.name = "output.txt"
                    await self.respond(
                        event,
                        InputMediaDocument(
                            doc,
                            caption=f"<code>$ {html.escape(command[:100])}...</code>\n\n<b><blockquote>{elapsed}</blockquote></b>",
                        )
                    )
            else:
                await self.respond(
                    event,
                    f"<code>$ {html.escape(command)}\n\n{html.escape(result_text)}</code>\n\n<b><blockquote>{elapsed}</blockquote></b>"
                )

        except Exception as e:
            await self.respond(
                event,
                f"<code>$ {html.escape(command)}\n\nError: {html.escape(str(e))}</code>\n\n<b><blockquote>{fmtsec(now)}</blockquote></b>"
            )
