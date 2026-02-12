import asyncio
import re

from pyrogram import filters
from pyrogram.types import Message

from selfbot.listener import handler, reply
from selfbot.module import Module

pattern = re.compile(r"^d(?:el(?:ete)?)?$")


class Delete(Module):
    name = "Delete Message"
    cmds = "<Reply> d(el(ete)?)?"
    desc = {"?": "Optional", "e.g.": "<Reply> del"}

    @handler(filters.regex(pattern) & reply, 1)
    async def on_message_out(self, event: Message) -> None:
        await asyncio.gather(event.delete(), event.reply_to_message.delete())
