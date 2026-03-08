import datetime
import html
import re

from pyrogram import filters, enums
from pyrogram.types import Message

from selfbot.listener import handler
from selfbot.module import Module

pattern = re.compile(r"^id(?:\s+)?$", re.IGNORECASE)
cinfo_pattern = re.compile(r"^cinfo(?:\s+(.+))?$", re.IGNORECASE)


class ID(Module):
    name = "ID"
    cmds = "id | cinfo {chat}"
    desc = {
        "Info": "Show IDs for current chat/message and replied/forwarded context. Cinfo command gets chat details and admins.",
        "chat": "Optional. Chat ID or Username",
        "e.g.": "id\ncinfo -1001129887931",
    }

    @handler(filters.regex(cinfo_pattern), 1)
    async def on_info_cmd(self, event: Message) -> None:
        await self.respond(event, "<code>Fetching info...</code>")
        match = cinfo_pattern.match(str(event.content or "").strip())
        chat_req = match.group(1)

        if not chat_req:
            chat_req = event.chat.id
        else:
            chat_req = chat_req.strip()
            if chat_req.lstrip('-').isdigit():
                chat_req = int(chat_req)

        try:
            chat = await event._client.get_chat(chat_req)
        except Exception as e:
            await self.respond(event, f"<b>Error:</b> <code>{html.escape(str(e))}</code>")
            return

        chat_id = chat.id
        title = chat.title or chat.first_name or "Unknown"

        if hasattr(self.client, "db") and hasattr(self.client.db, "chats"):
            try:
                await self.client.db.chats.update_one(
                    {"_id": chat_id},
                    {"$set": {"id": chat_id, "title": title}},
                    upsert=True
                )
            except Exception:
                pass

        lines = [
            "<b>Chat Info</b>",
            f"<b>chat_id:</b> <code>{chat_id}</code>",
            f"<b>title:</b> <code>{html.escape(title)}</code>",
        ]

        if chat.type in (enums.ChatType.GROUP, enums.ChatType.SUPERGROUP, enums.ChatType.CHANNEL):
            items = []
            admins_ids = []
            
            # Attempt to use prefix from config or fallback to '.'
            prefix = "."
            if hasattr(self.client, "config") and "prefix" in self.client.config:
                cfg_prefix = self.client.config["prefix"]
                if isinstance(cfg_prefix, list) and cfg_prefix:
                    prefix = cfg_prefix[0]
                elif isinstance(cfg_prefix, str):
                    prefix = cfg_prefix

            try:
                async for p in event._client.get_chat_members(chat.id, filter=enums.ChatMembersFilter.ADMINISTRATORS):
                    if p.status == enums.ChatMemberStatus.OWNER:
                        items.append(f"<code>{prefix}gban {p.user.id} \"Spamadd[0x0 {chat_id}]\"</code>")
                    elif p.user and not p.user.is_bot:
                        admins_ids.append(str(p.user.id))

                if admins_ids:
                    items.append(f"<code>{prefix}gban {' '.join(admins_ids)} \"Spamadd[0x1 {chat_id}]\"</code>")

                if items:
                    lines.append("")
                    lines.append("<b>Admins</b>")
                    lines.extend(items)
            except Exception as e:
                lines.append(f"\n<i>Could not get admins: {html.escape(str(e))}</i>")

        text = "\n".join(lines)
        now = datetime.datetime.now(datetime.UTC)
        text += f"\n\n<b><blockquote>{self.fmtsec(now)}</blockquote></b>"
        await self.respond(event, text)

    @handler(filters.regex(pattern), 2)
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
