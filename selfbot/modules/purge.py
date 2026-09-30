import asyncio
import datetime
import html
import re

from pyrogram import filters
from pyrogram.enums import ChatType
from pyrogram.types import Message

from selfbot.listener import handler
from selfbot.module import Module

pattern = re.compile(r"^purge(me)?(?:\s-l\s([1-9]\d{0,2}))?$")


class Purge(Module):
    name = "Purge Message"
    cmds = "<Reply>? purge(me)? (-l {limit})?"
    desc = {
        "Reply": "Min ID",
        "limit": "[1-999]",
        "?": "Optional",
        "e.g.": "purgeme -l 99",
    }

    @handler(filters.regex(pattern), 1)
    async def on_message_out(self, event: Message) -> None:
        await self.respond(event, "<code>...</code>")
        me, limit = pattern.match(event.content).groups()
        if limit:
            limit = int(limit)

        mids = []
        if me:
            mids = [
                m.id
                async for m in event._client.search_messages(
                    event.chat.id,
                    from_user="me",
                    message_thread_id=event.message_thread_id,
                    limit=(limit or 100) + 1,
                    min_id=(event.reply_to_message_id or 1) - 1,
                    max_id=event.id,
                )
            ]
        else:
            if (
                event.chat.type == ChatType.SUPERGROUP
                and (event.chat.is_direct_messages or event.chat.is_forum)
            ) or (event.chat.type == ChatType.BOT and event.message_thread_id):
                await self.respond(
                    event,
                    f"<code>Unsupported {html.escape('<ChatType>')}</code>",
                    revoke=2.5,
                )
                return

            mids = [
                m.id
                async for m in event._client.get_chat_history(
                    event.chat.id,
                    limit=limit or 100,
                    min_id=(event.reply_to_message_id or 1) - 1,
                    max_id=event.id,
                )
            ]

        res, now = 0, datetime.datetime.now(datetime.UTC)
        for chunk in (mids[i : i + 100] for i in range(0, len(mids), 100)):
            res += await event._client.delete_messages(event.chat.id, chunk)
            if len(mids) > 100 and res % 100 == 0:
                await asyncio.sleep(2.5)

        await self.respond(
            event,
            self.fmtmsg(
                f"Purge{'me' if me else ''}",
                f"{res} Message{'' if res == 1 else 's'}",
                self.fmtsec(now),
            ),
            revoke=2.5,
        )
