import asyncio
import struct

from pyrogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQuery,
    InlineQueryResultCachedSticker,
    InputTextMessageContent,
    Message,
    ReplyParameters,
    Update,
)
from pyrogram.utils import (
    MIN_MONOFORUM_CHANNEL_ID,
    get_channel_id,
    unpack_inline_message_id,
)


class Telegram:
    async def answer(
        self,
        event: InlineQuery,
        reply_markup: InlineKeyboardMarkup = None,
        message_text: str = "",
        *args,
        **kwargs,
    ) -> None:
        if not reply_markup:
            reply_markup = self.ikm((">_", "user_id", event._client.me.id))

        if not message_text:
            message_text = "<code>...</code>"

        await event.answer(
            [
                InlineQueryResultCachedSticker(
                    sticker_file_id=self.client.config["STICKER_FILE_ID"],
                    reply_markup=reply_markup,
                    input_message_content=InputTextMessageContent(message_text),
                )
            ],
            *args,
            **kwargs,
        )

    async def listen(self, revoke: bool = False, timeout: int = 15) -> Message:
        fut = asyncio.Future()

        async def result(event: Message) -> None:
            if not fut.done():
                fut.set_result(event)

            if revoke:
                await event.delete()

        self.client.register(self, result, "message_bot", priority=-1)
        try:
            res = await asyncio.wait_for(fut, timeout=timeout)
        except Exception:
            return None
        else:
            return res
        finally:
            for listener in tuple(self.client.listeners["message_bot"]):
                if listener.mod is self:
                    self.client.unregister(listener)

    async def progress(
        self, current: int, total: int, event: Update, title: str = "Progress"
    ) -> None:
        time = event._client.loop.time()
        if not hasattr(event, "_start"):
            event._start, event._last = time, time
            return

        if time - event._last >= 2.5:
            delta = time - event._start
            speed = current / delta

            await self.respond(
                event,
                self.fmtmsg(
                    title.lstrip(),
                    {
                        "Current": self.fmtbyte(current),
                        "Total": f"{self.fmtbyte(total)}\n",
                        "Speed": f"{self.fmtbyte(speed)}/s\n",
                        "Elapsed": self.fmtsec(delta, human=True),
                        "Estimated": self.fmtsec(
                            (total - current) / speed if speed > 0 else 0, human=True
                        ),
                    },
                    self.fmtbar(current, total),
                ),
                reply_markup=self.ikm(("Cancel", b"0")),
            )
            event._last = time

    async def respond(
        self,
        event: Update,
        text: str,
        reply: bool = False,
        revoke: int = 0,
        *args,
        **kwargs,
    ) -> Update | int:
        if reply:
            if not isinstance(event, Message):
                raise AttributeError

            event = await event.reply_text(
                text,
                reply_parameters=ReplyParameters(message_id=event.id),
                *args,
                **kwargs,
            )
        else:
            if isinstance(event, Message):
                edit = event.edit_text
            else:
                edit = event.edit_message_text

            event = await edit(text, *args, **kwargs)

        if revoke:
            if not isinstance(event, Message):
                raise AttributeError

            await asyncio.sleep(revoke)
            return await event.delete()

        return event

    def ids(self, inline_message_id: str) -> tuple:
        data = unpack_inline_message_id(inline_message_id)
        try:
            cid, mid = data.owner_id, data.id
        except AttributeError:
            cid, mid = struct.unpack(">ii", data.id.to_bytes(8, signed=True))

        if cid < 0 or cid >= MIN_MONOFORUM_CHANNEL_ID:
            cid = get_channel_id(abs(cid))

        return cid, mid

    def ikm(self, rows: list | tuple) -> InlineKeyboardMarkup:
        if isinstance(rows, tuple):
            rows = [[rows]]

        if isinstance(rows, list) and isinstance(rows[0], tuple):
            rows = [rows]

        ikb = []
        for row in rows:
            line = []
            for i in row:
                kwargs, last = {"text": i[0]}, i[-1]
                if len(i) == 2:
                    kwargs["callback_data"] = last
                elif len(i) == 3:
                    kwargs[i[1]] = last
                else:
                    raise ValueError

                line.append(InlineKeyboardButton(**kwargs))

            ikb.append(line)

        return InlineKeyboardMarkup(ikb)
