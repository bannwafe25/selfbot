import asyncio
import datetime
import html
import re

from pyrogram import filters
from pyrogram.types import Message, ReplyParameters

from selfbot.listener import handler, reply
from selfbot.module import Module

QUOTLY_BOT_ID = 1031952739
QUOTLY_TIMEOUT = 20
ERROR_VISIBLE_DURATION = 8

pattern = re.compile(r"^(q|quotly)(?:\s+(.+))?$")


class Quotly(Module):
    name = "Quotly"
    cmds = "<Reply to Message> q(uotly)? {color}? {count}?"
    desc = {
        "Info": "Creates a quote by forwarding messages to @QuotLyBot.",
        "color": "Color name or hex code (optional).",
        "count": "Number of messages to quote (1-10, optional).",
        "e.g.": "<Reply to Message> q red 3",
    }

    @staticmethod
    def _parse_arguments(args_str: str) -> tuple[str | None, int]:
        if not args_str:
            return None, 1

        color = None
        count = 1
        for part in args_str.split():
            if part.isdigit():
                count = max(1, min(int(part), 10))
            elif part.startswith("#") or part.isalpha():
                color = part

        return color, count

    @handler(filters.regex(pattern) & reply, 1)
    async def on_message_out(self, event: Message) -> None:
        if not event.reply_to_message:
            await self._edit_and_delete(
                event, "<code>Please reply to a message to quote.</code>"
            )
            return

        match = pattern.match(event.content)
        args_str = match.group(2) if match else ""
        color, count = self._parse_arguments(args_str or "")

        progress = await self.respond(event, f"<code>Fetching {count} message(s)...</code>")
        try:
            message_ids = await self._collect_message_ids(event, count)
        except Exception as e:
            await self._edit_and_delete(
                progress, f"<code>Failed to fetch messages: {html.escape(str(e))}</code>"
            )
            return

        if not message_ids:
            await self._edit_and_delete(
                progress, "<code>Could not find valid messages to quote.</code>"
            )
            return

        await self.respond(
            progress,
            f"<code>Forwarding {len(message_ids)} message(s) to @QuotLyBot...</code>",
        )

        try:
            start_time = datetime.datetime.now(datetime.UTC)

            if color:
                with_color = f"/qcolor {color}"
                await event._client.send_message(QUOTLY_BOT_ID, with_color)
                await asyncio.sleep(0.8)

            await event._client.forward_messages(
                chat_id=QUOTLY_BOT_ID,
                from_chat_id=event.chat.id,
                message_ids=message_ids,
            )

            quotly_response = await self._find_quotly_response(
                event._client, start_time, QUOTLY_TIMEOUT
            )
            if not quotly_response:
                raise asyncio.TimeoutError("@QuotLyBot did not respond in time.")

            await progress.delete()
            reply_to_id = event.reply_to_message_id or event.reply_to_message.id
            try:
                await event._client.copy_message(
                    chat_id=event.chat.id,
                    from_chat_id=QUOTLY_BOT_ID,
                    message_id=quotly_response.id,
                    reply_parameters=ReplyParameters(message_id=reply_to_id),
                )
            except TypeError:
                await event._client.copy_message(
                    chat_id=event.chat.id,
                    from_chat_id=QUOTLY_BOT_ID,
                    message_id=quotly_response.id,
                    reply_to_message_id=reply_to_id,
                )
            await event.delete()
        except Exception as e:
            error_text = (
                "<b>Error:</b> Could not get a quote from @QuotLyBot.\n"
                f"<code>{html.escape(str(e)[:300])}</code>"
            )
            await self._edit_and_delete(progress, error_text)

    async def _collect_message_ids(self, event: Message, count: int) -> list[int]:
        replied = event.reply_to_message
        if count <= 1:
            return [replied.id]

        start_id = max(1, replied.id - count + 1)
        ids = list(range(start_id, replied.id + 1))
        msgs = await event._client.get_messages(
            chat_id=event.chat.id,
            message_ids=ids,
        )
        return [msg.id for msg in msgs if msg]

    async def _find_quotly_response(
        self, client, start_time: datetime.datetime, timeout: int
    ) -> Message | None:
        end_time = start_time + datetime.timedelta(seconds=timeout)
        start_ts = start_time.timestamp()
        seen = set()

        while datetime.datetime.now(datetime.UTC) < end_time:
            try:
                async for message in client.get_chat_history(QUOTLY_BOT_ID, limit=10):
                    if not message or message.id in seen:
                        continue
                    seen.add(message.id)

                    if not message.from_user or message.from_user.id != QUOTLY_BOT_ID:
                        continue

                    msg_dt = message.date
                    if msg_dt.tzinfo is None:
                        msg_dt = msg_dt.replace(tzinfo=datetime.UTC)
                    if msg_dt.timestamp() < start_ts:
                        continue

                    if message.media or message.text:
                        return message
            except Exception as e:
                self.logger.debug(f"Error checking QuotLyBot response: {e}")

            await asyncio.sleep(1)

        return None

    async def _edit_and_delete(self, message: Message, text: str) -> None:
        try:
            await message.edit_text(text)
            await asyncio.sleep(ERROR_VISIBLE_DURATION)
            await message.delete()
        except Exception as e:
            self.logger.debug(f"Failed to edit/delete status message: {e}")
