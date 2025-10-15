import abc
import asyncio
import bisect
import contextlib

from pyrogram.errors import FloodWait, MessageNotModified, QueryIdInvalid, SlowmodeWait
from pyrogram.types import (
    CallbackQuery,
    InlineQuery,
    InlineQueryResultCachedSticker,
    InputTextMessageContent,
    Update,
)

from selfbot.listener import Listener
from selfbot.module import Module
from selfbot.utils import ikm


class Dispatcher(abc.ABC):
    def __init__(self, **kwargs) -> None:
        self.listeners: dict[str, list[Listener]] = {}

        super().__init__(**kwargs)

    async def dispatch(self, event: str, *args: any, **kwargs: any) -> None:
        for listener in self.listeners.get(event, []):
            try:
                if listener.filters and args and isinstance(args[0], Update):
                    update = args[0]
                    if not await listener.filters(update._client, update):
                        continue
                    else:
                        if (
                            isinstance(update, CallbackQuery | InlineQuery)
                            and update.from_user.id != self.app.me.id
                        ):
                            if isinstance(update, InlineQuery):
                                await update.answer(
                                    [
                                        InlineQueryResultCachedSticker(
                                            sticker_file_id=self.config[
                                                "sticker_file_id"
                                            ],
                                            reply_markup=ikm(
                                                (
                                                    "Source",
                                                    "url",
                                                    "https://github.com/DeltaUniverse/selfbot.git",
                                                )
                                            ),
                                            input_message_content=InputTextMessageContent(
                                                "<b>Who are You?</b>"
                                            ),
                                        )
                                    ],
                                    cache_time=15,
                                )
                            else:
                                await update.answer(
                                    "Who are You?", show_alert=True, cache_time=15
                                )

                            continue

                await listener.func(*args, **kwargs)

            except (MessageNotModified, QueryIdInvalid):
                continue

            except (FloodWait, SlowmodeWait) as e:
                if e.value <= 30:
                    await asyncio.sleep(e.value)
                    with contextlib.suppress(Exception):
                        await listener.func(*args, **kwargs)
                else:
                    continue

            except Exception as e:
                tb = e.__traceback__
                while tb and tb.tb_next:
                    tb = tb.tb_next

                fn = tb.tb_frame.f_code.co_filename if tb else "N/A"
                ln = tb.tb_lineno if tb else "N/A"

                with contextlib.suppress(Exception):
                    await self.bot.send_message(
                        self.app.me.id,
                        (
                            f"<b>Line {ln}</b>\n<code>{fn}</code>"
                            f"\n\n<b>{e.__class__.__name__}</b>\n<code>{e}</code>"
                        ),
                    )

                self.logger.error(f"{e.__class__.__name__}: {e} at {fn}:{ln}")

    def registers(self, mod: "Module") -> None:
        for event, func in self._funcs(mod, "on_"):
            done = False
            try:
                self.register(
                    mod,
                    func,
                    event,
                    filters=getattr(func, "filters", None),
                    priority=getattr(func, "priority", 100),
                )
                done = True
            finally:
                if not done:
                    self.unregisters(mod)

    def unregisters(self, mod: "Module") -> None:
        slots = []
        for event, listeners in self.listeners.items():
            for listener in listeners:
                if listener.mod == mod:
                    slots.append(listener)

        for listener in slots:
            self.unregister(listener)

    def register(
        self, mod: type, func: callable, event: str, *, filters=None, priority=100
    ) -> None:
        if event not in self.listeners:
            self.listeners[event] = []

        bisect.insort(
            self.listeners[event], Listener(mod, func, event, filters, priority)
        )
        self.updates()

    def unregister(self, listener: "Listener") -> None:
        self.listeners[listener.event].remove(listener)
        if not self.listeners[listener.event]:
            del self.listeners[listener.event]

        self.updates()
