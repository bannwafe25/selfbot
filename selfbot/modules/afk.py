import asyncio
import datetime
import html
import re

from pyrogram import filters
from pyrogram.errors import RPCError
from pyrogram.raw.functions.messages import ReadMentions
from pyrogram.raw.types import InputPeerChannel
from pyrogram.types import Message

from selfbot.listener import handler, reply
from selfbot.module import Module

AFK_PATTERN = re.compile(r"^afk(?:\s+([\s\S]+))?$", re.IGNORECASE)
UNAFK_PATTERN = re.compile(r"^unafk$", re.IGNORECASE)
SETAFKMSG_PATTERN = re.compile(r"^setafkmsg$", re.IGNORECASE)
DISPATCH_PATTERN = re.compile(
    r"^(?:afk|unafk|setafkmsg)(?:\s+[\s\S]+)?$", re.IGNORECASE
)


class AFK(Module):
    name = "Away From Keyboard"
    cmds = "{afk|unafk|setafkmsg} ..."
    desc = {
        "afk [reason]": "Go AFK with optional reason.",
        "unafk": "Manually disable AFK.",
        "setafkmsg": "Set custom AFK message (reply to a message).",
        "e.g.": "afk brb lunch",
    }

    status = False
    reason = ""
    since = None
    users = {}
    groups = {}
    custom_msg = None

    async def on_starting(self) -> None:
        try:
            await self.client.db.afk_meta.create_index([("_id", 1)], unique=True)
        except Exception:
            pass

        row = await self.client.db.afk_meta.find_one({"_id": "state"})
        if row and row.get("active"):
            self.status = True
            self.reason = row.get("reason", "")
            self.since = row.get("since")

        msg_row = await self.client.db.afk_meta.find_one({"_id": "custom_msg"})
        if msg_row:
            self.custom_msg = msg_row.get("text")

        self.lock = asyncio.Lock()

    @handler(filters.regex(DISPATCH_PATTERN), 1)
    async def on_message_out(self, event: Message) -> None:
        text = str(event.content).strip()

        if SETAFKMSG_PATTERN.match(text):
            await self._cmd_setafkmsg(event)
            return

        if UNAFK_PATTERN.match(text):
            await self._cmd_unafk(event)
            return

        m = AFK_PATTERN.match(text)
        if m:
            await self._cmd_afk(event, (m.group(1) or "").strip())
            return

    async def _cmd_afk(self, event: Message, reason: str) -> None:
        await self.respond(event, "<code>Going AFK...</code>")

        if self.status:
            await self.respond(
                event, "<code>Already AFK. Use unafk to disable first.</code>"
            )
            return

        self.status = True
        self.reason = reason
        self.since = datetime.datetime.now(datetime.UTC)
        self.users = {}
        self.groups = {}

        await self.client.db.afk_meta.update_one(
            {"_id": "state"},
            {
                "$set": {
                    "active": True,
                    "reason": reason,
                    "since": self.since,
                }
            },
            upsert=True,
        )

        await self.respond(
            event,
            self.fmtmsg(
                "Away From Keyboard",
                {
                    "Status": "Enabled",
                    "Reason": reason or "-",
                },
                self.fmtsec(self.since),
            ),
        )

    async def _cmd_unafk(self, event: Message) -> None:
        await self.respond(event, "<code>...</code>")

        if not self.status:
            await self.respond(event, "<code>You are not AFK.</code>")
            return

        total_msgs = sum(self.users.values()) + sum(self.groups.values())
        total_chats = len(self.users) + len(self.groups)
        elapsed = self.fmtsec(self.since, human=True)

        await self._cleanup_afk_replies()

        self.status = False
        self.reason = ""
        self.since = None
        self.users = {}
        self.groups = {}

        await asyncio.gather(
            self.client.db.afk_meta.update_one(
                {"_id": "state"},
                {"$set": {"active": False}},
                upsert=True,
            ),
            self.client.db.afk_msgs.delete_many({}),
        )

        await self.respond(
            event,
            self.fmtmsg(
                "Away From Keyboard",
                {
                    "Status": "Disabled",
                    "Away for": elapsed,
                    "Messages": str(total_msgs),
                    "Chats": str(total_chats),
                },
            ),
        )

    async def _cmd_setafkmsg(self, event: Message) -> None:
        await self.respond(event, "<code>...</code>")
        replied = event.reply_to_message

        if not replied:
            await self.respond(
                event,
                (
                    "<code>Reply to a message to set custom AFK text.</code>\n"
                    "<code>Use {reason} and {last_seen} as placeholders.</code>"
                ),
            )
            return

        msg_text = replied.text or replied.caption or ""
        if not msg_text:
            await self.respond(
                event, "<code>Reply to a text or caption message.</code>"
            )
            return

        if len(msg_text) > 200:
            await self.respond(
                event, "<code>Message too long. Max 200 characters.</code>"
            )
            return

        if "{reason}" not in msg_text or "{last_seen}" not in msg_text:
            await self.respond(
                event,
                (
                    "<code>Message must contain both {reason} and "
                    "{last_seen} placeholders.</code>"
                ),
            )
            return

        self.custom_msg = msg_text
        await self.client.db.afk_meta.update_one(
            {"_id": "custom_msg"},
            {"$set": {"text": msg_text}},
            upsert=True,
        )

        await self.respond(
            event,
            self.fmtmsg(
                "AFK Message Set",
                {"Template": msg_text},
            ),
        )

    @handler(~filters.private, 2)
    async def on_message_in(self, event: Message) -> None:
        if not self.status:
            return

        async with self.lock:
            is_group = hasattr(event.chat, "type") and str(
                event.chat.type
            ) in ("ChatType.SUPERGROUP", "ChatType.GROUP")
            tracker = self.groups if is_group else self.users
            chat_id = event.chat.id
            count = tracker.get(chat_id, 0)

            elapsed = self.fmtsec(self.since, human=True)

            if count == 0:
                if self.custom_msg:
                    text = self.custom_msg.format(
                        last_seen=elapsed, reason=self.reason or "-"
                    )
                else:
                    wib = self.since.astimezone(
                        datetime.timezone(datetime.timedelta(hours=7))
                    )
                    text = self.fmtmsg(
                        "Away From Keyboard",
                        {
                            "Since": wib.strftime("%B %-d, %-I:%M %p"),
                            "Timezone": "UTC+7\n",
                            "Reason": self.reason or "-",
                        },
                        elapsed,
                    )
            elif count >= 50:
                if count == 50:
                    text = (
                        "<b>I'm still AFK.</b>\n\n"
                        "<code>This is the last auto-reply for this chat.</code>"
                    )
                else:
                    tracker[chat_id] = count + 1
                    return
            elif count % 5 == 0:
                text = self.fmtmsg(
                    "Still AFK",
                    {
                        "Away for": elapsed,
                        "Reason": self.reason or "-",
                    },
                )
            else:
                tracker[chat_id] = count + 1
                await self._read_and_notify(event)
                return

            new = await self.respond(event, text, reply=True)
            old_doc = await self.client.db.afk_msgs.find_one({"chat_id": chat_id})

            if old_doc:
                try:
                    await event._client.delete_messages(
                        chat_id, old_doc["message_id"]
                    )
                except RPCError:
                    pass
                await self.client.db.afk_msgs.update_one(
                    {"chat_id": chat_id},
                    {"$set": {"message_id": new.id}},
                )
            else:
                await self.client.db.afk_msgs.insert_one(
                    {"chat_id": chat_id, "message_id": new.id}
                )

            tracker[chat_id] = count + 1
            await self._read_and_notify(event)

    @handler(filters.me & filters.private, 3)
    async def on_message_self(self, event: Message) -> None:
        """Auto-unset AFK when user sends a message."""
        if not self.status:
            return

        text = str(getattr(event, "content", "") or "").strip()
        if DISPATCH_PATTERN.match(text):
            return

        total_msgs = sum(self.users.values()) + sum(self.groups.values())
        total_chats = len(self.users) + len(self.groups)
        elapsed = self.fmtsec(self.since, human=True)

        await self._cleanup_afk_replies()

        self.status = False
        self.reason = ""
        self.since = None
        self.users = {}
        self.groups = {}

        await asyncio.gather(
            self.client.db.afk_meta.update_one(
                {"_id": "state"},
                {"$set": {"active": False}},
                upsert=True,
            ),
            self.client.db.afk_msgs.delete_many({}),
        )

        msg = await event.reply(
            f"<code>Back online! Away for {html.escape(elapsed)}, "
            f"received {total_msgs} messages from {total_chats} chats.</code>"
        )
        await asyncio.sleep(5)
        try:
            await msg.delete()
        except RPCError:
            pass

    async def _read_and_notify(self, event: Message) -> None:
        """Read mentions and send notification sticker."""
        try:
            peer = await event._client.resolve_peer(event.chat.id)
            if isinstance(peer, InputPeerChannel):
                chat_id = peer.channel_id
            else:
                chat_id = peer.chat_id

            await asyncio.gather(
                event._client.invoke(ReadMentions(peer=peer)),
                self.client.bot.send_sticker(
                    event._client.me.id,
                    self.client.config["STICKER_FILE_ID"],
                    disable_notification=True,
                    reply_markup=self.ikm(
                        (
                            "Message",
                            "url",
                            f"tg://openmessage?chat_id={chat_id}&message_id={event.id}",
                            "B",
                        )
                    ),
                ),
            )
        except Exception:
            pass

    async def _cleanup_afk_replies(self) -> None:
        """Delete all stored AFK auto-reply messages."""
        cursor = self.client.db.afk_msgs.find()
        async for row in cursor:
            try:
                # need a client reference; use the first available
                for name, client in self.client.clients.items():
                    await client.delete_messages(
                        row["chat_id"], row["message_id"]
                    )
                    break
            except (RPCError, Exception):
                continue
