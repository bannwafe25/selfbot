import datetime
import re

from pyrogram import filters
from pyrogram.raw.functions import Ping as Latency
from pyrogram.types import Message

from selfbot import __version__
from selfbot.listener import handler
from selfbot.module import Module

pattern = re.compile(r"^alive(?:\s+)?$", re.IGNORECASE)


class Alive(Module):
    name = "Alive"
    cmds = "alive"
    desc = {
        "Info": "Check selfbot status and uptime.",
        "e.g.": "alive",
    }

    async def on_starting(self) -> None:
        self.started_at = datetime.datetime.now(datetime.UTC)

    @handler(filters.regex(pattern), 1)
    async def on_message_out(self, event: Message) -> None:
        await self.respond(event, "<code>Checking...</code>")
        now = datetime.datetime.now(datetime.UTC)
        await self.client.app.invoke(Latency(ping_id=0))
        started_at = getattr(self, "started_at", now)

        await self.respond(
            event,
            self.fmtmsg(
                "Selfbot Alive",
                {
                    "Status": "Online",
                    "Version": __version__,
                    "Uptime": self.fmtsec(started_at, human=True),
                },
                self.fmtsec(now),
                "Repository: Coming Soon",
            ),
        )
