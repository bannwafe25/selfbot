import datetime
import html
import re

from pyrogram import enums, filters
from pyrogram.types import Chat, Message

from selfbot.listener import handler
from selfbot.module import Module


pattern = re.compile(
    r"^(?:id|cinfo(?:\s+.+)?)$",
    flags=re.IGNORECASE | re.DOTALL,
)


class ID(Module):
    name = "ID"
    cmds = "id | cinfo {chat}?"
    desc = {
        "Info": "Show IDs for the current chat/message and detailed chat information.",
        "chat": "Optional. Chat ID or username for cinfo.",
        "e.g.": "id\ncinfo -1001129887931",
    }

    @handler(filters.regex(pattern), 1)
    async def on_message_out(self, event: Message) -> None:
        content = (event.content or "").strip()

        if re.fullmatch(r"id", content, flags=re.IGNORECASE):
            await self.id_cmd(event)
            return

        match = re.fullmatch(
            r"cinfo(?:\s+(.+))?",
            content,
            flags=re.IGNORECASE | re.DOTALL,
        )

        if match:
            await self.cinfo_cmd(event, match.group(1))
            return

    # =========================
    # ID
    # =========================

    async def id_cmd(self, event: Message) -> None:
        await self.respond(
            event,
            "<code>Collecting IDs...</code>",
        )

        lines = [
            "<b>ID Information</b>",
            self._kv("Chat ID", event.chat.id),
        ]

        if getattr(event.chat, "dc_id", None):
            lines.append(
                self._kv("Chat DC", event.chat.dc_id)
            )

        lines.append(
            self._kv("Message ID", event.id)
        )

        self._append_user_chat_info(
            lines,
            event.from_user,
            event.sender_chat,
            "Your",
            "Sender Chat",
        )

        if event.reply_to_message:
            replied = event.reply_to_message

            lines.append("")
            lines.append(
                self._kv("Replied Msg ID", replied.id)
            )

            self._append_user_chat_info(
                lines,
                replied.from_user,
                replied.sender_chat,
                "Replied User",
                "Replied Chat",
            )

            self._extract_forward_info(
                lines,
                replied,
            )

        await self._send_result(event, lines)

    # =========================
    # CINFO
    # =========================

    async def cinfo_cmd(
        self,
        event: Message,
        chat_arg: str | None = None,
    ) -> None:
        await self.respond(
            event,
            "<code>Fetching chat information...</code>",
        )

        chat_req = (
            chat_arg.strip()
            if chat_arg and chat_arg.strip()
            else event.chat.id
        )

        if isinstance(chat_req, str):
            if chat_req.lstrip("-").isdigit():
                chat_req = int(chat_req)

        try:
            chat: Chat = await event._client.get_chat(chat_req)

        except Exception as e:
            return await self.respond(
                event,
                (
                    "<b>Error:</b>\n"
                    f"<code>{html.escape(str(e))}</code>"
                ),
            )

        # Save chat information if database collection exists.
        if (
            hasattr(self.client, "db")
            and hasattr(self.client.db, "chats")
        ):
            try:
                await self.client.db.chats.update_one(
                    {"_id": chat.id},
                    {
                        "$set": {
                            "id": chat.id,
                            "title": (
                                chat.title
                                or chat.first_name
                                or "Unknown"
                            ),
                            "username": chat.username,
                            "type": str(chat.type),
                        }
                    },
                    upsert=True,
                )
            except Exception as e:
                self.logger.debug(
                    f"Failed to save chat info: {e}"
                )

        lines = [
            "<b>Chat Information</b>",
            self._kv("ID", chat.id),
            self._kv("Type", chat.type),
            self._kv(
                "Title",
                chat.title
                or chat.first_name
                or "Unknown",
            ),
        ]

        if chat.username:
            lines.append(
                self._kv(
                    "Username",
                    f"@{chat.username}",
                )
            )

        if getattr(chat, "dc_id", None):
            lines.append(
                self._kv("DC", chat.dc_id)
            )

        if getattr(chat, "members_count", None):
            lines.append(
                self._kv(
                    "Members",
                    chat.members_count,
                )
            )

        creation_date = await self._get_creation_date(
            event._client,
            chat,
        )

        if creation_date:
            lines.append(
                self._kv(
                    "Created",
                    creation_date,
                )
            )

        if chat.type in (
            enums.ChatType.GROUP,
            enums.ChatType.SUPERGROUP,
            enums.ChatType.CHANNEL,
        ):
            admin_lines = await self._get_admin_gban_lines(
                event._client,
                chat,
            )

            if admin_lines:
                lines.append("")
                lines.append("<b>Admins</b>")
                lines.extend(admin_lines)

        await self._send_result(event, lines)

    # =========================
    # HELPERS
    # =========================

    async def _send_result(
        self,
        event: Message,
        lines: list[str],
    ) -> None:
        text = "\n".join(lines).strip()

        now = datetime.datetime.now(datetime.UTC)

        text += (
            "\n\n"
            f"<b><blockquote>"
            f"{self.fmtsec(now)}"
            f"</blockquote></b>"
        )

        await self.respond(event, text)

    @staticmethod
    def _kv(
        key: str,
        value: object,
    ) -> str:
        if value in (None, ""):
            value = "-"

        return (
            f"<b>{html.escape(str(key))}:</b> "
            f"<code>{html.escape(str(value))}</code>"
        )

    @staticmethod
    async def _get_creation_date(
        client,
        chat: Chat,
    ) -> str:
        try:
            if chat.type in (
                enums.ChatType.CHANNEL,
                enums.ChatType.SUPERGROUP,
            ):
                try:
                    first_msg = await client.get_messages(
                        chat.id,
                        1,
                    )

                    if first_msg and first_msg.date:
                        return first_msg.date.strftime(
                            "%Y-%m-%d %H:%M:%S"
                        )

                except Exception:
                    pass

            async for msg in client.get_chat_history(
                chat.id,
                limit=1,
                reverse=True,
            ):
                if msg.date:
                    return msg.date.strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )

        except Exception:
            pass

        return ""

    async def _get_admin_gban_lines(
        self,
        client,
        chat: Chat,
    ) -> list[str]:
        lines = []
        admins_ids = []

        prefix = "."

        if hasattr(self.client, "config"):
            cfg_prefix = self.client.config.get(
                "prefix",
                ".",
            )

            if isinstance(cfg_prefix, list):
                if cfg_prefix:
                    prefix = str(cfg_prefix[0])
            else:
                prefix = str(cfg_prefix)

        try:
            async for member in client.get_chat_members(
                chat.id,
                filter=enums.ChatMembersFilter.ADMINISTRATORS,
            ):
                if not member.user:
                    continue

                if (
                    member.status
                    == enums.ChatMemberStatus.OWNER
                ):
                    lines.append(
                        (
                            f'<code>{prefix}gban '
                            f'{member.user.id} '
                            f'"Spamadd[0x0 {chat.id}]"'
                            f"</code>"
                        )
                    )

                elif not member.user.is_bot:
                    admins_ids.append(
                        str(member.user.id)
                    )

            if admins_ids:
                lines.append(
                    (
                        f'<code>{prefix}gban '
                        f'{" ".join(admins_ids)} '
                        f'"Spamadd[0x1 {chat.id}]"'
                        f"</code>"
                    )
                )

        except Exception as e:
            lines.append(
                (
                    "<i>Could not fetch admins: "
                    f"{html.escape(str(e))}</i>"
                )
            )

        return lines

    def _append_user_chat_info(
        self,
        lines: list[str],
        user,
        chat,
        user_prefix: str,
        chat_prefix: str,
    ) -> None:
        if user:
            lines.append(
                self._kv(
                    f"{user_prefix} ID",
                    user.id,
                )
            )

            if getattr(user, "dc_id", None):
                lines.append(
                    self._kv(
                        f"{user_prefix} DC",
                        user.dc_id,
                    )
                )

        elif chat:
            lines.append(
                self._kv(
                    f"{chat_prefix} ID",
                    chat.id,
                )
            )

            if getattr(chat, "dc_id", None):
                lines.append(
                    self._kv(
                        f"{chat_prefix} DC",
                        chat.dc_id,
                    )
                )

    def _extract_forward_info(
        self,
        lines: list[str],
        message: Message,
    ) -> None:
        origin = getattr(
            message,
            "forward_origin",
            None,
        )

        if origin:
            lines.append("")
            self._add_origin_details(
                lines,
                origin,
            )
            return

        if message.forward_from_message_id:
            lines.append("")
            lines.append(
                self._kv(
                    "Forwarded Msg ID",
                    message.forward_from_message_id,
                )
            )

        if message.forward_from:
            lines.append(
                self._kv(
                    "Forwarded User ID",
                    message.forward_from.id,
                )
            )

            if getattr(
                message.forward_from,
                "dc_id",
                None,
            ):
                lines.append(
                    self._kv(
                        "Forwarded User DC",
                        message.forward_from.dc_id,
                    )
                )

            return

        if message.forward_from_chat:
            lines.append(
                self._kv(
                    "Forwarded Chat ID",
                    message.forward_from_chat.id,
                )
            )

            if getattr(
                message.forward_from_chat,
                "dc_id",
                None,
            ):
                lines.append(
                    self._kv(
                        "Forwarded Chat DC",
                        message.forward_from_chat.dc_id,
                    )
                )

            return

        if message.forward_sender_name:
            lines.append(
                self._kv(
                    "Forwarded From",
                    message.forward_sender_name,
                )
            )

    def _add_origin_details(
        self,
        lines: list[str],
        origin,
    ) -> None:
        if getattr(origin, "message_id", None):
            lines.append(
                self._kv(
                    "Forwarded Msg ID",
                    origin.message_id,
                )
            )

        if getattr(origin, "sender_user", None):
            user = origin.sender_user

            lines.append(
                self._kv(
                    "Forwarded User ID",
                    user.id,
                )
            )

            if getattr(user, "dc_id", None):
                lines.append(
                    self._kv(
                        "Forwarded User DC",
                        user.dc_id,
                    )
                )

            return

        if getattr(origin, "sender_chat", None):
            chat = origin.sender_chat

            lines.append(
                self._kv(
                    "Forwarded Chat ID",
                    chat.id,
                )
            )

            if getattr(chat, "dc_id", None):
                lines.append(
                    self._kv(
                        "Forwarded Chat DC",
                        chat.dc_id,
                    )
                )

            return

        sender_name = (
            getattr(origin, "sender_name", None)
            or getattr(origin, "hidden_user_name", None)
            or getattr(origin, "author_signature", None)
            or getattr(origin, "name", None)
        )

        lines.append(
            self._kv(
                "Forwarded From",
                sender_name or "Hidden user",
            )
        )
