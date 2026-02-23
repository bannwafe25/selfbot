import contextlib
import datetime
import html
import inspect
import re
from typing import ClassVar

from pyrogram import filters
from pyrogram.enums import ChatType
from pyrogram.errors import ChatAdminRequired, RPCError, UserAdminInvalid
from pyrogram.types import ChatPermissions, LinkPreviewOptions, Message, User

from selfbot.listener import handler, reply
from selfbot.module import Module

pattern = re.compile(r"^(antich|antiraid|welcome|ro|unro)(?:\s+([\s\S]+))?$", re.IGNORECASE)

DEFAULT_SETTINGS = {
    "antich": False,
    "antiraid": False,
    "linked_chat_id": 0,
    "welcome_enabled": False,
    "welcome_text": "",
    "ro_enabled": False,
    "ro_permissions": {},
}


class AdminTool(Module):
    name = "Admin Tools"
    cmds = "{antich|antiraid|welcome|ro|unro} ..."
    desc = {
        "antich": "Anti anonymous/channel sender in current group.",
        "antiraid": "Delete and ban every new sender in current group.",
        "welcome": "Set welcome text. Empty arg disables welcome.",
        "ro": "Enable read-only mode for non-admins.",
        "unro": "Disable read-only mode and restore saved permissions.",
        "e.g.": "welcome Welcome {mention} to {chat_title}",
    }

    permission_fields: ClassVar[tuple[str, ...]] = (
        tuple(
            name
            for name in inspect.signature(ChatPermissions.__init__).parameters
            if name != "self"
        )
        or tuple(getattr(ChatPermissions, "__annotations__", {}).keys())
        or (
            "can_send_messages",
            "can_send_media_messages",
            "can_send_polls",
            "can_send_other_messages",
            "can_add_web_page_previews",
            "can_change_info",
            "can_invite_users",
            "can_pin_messages",
            "can_manage_topics",
        )
    )

    async def on_starting(self) -> None:
        try:
            await self.client.db.admintool_settings.create_index(
                [("chat_id", 1)], unique=True
            )
        except Exception:
            pass

        self.cache = {}
        cursor = self.client.db.admintool_settings.find()
        async for row in cursor:
            chat_id = row.get("chat_id")
            if isinstance(chat_id, int):
                self.cache[chat_id] = self._normalize_settings(row)

    @handler(filters.regex(pattern) & ~reply, 1)
    async def on_message_out(self, event: Message) -> None:
        await self.respond(event, "<code>Processing...</code>")
        now = datetime.datetime.now(datetime.UTC)

        command, args = pattern.match(str(event.content).strip()).groups()
        command = command.lower()
        args = (args or "").strip()

        if event.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
            await self.respond(
                event, "<code>This command only works in groups/supergroups.</code>"
            )
            return

        if command == "antich":
            await self._cmd_antich(event, args, now)
            return
        if command == "antiraid":
            await self._cmd_antiraid(event, args, now)
            return
        if command == "welcome":
            await self._cmd_welcome(event, args, now)
            return
        if command == "ro":
            await self._cmd_ro(event, now)
            return
        if command == "unro":
            await self._cmd_unro(event, now)
            return

    @handler(filters.group, 2)
    async def on_app(self, event: Message) -> None:
        if event.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
            return

        settings = self.cache.get(event.chat.id)
        if not settings:
            return

        if not any(
            (
                settings["antich"],
                settings["antiraid"],
                settings["welcome_enabled"],
            )
        ):
            return

        sender_chat = event.sender_chat
        linked_chat_id = int(settings.get("linked_chat_id") or 0)
        if sender_chat and (
            sender_chat.type == ChatType.SUPERGROUP
            or (linked_chat_id and sender_chat.id == linked_chat_id)
        ):
            return

        if settings["antich"] and sender_chat:
            await self._delete_and_ban(event, sender_chat.id)
            return

        if settings["antiraid"]:
            target_id = (
                event.from_user.id
                if event.from_user
                else (sender_chat.id if sender_chat else None)
            )
            if target_id:
                await self._delete_and_ban(event, target_id)
                return

        if settings["welcome_enabled"] and event.new_chat_members:
            welcome_text = settings.get("welcome_text") or (
                "Welcome {mention} to <b>{chat_title}</b>."
            )
            text = self._format_welcome_text(
                welcome_text, event.new_chat_members[0], event.chat
            )
            with contextlib.suppress(RPCError):
                await event.reply_text(
                    text,
                    link_preview_options=LinkPreviewOptions(is_disabled=True),
                )

    async def _cmd_antich(self, event: Message, args: str, now: datetime.datetime) -> None:
        settings = self._get_settings(event.chat.id)
        state = self._resolve_toggle(args, settings["antich"])
        if state is None:
            await self.respond(event, "<code>Usage: antich [enable|disable]</code>")
            return

        linked_chat_id = 0
        if state:
            chat = await event._client.get_chat(event.chat.id)
            linked = getattr(chat, "linked_chat", None)
            linked_chat_id = int(getattr(linked, "id", 0) or 0)

        await self._update_settings(
            event.chat.id,
            antich=state,
            linked_chat_id=linked_chat_id if state else settings["linked_chat_id"],
        )
        await self.respond(
            event,
            self.fmtmsg(
                "Admin Tools",
                {
                    "Anti Channel": state,
                    "Linked Chat": linked_chat_id or "-",
                },
                self.fmtsec(now),
            ),
        )

    async def _cmd_antiraid(
        self, event: Message, args: str, now: datetime.datetime
    ) -> None:
        settings = self._get_settings(event.chat.id)
        state = self._resolve_toggle(args, settings["antiraid"])
        if state is None:
            await self.respond(event, "<code>Usage: antiraid [on|off]</code>")
            return

        linked_chat_id = settings["linked_chat_id"]
        if state:
            chat = await event._client.get_chat(event.chat.id)
            linked = getattr(chat, "linked_chat", None)
            linked_chat_id = int(getattr(linked, "id", 0) or 0)

        await self._update_settings(
            event.chat.id,
            antiraid=state,
            linked_chat_id=linked_chat_id,
        )
        await self.respond(
            event,
            self.fmtmsg(
                "Admin Tools",
                {
                    "Anti Raid": state,
                    "Linked Chat": linked_chat_id or "-",
                },
                self.fmtsec(now),
            ),
        )

    async def _cmd_welcome(
        self, event: Message, args: str, now: datetime.datetime
    ) -> None:
        if not args or args.lower() in {"disable", "off", "0", "no", "false"}:
            await self._update_settings(
                event.chat.id, welcome_enabled=False, welcome_text=""
            )
            await self.respond(
                event,
                self.fmtmsg(
                    "Admin Tools",
                    {"Welcome": False},
                    self.fmtsec(now),
                ),
            )
            return

        await self._update_settings(event.chat.id, welcome_enabled=True, welcome_text=args)
        await self.respond(
            event,
            self.fmtmsg(
                "Admin Tools",
                {"Welcome": True},
                self.fmtsec(now),
                args,
            ),
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )

    async def _cmd_ro(self, event: Message, now: datetime.datetime) -> None:
        settings = self._get_settings(event.chat.id)
        if settings["ro_enabled"]:
            await self.respond(
                event,
                "<code>Read-only mode is already enabled. Use unro to disable.</code>",
            )
            return

        try:
            current = self._permissions_to_dict(event.chat.permissions)
            await event._client.set_chat_permissions(event.chat.id, ChatPermissions())
        except (UserAdminInvalid, ChatAdminRequired):
            await self.respond(event, "<code>No rights to change chat permissions.</code>")
            return
        except RPCError as e:
            await self.respond(event, f"<code>{html.escape(str(e))}</code>")
            return

        await self._update_settings(
            event.chat.id, ro_enabled=True, ro_permissions=current
        )
        await self.respond(
            event,
            self.fmtmsg("Admin Tools", {"Read Only": True}, self.fmtsec(now)),
        )

    async def _cmd_unro(self, event: Message, now: datetime.datetime) -> None:
        settings = self._get_settings(event.chat.id)
        if not settings["ro_enabled"]:
            await self.respond(
                event,
                "<code>Read-only mode is not enabled in this chat.</code>",
            )
            return

        raw = settings.get("ro_permissions") or {}
        perms_data = {k: bool(v) for k, v in raw.items() if k in self.permission_fields}
        if not perms_data:
            perms_data = {"can_send_messages": True}

        try:
            await event._client.set_chat_permissions(
                event.chat.id, ChatPermissions(**perms_data)
            )
        except (UserAdminInvalid, ChatAdminRequired):
            await self.respond(event, "<code>No rights to change chat permissions.</code>")
            return
        except RPCError as e:
            await self.respond(event, f"<code>{html.escape(str(e))}</code>")
            return

        await self._update_settings(
            event.chat.id, ro_enabled=False, ro_permissions={}
        )
        await self.respond(
            event,
            self.fmtmsg("Admin Tools", {"Read Only": False}, self.fmtsec(now)),
        )

    async def _delete_and_ban(self, event: Message, target_id: int) -> None:
        with contextlib.suppress(RPCError):
            await event.delete()
        with contextlib.suppress(RPCError):
            await event.chat.ban_member(target_id)

    def _get_settings(self, chat_id: int) -> dict:
        if chat_id not in self.cache:
            self.cache[chat_id] = self._normalize_settings({})
        return self.cache[chat_id]

    async def _update_settings(self, chat_id: int, **updates: object) -> None:
        current = self._get_settings(chat_id).copy()
        current.update(updates)
        current["chat_id"] = chat_id
        self.cache[chat_id] = self._normalize_settings(current)
        payload = self.cache[chat_id].copy()
        payload["updated_at"] = datetime.datetime.now(datetime.UTC)
        await self.client.db.admintool_settings.update_one(
            {"chat_id": chat_id},
            {"$set": payload},
            upsert=True,
        )

    @staticmethod
    def _resolve_toggle(args: str, current_state: bool) -> bool | None:
        if not args:
            return not current_state
        arg = args.split(maxsplit=1)[0].lower()
        if arg in {"enable", "enabled", "on", "1", "yes", "true"}:
            return True
        if arg in {"disable", "disabled", "off", "0", "no", "false"}:
            return False
        return None

    def _normalize_settings(self, row: dict) -> dict:
        data = {**DEFAULT_SETTINGS}
        data.update({k: row[k] for k in data.keys() if k in row})
        data["antich"] = bool(data["antich"])
        data["antiraid"] = bool(data["antiraid"])
        data["welcome_enabled"] = bool(data["welcome_enabled"])
        data["ro_enabled"] = bool(data["ro_enabled"])
        data["linked_chat_id"] = int(data["linked_chat_id"] or 0)
        if not isinstance(data.get("ro_permissions"), dict):
            data["ro_permissions"] = {}
        if not isinstance(data.get("welcome_text"), str):
            data["welcome_text"] = ""
        return data

    def _permissions_to_dict(self, perms: ChatPermissions | None) -> dict:
        if not perms:
            return {}
        data = {}
        for field in self.permission_fields:
            value = getattr(perms, field, None)
            if isinstance(value, bool):
                data[field] = value
        return data

    @staticmethod
    def _format_welcome_text(text: str, user: User, chat) -> str:
        first = html.escape(user.first_name or "")
        last = html.escape(user.last_name or "")
        fullname = f"{first} {last}".strip()
        username = (
            f"@{html.escape(user.username)}"
            if getattr(user, "username", None)
            else user.mention(first or "User")
        )
        mention = user.mention(first or "User")
        chat_title = html.escape(getattr(chat, "title", None) or "Group")
        user_id = str(user.id)
        chat_id = str(chat.id)

        return (
            text.replace("{first}", first)
            .replace("{last}", last)
            .replace("{fullname}", fullname)
            .replace("{username}", username)
            .replace("{mention}", mention)
            .replace("{id}", user_id)
            .replace("{chat_id}", chat_id)
            .replace("{chat_title}", chat_title)
        )
