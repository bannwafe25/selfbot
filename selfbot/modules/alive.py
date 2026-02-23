import datetime
import platform
import re

from pyrogram import __version__ as pyrogram_version
from pyrogram import filters
from pyrogram.types import Message

from selfbot import __version__
from selfbot.listener import handler
from selfbot.module import Module

pattern = re.compile(r"^alive(?:\s+)?$", re.IGNORECASE)


class Alive(Module):
    name = "Alive"
    cmds = "alive"
    desc = {
        "Info": "Check selfbot status, versions, and uptime.",
        "e.g.": "alive",
    }

    async def on_starting(self) -> None:
        self.started_at = datetime.datetime.now(datetime.UTC)

    @handler(filters.regex(pattern), 1)
    async def on_message_out(self, event: Message) -> None:
        await self.respond(event, "<code>Checking...</code>")
        now = datetime.datetime.now(datetime.UTC)

        await self.respond(
            event,
            self.fmtmsg(
                "Selfbot Alive",
                {
                    "Status": "Online",
                    "Version": __version__,
                    "Python": platform.python_version(),
                    "Pyrogram": pyrogram_version,
                    "Uptime": self.fmtsec(self.started_at, human=True),
                },
                self.fmtsec(now),
                "Repository: https://github.com/The-MoonTg-project/Moon-Userbot",
            ),
        )
