import contextlib
import re

from pyrogram import filters
from pyrogram.types import Message

from selfbot.listener import handler
from selfbot.module import Module

pattern = re.compile(r"^pmdel(?:\s+(on|off))?$", re.IGNORECASE)


class PmDelete(Module):
    """PM masuk: dihapus + diteruskan (copy) ke bot sebagai log."""

    name = "PM Delete & Log"
    cmds = "pmdel [on|off]"
    desc = {
        "on/off": "Nyalain/matiin auto-delete PM",
        "e.g.": "pmdel on",
    }

    async def on_starting(self) -> None:
        enabled = await self.getvar("PMDEL_ENABLED")
        self.enabled = str(enabled).lower() in ("1", "true", "yes", "on")

    @handler(filters.regex(pattern) & filters.outgoing, 0)
    async def on_message_out(self, event: Message) -> None:
        arg = (event.text or "").split()[-1].lower()
        if arg == "on":
            self.enabled = True
            await self.setvar("PMDEL_ENABLED", "1")
            await event.edit("**PM Delete & Log:** ON ✅")
        elif arg == "off":
            self.enabled = False
            await self.setvar("PMDEL_ENABLED", "0")
            await event.edit("**PM Delete & Log:** OFF ❌")

    async def on_message_in(self, event: Message) -> None:
        if not self.enabled:
            return

        user = event.from_user
        # skip saved messages / pesan tanpa from_user
        if not user or user.is_self or user.is_bot:
            return

        uname = f"@{user.username}" if user.username else "tanpa username"
        info = (
            "<b>PM terhapus</b>\n"
            f"<b>Dari</b>: <a href='tg://user?id={user.id}'>{user.first_name}</a>"
            f" ({uname}) [<code>{user.id}</code>]\n\n"
        )
        text = (event.text or event.caption or "-")[:1000]

        # log ke bot, terus bot kirim ke owner (saved messages userbot)
        with contextlib.suppress(Exception):
            bot = self.client.bot
            await bot.send_message(
                self.client.app.me.id,
                f"{info}<blockquote>{text}</blockquote>",
            )

        # hapus PM-nya
        with contextlib.suppress(Exception):
            await event.delete()
