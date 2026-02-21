import asyncio
import datetime
import re

from pyrogram import filters
from pyrogram.errors import RPCError
from pyrogram.raw.functions.messages import ReadMentions
from pyrogram.raw.types import InputPeerChannel
from pyrogram.types import Message

from selfbot.listener import handler, reply
from selfbot.module import Module

pattern = re.compile(r"^afk(?:\s-r\s(.+))?$")


class AFK(Module):
    name = "Away From Keyboard"
    cmds = "afk (-r {reason})?"
    desc = {
        "afk": "Toggle",
        "reason": "String",
        "?": "Optional",
        "e.g.": "afk -r Hello, World!",
    }
    status, reason, since = False, "", None

    async def on_starting(self) -> None:
        row = await self.client.db.afk_meta.find_one()
        if row:
            self.status = True
            self.reason, self.since = row["reason"], row["since"]

        self.lock = asyncio.Lock()

    @handler(filters.regex(pattern) & ~reply, 1)
    async def on_message_out(self, event: Message) -> None:
        await self.respond(event, "<code>...</code>")
        since, (reason,) = (
            datetime.datetime.now(datetime.UTC),
            pattern.match(event.content).groups(),
        )
        if self.status:
            meta = await self.client.db.afk_meta.find_one()
            since = meta["since"] if meta else self.since
            cursor = self.client.db.afk_msgs.find()
            rows = []
            async for row in cursor:
                rows.append(row)

            for row in rows:
                try:
                    await event._client.delete_messages(
                        row["chat_id"], row["message_id"]
                    )
                except RPCError:
                    continue

            await asyncio.gather(
                self.client.db.afk_meta.delete_many({}),
                self.client.db.afk_msgs.delete_many({})
            )
            self.status, self.reason, self.since = False, "", None
        else:
            await self.client.db.afk_meta.insert_one({"reason": reason, "since": since})
            self.status, self.reason, self.since = True, reason, since

        await self.respond(
            event,
            self.fmtmsg(
                "Away From Keyboard",
                {"Status": self.status, "Reason": reason},
                self.fmtsec(since),
            ),
        )

    @handler(~filters.private, 2)
    async def on_message_in(self, event: Message) -> None:
        if not self.status:
            return

        async with self.lock:
            wib = self.since.astimezone(datetime.timezone(datetime.timedelta(hours=7)))
            new, old_doc = await asyncio.gather(
                self.respond(
                    event,
                    self.fmtmsg(
                        "Away From Keyboard",
                        {
                            "Since": wib.strftime("%B %-d, %-I:%M %p"),
                            "Timezone": "UTC+7\n",
                            "Reason": self.reason,
                        },
                        self.fmtsec(self.since, human=True),
                    ),
                    reply=True,
                ),
                self.client.db.afk_msgs.find_one({"chat_id": event.chat.id}),
            )
            if old_doc:
                await asyncio.gather(
                    event._client.delete_messages(event.chat.id, old_doc["message_id"]),
                    self.client.db.afk_msgs.update_one(
                        {"chat_id": event.chat.id},
                        {"$set": {"message_id": new.id}}
                    ),
                )
            else:
                await self.client.db.afk_msgs.insert_one(
                    {"chat_id": event.chat.id, "message_id": new.id}
                )

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
