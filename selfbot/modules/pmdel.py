import asyncio
import contextlib
import re

from pyrogram import filters
from pyrogram.types import Message

from selfbot.listener import handler
from selfbot.module import Module

pattern = re.compile(r"^pmdel(?:\s+(on|off))?$", re.IGNORECASE)


class PmDelete(Module):
    """Auto-delete semua PM yang masuk. Toggle: .pmdel on/off"""

    name = "PM Auto Delete"
    cmds = "pmdel [on|off]"
    desc = {
        "on/off": "Nyalain/matiin auto-delete PM",
        "e.g.": "pmdel on",
    }

    async def on_starting(self) -> None:
        enabled = await self.getvar("PMDEL_ENABLED")
        self.enabled = str(enabled).lower() in ("1", "true", "yes", "on")

    @handler(filters.regex(pattern) & filters.outgoing, 0)
    async def on_toggle(self, event: Message) -> None:
        arg = (event.text or "").split()[-1].lower()
        if arg == "on":
            self.enabled = True
            await self.setvar("PMDEL_ENABLED", "1")
            await event.edit("**PM Auto Delete:** ON ✅")
        elif arg == "off":
            self.enabled = False
            await self.setvar("PMDEL_ENABLED", "0")
            await event.edit("**PM Auto Delete:** OFF ❌")

    @handler(filters.incoming & filters.private, 5)
    async def on_pm(self, event: Message) -> None:
        if not self.enabled:
            return
        with contextlib.suppress(Exception):
            await event.delete()
