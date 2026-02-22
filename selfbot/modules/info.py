import datetime
import html
import re

from pyrogram import enums, filters
from pyrogram.enums import ChatMemberStatus, ChatType, UserStatus
from pyrogram.errors import RPCError, UserIsBlocked
from pyrogram.types import LinkPreviewOptions, Message, User

from selfbot.listener import handler
from selfbot.module import Module

pattern = re.compile(r"^info(?:\s+(.+))?$", flags=re.DOTALL)


class Info(Module):
    name = "Info"
    cmds = "info {user_id|username}? (-full)?"
    desc = {
        "user_id|username": "User ID or username target.",
        "?": "Optional. Reply to a message or get self info.",
        "-full": "Show detailed information.",
        "e.g.": "info @username",
    }

    @handler(filters.regex(pattern), 1)
    async def on_message_out(self, event: Message) -> None:
        await self.respond(event, "<code>Fetching user information...</code>")
        now = datetime.datetime.now(datetime.UTC)

        input_str = (pattern.match(event.content).group(1) or "").strip()
        tokens = [token for token in input_str.split() if token]
        is_full_mode = False
        cleaned = []
        for token in tokens:
            if token.lower() == "-full":
                is_full_mode = True
            else:
                cleaned.append(token)

        target_identifier = " ".join(cleaned).strip()
        if not target_identifier:
            if event.reply_to_message and event.reply_to_message.from_user:
                target_identifier = event.reply_to_message.from_user.id
            elif event.from_user:
                target_identifier = event.from_user.id
            else:
                await self.respond(event, "<code>Unable to resolve target user.</code>")
                return

        if isinstance(target_identifier, str) and target_identifier.lstrip("-").isdigit():
            target_identifier = int(target_identifier)

        try:
            res = await event._client.get_users(target_identifier)
            if isinstance(res, list):
                user = res[0] if res else None
            else:
                user = res
            if not isinstance(user, User):
                user = None

            if not user:
                await self.respond(
                    event,
                    f"<code>User '{html.escape(str(target_identifier))}' not found.</code>",
                )
                return

            caption, photo_id = await self._format_user_info(user, is_full_mode, event)
            caption += f"\n\n<b><blockquote>{self.fmtsec(now)}</blockquote></b>"

            if photo_id:
                try:
                    photo = await event._client.download_media(photo_id, in_memory=True)
                    await event.delete()
                    await event.reply_photo(photo=photo, caption=caption)
                except Exception as e:
                    self.logger.warning(f"Failed to download profile photo: {e}")
                    await self.respond(
                        event,
                        caption,
                        link_preview_options=LinkPreviewOptions(is_disabled=True),
                    )
            else:
                await self.respond(
                    event, caption, link_preview_options=LinkPreviewOptions(is_disabled=True)
                )
        except RPCError as e:
            await self.respond(
                event, f"<b>RPCError:</b> <code>{html.escape(str(e))}</code>"
            )
        except Exception as e:
            await self.respond(event, f"<b>Error:</b> <code>{html.escape(str(e))}</code>")

    def _get_user_status(self, user: User) -> str:
        if not user.status:
            return "N/A"

        if user.status == UserStatus.OFFLINE:
            dt = user.last_online_date
            if dt:
                return dt.strftime("%d %b %Y, %H:%M")
            return "Offline"

        status_map = {
            UserStatus.ONLINE: "Online",
            UserStatus.RECENTLY: "Recently",
            UserStatus.LAST_WEEK: "Within a week",
            UserStatus.LAST_MONTH: "Within a month",
        }
        return status_map.get(user.status, "Long time ago")

    async def _format_user_info(
        self, user: User, is_full: bool, message: Message
    ) -> tuple[str, str | None]:
        full_chat_info = None
        try:
            full_chat_info = await message._client.get_chat(user.id)
        except Exception:
            pass

        def esc(value: object) -> str:
            return html.escape(str(value)) if value else ""

        if is_full:
            lines = [
                "<b>User Info:</b>",
                f"• <b>ID:</b> <code>{user.id}</code>",
                f"• <b>First Name:</b> {esc(user.first_name)}",
            ]
            if user.last_name:
                lines.append(f"• <b>Last Name:</b> {esc(user.last_name)}")
            if user.username:
                lines.append(f"• <b>Username:</b> @{user.username}")
            if getattr(user, "dc_id", None):
                lines.append(f"• <b>DC ID:</b> {user.dc_id}")
            if getattr(user, "language_code", None):
                lines.append(f"• <b>Language:</b> {user.language_code}")

            sender_id = message.from_user.id if message.from_user else 0
            if user.id != sender_id:
                try:
                    common = await self.client.app.get_common_chats(user.id)
                    lines.append(f"• <b>Common Groups:</b> {len(common)}")
                except Exception:
                    pass

                try:
                    await self.client.app.send_chat_action(user.id, enums.ChatAction.TYPING)
                    lines.append("• <b>You Blocked:</b> No ✅")
                except UserIsBlocked:
                    lines.append("• <b>You Blocked:</b> Yes ⛔️")
                except Exception:
                    pass

            flags = []
            if user.is_bot:
                flags.append("Bot 🤖")
            if user.is_verified:
                flags.append("Verified ✅")
            if user.is_scam:
                flags.append("Scam ‼️")
            if user.is_premium:
                flags.append("Premium ✨")
            if flags:
                lines.append(f"• <b>Flags:</b> {', '.join(flags)}")

            try:
                reg = await self.client.http.get(
                    "https://yasirapi.eu.org/register_date",
                    params={"user_id": user.id, "tz": "UTC"},
                    timeout=10,
                )
                if reg.status_code == 200:
                    data = reg.json()
                    if data.get("success") and data.get("reg_date"):
                        lines.append(
                            f"• <b>Registration Date:</b> {esc(data.get('reg_date'))} UTC"
                        )
            except Exception as e:
                self.logger.debug(f"Failed to fetch registration date: {e}")

            lines.append(f"• <b>Last Seen:</b> {self._get_user_status(user)}")

            bio = getattr(full_chat_info, "bio", None) if full_chat_info else None
            if bio:
                lines.append(f"• <b>Bio:</b> {esc(bio)}")

            try:
                photos_count = await message._client.get_chat_photos_count(user.id)
                if photos_count > 0:
                    lines.append(f"• <b>Profile Photos:</b> {photos_count}")
            except Exception:
                pass

            if message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
                try:
                    member = await message._client.get_chat_member(message.chat.id, user.id)
                    lines.append("\n<b>Group Info:</b>")

                    status_map = {
                        ChatMemberStatus.OWNER: "Owner",
                        ChatMemberStatus.ADMINISTRATOR: "Administrator",
                        ChatMemberStatus.MEMBER: "Member",
                        ChatMemberStatus.RESTRICTED: "Restricted",
                        ChatMemberStatus.LEFT: "Not in chat",
                        ChatMemberStatus.BANNED: "Banned",
                    }
                    status_str = status_map.get(member.status, "Unknown")
                    if getattr(member, "custom_title", None):
                        status_str += f" (Title: {esc(member.custom_title)})"

                    group_lines = [f"• <b>Status:</b> {status_str}"]

                    joined_date = getattr(member, "joined_date", None)
                    if joined_date:
                        group_lines.append(
                            f"• <b>Joined:</b> {joined_date.strftime('%d %b %Y, %H:%M UTC')}"
                        )

                    promoted_by = getattr(member, "promoted_by", None)
                    if promoted_by:
                        group_lines.append(
                            f"• <b>Promoted By:</b> {self._user_link(promoted_by)}"
                        )

                    privileges = getattr(member, "privileges", None)
                    if privileges:
                        perms = [
                            ("– Manage Chat", getattr(privileges, "can_manage_chat", False)),
                            (
                                "– Delete Messages",
                                getattr(privileges, "can_delete_messages", False),
                            ),
                            (
                                "– Manage Video Chats",
                                getattr(privileges, "can_manage_video_chats", False),
                            ),
                            (
                                "– Restrict Members",
                                getattr(privileges, "can_restrict_members", False),
                            ),
                            ("– Change Info", getattr(privileges, "can_change_info", False)),
                            (
                                "– Invite Users",
                                getattr(privileges, "can_invite_users", False),
                            ),
                            ("– Pin Messages", getattr(privileges, "can_pin_messages", False)),
                            ("– Post Stories", getattr(privileges, "can_post_stories", False)),
                            ("– Edit Stories", getattr(privileges, "can_edit_stories", False)),
                            (
                                "– Delete Stories",
                                getattr(privileges, "can_delete_stories", False),
                            ),
                        ]
                        granted = [text for text, ok in perms if ok]
                        if granted:
                            group_lines.append(
                                "• <b>Permissions:</b><br>" + "<br>".join(granted)
                            )

                    lines.append(f"<blockquote>{'<br>'.join(group_lines)}</blockquote>")
                except Exception:
                    pass

            lines.append(f"\n<b>Permalink:</b> {self._user_link(user, 'Click Here')}")
        else:
            lines = [
                "<b>User Info:</b>",
                f"• <b>ID:</b> <code>{user.id}</code>",
                f"• <b>First Name:</b> {esc(user.first_name)}",
            ]
            if user.last_name:
                lines.append(f"• <b>Last Name:</b> {esc(user.last_name)}")
            if user.username:
                lines.append(f"• <b>Username:</b> @{user.username}")

            if message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
                try:
                    member = await message._client.get_chat_member(message.chat.id, user.id)
                    status_map = {
                        ChatMemberStatus.OWNER: "Owner",
                        ChatMemberStatus.ADMINISTRATOR: "Admin",
                        ChatMemberStatus.MEMBER: "Member",
                        ChatMemberStatus.RESTRICTED: "Restricted",
                        ChatMemberStatus.LEFT: "Not in chat",
                        ChatMemberStatus.BANNED: "Banned",
                    }
                    if member.status in status_map:
                        lines.append(f"• <b>Status:</b> {status_map[member.status]}")
                except Exception:
                    pass

            lines.append(f"\n<b>Permalink:</b> {self._user_link(user, 'Click Here')}")

        photo = getattr(full_chat_info, "photo", None) if full_chat_info else None
        photo_id = getattr(photo, "big_file_id", None) if photo else None
        return "\n".join(lines), photo_id

    @staticmethod
    def _user_link(user: User, text: str | None = None) -> str:
        label = html.escape(text or user.first_name or "User")
        return f"<a href='tg://user?id={user.id}'>{label}</a>"
