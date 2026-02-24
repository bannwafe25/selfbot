import datetime
import html
import re

from pyrogram import filters
from pyrogram.types import Message

from selfbot.listener import handler
from selfbot.module import Module

pattern = re.compile(r"^id(?:\s+)?$", re.IGNORECASE)


class ID(Module):
    name = "ID"
    cmds = "id"
    desc = {
        "Info": "Show IDs for current chat/message and replied/forwarded context.",
        "e.g.": "id",
    }

    @handler(filters.regex(pattern), 1)
    async def on_message_out(self, event: Message) -> None:
        await self.respond(event, "<code>Collecting IDs...</code>")
        now = datetime.datetime.now(datetime.UTC)

        lines = []
        self._append_line(lines, "Chat ID", event.chat.id)
        self._append_line(lines, "Chat DC ID", getattr(event.chat, "dc_id", None))
        self._append_line(lines, "Message ID", event.id)

        self._append_actor(
            lines=lines,
            user=event.from_user,
            sender_chat=event.sender_chat,
            user_prefix="Your",
            chat_prefix="Sender Chat",
        )

        replied = event.reply_to_message
        if replied:
            lines.append("")
            self._append_line(lines, "Replied Message ID", replied.id)

            self._append_actor(
                lines=lines,
                user=replied.from_user,
                sender_chat=replied.sender_chat,
                user_prefix="Replied User",
                chat_prefix="Replied Chat",
            )

            self._append_forward_info(lines, replied)

        content = "\n".join(lines).strip()
        text = (
            "<b>ID Information</b>\n\n"
            f"<code>{html.escape(content)}</code>\n\n"
            f"<b><blockquote>{self.fmtsec(now)}</blockquote></b>"
        )
        await self.respond(event, text)

    def _append_forward_info(self, lines: list[str], message: Message) -> None:
        origin = getattr(message, "forward_origin", None)
        if origin:
            lines.append("")
            self._append_line(lines, "Forwarded Message ID", getattr(origin, "message_id", None))

            sender_user = getattr(origin, "sender_user", None)
            if sender_user:
                self._append_line(lines, "Forwarded User ID", getattr(sender_user, "id", None))
                self._append_line(
                    lines, "Forwarded User DC ID", getattr(sender_user, "dc_id", None)
                )
                return

            sender_chat = getattr(origin, "sender_chat", None)
            if sender_chat:
                self._append_line(lines, "Forwarded Chat ID", getattr(sender_chat, "id", None))
                self._append_line(
                    lines, "Forwarded Chat DC ID", getattr(sender_chat, "dc_id", None)
                )
                return

            sender_name = (
                getattr(origin, "sender_name", None)
                or getattr(origin, "hidden_user_name", None)
                or getattr(origin, "author_signature", None)
            )
            if sender_name:
                self._append_line(lines, "Forwarded From", sender_name)
            else:
                self._append_line(lines, "Forwarded From", "Hidden user")
            return

        if message.forward_from_message_id:
            lines.append("")
            self._append_line(lines, "Forwarded Message ID", message.forward_from_message_id)

        if message.forward_from:
            self._append_line(lines, "Forwarded User ID", message.forward_from.id)
            self._append_line(
                lines, "Forwarded User DC ID", getattr(message.forward_from, "dc_id", None)
            )
            return

        if message.forward_from_chat:
            self._append_line(lines, "Forwarded Chat ID", message.forward_from_chat.id)
            self._append_line(
                lines,
                "Forwarded Chat DC ID",
                getattr(message.forward_from_chat, "dc_id", None),
            )
            return

        if message.forward_sender_name:
            self._append_line(lines, "Forwarded From", message.forward_sender_name)

    @staticmethod
    def _append_line(lines: list[str], label: str, value: object) -> None:
        if value is None or value == "":
            value = "-"
        lines.append(f"{label}: {value}")

    def _append_actor(
        self,
        lines: list[str],
        user,
        sender_chat,
        user_prefix: str,
        chat_prefix: str,
    ) -> None:
        if user:
            self._append_line(lines, f"{user_prefix} ID", user.id)
            self._append_line(lines, f"{user_prefix} DC ID", getattr(user, "dc_id", None))
            return

        if sender_chat:
            self._append_line(lines, f"{chat_prefix} ID", sender_chat.id)
            self._append_line(
                lines, f"{chat_prefix} DC ID", getattr(sender_chat, "dc_id", None)
            )
