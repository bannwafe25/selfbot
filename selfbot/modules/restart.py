import asyncio
import os
import re
import sys

from pyrogram import filters
from pyrogram.types import Message

from selfbot.listener import fltrep, handler
from selfbot.module import Module

pattern = re.compile(r"^r(?:estart)?$")


class Restart(Module):
    name = "Restart System"
    cmds = "r(estart)?"
    desc = {"?": "Optional", "e.g": "restart"}

    @handler(filters.regex(pattern) & ~fltrep, 1)
    async def on_message_out(self, event: Message) -> None:
        await asyncio.gather(
            self.respond(event, "<code>Restarting...</code>"),
            self.client.db.execute(
                "INSERT INTO restart.msg (chat_id, message_id) VALUES ($1, $2);",
                event.chat.id,
                event.id,
            ),
        )
        os.execv(sys.argv[0], sys.argv)
