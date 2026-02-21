import asyncio
import os
import re
import sys

from pyrogram import filters
from pyrogram.types import Message

from selfbot.listener import handler, reply
from selfbot.module import Module

pattern = re.compile(r"^r(?:estart)?$")


class Restart(Module):
    name = "Restart System"
    cmds = "r(estart)?"
    desc = {"?": "Optional", "e.g": "restart"}

    @handler(filters.regex(pattern) & ~reply, 1)
    async def on_message_out(self, event: Message) -> None:
        await asyncio.gather(
            self.respond(event, "<code>Restarting...</code>"),
            self.client.db.restart_msgs.update_one(
                {"name": "app"},
                {"$set": {"chat_id": event.chat.id, "message_id": event.id}},
                upsert=True
            ),
        )
        os.execv(sys.argv[0], sys.argv)
