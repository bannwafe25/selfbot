import asyncio
import logging
import typing

from pyrogram.types import (
    InlineKeyboardMarkup,
    InlineQuery,
    InlineQueryResultCachedSticker,
    InputTextMessageContent,
    Message,
    ReplyParameters,
    Update,
)

from selfbot.utils import ikm

if typing.TYPE_CHECKING:
    from selfbot.core import Selfbot


class Module:
    name = "Module"
    cmds = ""
    desc = None

    def __init__(self, client: "Selfbot") -> None:
        self.client = client
        self.logger = logging.getLogger(self.__class__.__name__)

    async def answer(
        self,
        event: InlineQuery,
        reply_markup: InlineKeyboardMarkup = None,
        message_text: str = "",
        *args,
        **kwargs,
    ) -> None:
        if not reply_markup:
            reply_markup = ikm((">_", "user_id", event._client.me.id))

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
                fmtmsg(
                    title.lstrip(),
                    {
                        "Current": fmtbyte(current),
                        "Total": f"{fmtbyte(total)}\n",
                        "Speed": f"{fmtbyte(speed)}/s\n",
                        "Elapsed": fmtsec(delta, human=True),
                        "Estimated": fmtsec(
                            (total - current) / speed if speed > 0 else 0, human=True
                        ),
                    },
                    fmtbar(current, total),
                ),
                reply_markup=ikm(("Cancel", b"0")),
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

            return await event.reply_text(
                text,
                reply_parameters=ReplyParameters(message_id=event.id),
                *args,
                **kwargs,
            )

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


class ModuleError(Exception):
    pass


class ModuleExists(ModuleError):
    def __init__(self, obj: type) -> None:
        super().__init__(f"Module '{obj.__name__}' Exists")
