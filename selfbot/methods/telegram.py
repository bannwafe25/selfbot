import asyncio
import struct

from pyrogram import Client, filters
from pyrogram.enums import ButtonStyle
from pyrogram.types import (
    CopyTextButton,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQuery,
    InlineQueryResultCachedSticker,
    InputMedia,
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
            reply_markup = self.ikm((">_", "user", event._client.me.id, "blue"))

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

    async def listen(
        self,
        client: Client = None,
        user_id: int | str = None,
        chat_id: int | str = None,
        timeout: int = 15,
    ) -> Message | None:
        flt = filters.all
        if user_id:
            flt &= filters.user(user_id)

        if chat_id:
            flt &= filters.chat(chat_id)

        fut = asyncio.Future()
        mod = self.__class__(self.client)

        async def result(event: Message) -> None:
            if not fut.done():
                fut.set_result(event)

        self.client.register(mod, result, client.name, filters=flt, priority=-1)
        try:
            res = await asyncio.wait_for(fut, timeout=timeout)
        except Exception:
            return None
        else:
            return res
        finally:
            for listener in tuple(self.client.listeners[client.name]):
                if listener.mod is mod:
                    self.client.unregister(listener)

    async def progress(
        self, current: int, total: int, event: Update, title: str = "Progress"
    ) -> None:
        time = event._client.loop.time()
        byte = getattr(event, "prog_byte", 0)
        if current < byte or not hasattr(event, "prog_init"):
            event.prog_init = time
            event.prog_last = time
            event.prog_byte = 0
            return

        if time - event.prog_last >= 2.5 or current == total:
            speed = (current - event.prog_byte) / (time - event.prog_last)
            await self.respond(
                event,
                self.fmtmsg(
                    title.lstrip(),
                    {
                        "Current": self.fmtbyte(current),
                        "Total": f"{self.fmtbyte(total)}\n",
                        "Speed": f"{self.fmtbyte(speed)}/s\n",
                        "Elapsed": self.fmtsec(time - event.prog_init, human=True),
                        "Estimated": self.fmtsec(
                            (total - current) / speed if speed > 0 else 0, human=True
                        ),
                    },
                    self.fmtbar(current, total),
                ),
                reply_markup=self.ikm(("Cancel", "data", b"0", "red")),
            )
            event.prog_last = time
            event.prog_byte = current

    async def respond(
        self,
        event: Update,
        message: str | InputMedia,
        reply: bool = False,
        revoke: int = 0,
        *args,
        **kwargs,
    ) -> Update | int:
        if reply:
            if not isinstance(event, Message):
                raise AttributeError

            event = await event.reply_text(
                message,
                reply_parameters=ReplyParameters(message_id=event.id),
                *args,
                **kwargs,
            )
        else:
            if isinstance(event, Message):
                if isinstance(message, str):
                    edit = event.edit_text
                else:
                    edit = event.edit_media
            else:
                if isinstance(message, str):
                    edit = event.edit_message_text
                else:
                    edit = event.edit_message_media

            event = await edit(message, *args, **kwargs)

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
        elif isinstance(rows, list):
            if isinstance(rows[0], tuple):
                rows = [rows]
            elif isinstance(rows[0], list):
                rows = rows
            else:
                raise TypeError
        else:
            raise TypeError

        ikb = []
        btn = {
            "blue": ButtonStyle.PRIMARY,
            "red": ButtonStyle.DANGER,
            "green": ButtonStyle.SUCCESS,
            "default": ButtonStyle.DEFAULT,
        }
        for row in rows:
            line = []
            for i in row:
                kwargs, length = {"text": i[0]}, len(i)

                if length == 2:
                    kwargs["callback_data"] = i[1]
                elif 2 < length < 6:
                    k, v = i[1], i[2]
                    if k == "copy":
                        kwargs["copy_text"] = CopyTextButton(text=v)
                    elif k == "data":
                        kwargs["callback_data"] = v
                    elif k == "link":
                        kwargs["url"] = v
                    elif k == "user":
                        kwargs["user_id"] = v
                    else:
                        kwargs[k] = v

                    if length > 3:
                        if i[3] in btn:
                            kwargs["style"] = btn[i[3]]
                        else:
                            kwargs["style"] = btn["default"]

                        if length == 5:
                            kwargs["icon_custom_emoji_id"] = i[4]
                        elif length != 4:
                            raise ValueError
                else:
                    raise ValueError

                line.append(InlineKeyboardButton(**kwargs))

            ikb.append(line)

        return InlineKeyboardMarkup(ikb)
