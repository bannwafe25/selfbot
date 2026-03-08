import datetime
import html
import re

from pyrogram import filters, enums
from pyrogram.types import Message, Chat

from selfbot.listener import handler
from selfbot.module import Module


class ID(Module):
    name = "ID"
    cmds = "id | cinfo {chat}?"
    desc = {
        "Info": "Show IDs for the current chat/message, replied/forwarded context, and detailed chat info.",
        "chat": "Optional. Chat ID or Username for cinfo command.",
        "e.g.": "id\ncinfo -1001129887931",
    }

    _id_pattern = re.compile(r"^id(?:\s+)?$", re.IGNORECASE)
    _cinfo_pattern = re.compile(r"^cinfo(?:\s+(.+))?$", re.IGNORECASE)

    @handler(filters.regex(_cinfo_pattern), 1)
    async def on_cinfo_cmd(self, event: Message) -> None:
        await self.respond(event, "<code>Fetching chat information...</code>")
        match = self._cinfo_pattern.match(str(event.content or "").strip())
        chat_req = match.group(1)

        chat_req = chat_req.strip() if chat_req else event.chat.id
        if isinstance(chat_req, str) and chat_req.lstrip('-').isdigit():
            chat_req = int(chat_req)

        try:
            chat: Chat = await event._client.get_chat(chat_req)
        except Exception as e:
            return await self.respond(event, f"<b>Error:</b> <code>{html.escape(str(e))}</code>")

        if hasattr(self.client, "db") and hasattr(self.client.db, "chats"):
            try:
                await self.client.db.chats.update_one(
                    {"_id": chat.id},
                    {"$set": {"id": chat.id, "title": chat.title or chat.first_name or "Unknown"}},
                    upsert=True
                )
            except Exception:
                pass

        lines = [
            "<b>Chat Information</b>",
            self._kv("ID", chat.id),
            self._kv("Title", chat.title or chat.first_name or "Unknown"),
        ]

        if chat.username:
            lines.append(self._kv("Username", f"@{chat.username}"))
        
        if chat.members_count:
            lines.append(self._kv("Members", chat.members_count))

        creation_date = await self._get_creation_date(event._client, chat)
        if creation_date:
            lines.append(self._kv("Created", creation_date))

        if chat.type in (enums.ChatType.GROUP, enums.ChatType.SUPERGROUP, enums.ChatType.CHANNEL):
            admin_lines = await self._get_admin_gban_lines(event._client, chat)
            if admin_lines:
                lines.append("\n<b>Admins</b>")
                lines.extend(admin_lines)

        await self._send_result(event, lines)

    @handler(filters.regex(_id_pattern), 2)
    async def on_id_cmd(self, event: Message) -> None:
        await self.respond(event, "<code>Collecting IDs...</code>")
        
        lines = [
            "<b>ID Information</b>",
            self._kv("Chat ID", event.chat.id),
        ]
        
        if getattr(event.chat, "dc_id", None):
            lines.append(self._kv("Chat DC", event.chat.dc_id))
            
        lines.append(self._kv("Message ID", event.id))

        self._append_user_chat_info(lines, event.from_user, event.sender_chat, "Your", "Sender Chat")

        if event.reply_to_message:
            replied = event.reply_to_message
            lines.append("")
            lines.append(self._kv("Replied Msg ID", replied.id))
            self._append_user_chat_info(lines, replied.from_user, replied.sender_chat, "Replied User", "Replied Chat")
            self._extract_forward_info(lines, replied)

        await self._send_result(event, lines)

    # --- Helper Methods ---

    async def _send_result(self, event: Message, lines: list[str]) -> None:
        text = "\n".join(lines).strip()
        now = datetime.datetime.now(datetime.UTC)
        text += f"\n\n<b><blockquote>{self.fmtsec(now)}</blockquote></b>"
        await self.respond(event, text)

    @staticmethod
    def _kv(key: str, value: object) -> str:
        val_str = html.escape(str(value)) if value not in (None, "") else "-"
        return f"<b>{key}:</b> <code>{val_str}</code>"

    @staticmethod
    async def _get_creation_date(client, chat: Chat) -> str:
        try:
            if chat.type in (enums.ChatType.CHANNEL, enums.ChatType.SUPERGROUP):
                try:
                    first_msg = await client.get_messages(chat.id, 1)
                    if first_msg and first_msg.date:
                        return first_msg.date.strftime("%Y-%m-%d %H:%M:%S")
                except Exception:
                    pass
            
            async for msg in client.get_chat_history(chat.id, limit=1, reverse=True):
                if msg.date:
                    return msg.date.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            pass
        return ""

    async def _get_admin_gban_lines(self, client, chat: Chat) -> list[str]:
        lines = []
        admins_ids = []
        prefix = "."
        
        if hasattr(self.client, "config") and "prefix" in self.client.config:
            cfg_prefix = self.client.config["prefix"]
            prefix = cfg_prefix[0] if isinstance(cfg_prefix, list) and cfg_prefix else str(cfg_prefix)

        try:
            async for p in client.get_chat_members(chat.id, filter=enums.ChatMembersFilter.ADMINISTRATORS):
                if p.status == enums.ChatMemberStatus.OWNER:
                    lines.append(f"<code>{prefix}gban {p.user.id} \"Spamadd[0x0 {chat.id}]\"</code>")
                elif p.user and not p.user.is_bot:
                    admins_ids.append(str(p.user.id))

            if admins_ids:
                lines.append(f"<code>{prefix}gban {' '.join(admins_ids)} \"Spamadd[0x1 {chat.id}]\"</code>")
        except Exception as e:
            lines.append(f"<i>Could not fetch admins: {html.escape(str(e))}</i>")
            
        return lines

    def _append_user_chat_info(self, lines: list[str], user, chat, user_prefix: str, chat_prefix: str) -> None:
        if user:
            lines.append(self._kv(f"{user_prefix} ID", user.id))
            if getattr(user, "dc_id", None):
                lines.append(self._kv(f"{user_prefix} DC", user.dc_id))
        elif chat:
            lines.append(self._kv(f"{chat_prefix} ID", chat.id))
            if getattr(chat, "dc_id", None):
                lines.append(self._kv(f"{chat_prefix} DC", chat.dc_id))

    def _extract_forward_info(self, lines: list[str], message: Message) -> None:
        origin = getattr(message, "forward_origin", None)
        if origin:
            lines.append("")
            self._add_origin_details(lines, origin)
            return

        if message.forward_from_message_id:
            lines.append("")
            lines.append(self._kv("Forwarded Msg ID", message.forward_from_message_id))

        if message.forward_from:
            lines.append(self._kv("Forwarded User ID", message.forward_from.id))
            if getattr(message.forward_from, "dc_id", None):
                lines.append(self._kv("Forwarded User DC", message.forward_from.dc_id))
            return

        if message.forward_from_chat:
            lines.append(self._kv("Forwarded Chat ID", message.forward_from_chat.id))
            if getattr(message.forward_from_chat, "dc_id", None):
                lines.append(self._kv("Forwarded Chat DC", message.forward_from_chat.dc_id))
            return

        if message.forward_sender_name:
            lines.append(self._kv("Forwarded From", message.forward_sender_name))

    def _add_origin_details(self, lines: list[str], origin) -> None:
        if getattr(origin, "message_id", None):
            lines.append(self._kv("Forwarded Msg ID", origin.message_id))

        if getattr(origin, "sender_user", None):
            lines.append(self._kv("Forwarded User ID", origin.sender_user.id))
            if getattr(origin.sender_user, "dc_id", None):
                lines.append(self._kv("Forwarded User DC", origin.sender_user.dc_id))
            return

        if getattr(origin, "sender_chat", None):
            lines.append(self._kv("Forwarded Chat ID", origin.sender_chat.id))
            if getattr(origin.sender_chat, "dc_id", None):
                lines.append(self._kv("Forwarded Chat DC", origin.sender_chat.dc_id))
            return

        sender_name = (
            getattr(origin, "sender_name", None)
            or getattr(origin, "hidden_user_name", None)
            or getattr(origin, "author_signature", None)
        )
        if hasattr(origin, "name") and origin.name:
            sender_name = sender_name or origin.name
            
        lines.append(self._kv("Forwarded From", sender_name or "Hidden user"))
