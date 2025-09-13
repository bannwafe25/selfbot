import abc
import asyncio
import bisect
import contextlib
import html

from pyrogram.errors import FloodWait, SlowmodeWait

from selfbot.listener import Listener
from selfbot.module import Module


class Dispatcher(abc.ABC):
    def __init__(self, **kwargs) -> None:
        self.listeners = {}

        super().__init__(**kwargs)

    async def dispatch(self, event: str, *args, **kwargs) -> None:
        for listener in self.listeners.get(event, []):
            if listener.filters:
                arg = args[0]

                if not await listener.filters(arg._client, arg):
                    continue

            try:
                await listener.func(*args, **kwargs)

            except (FloodWait, SlowmodeWait) as e:
                text = f"{e.__class__.__name__}: Sleep {e.value} s"

                await edit(args[0], text)
                await asyncio.sleep(e.value)

                try:
                    await listener.func(*args, **kwargs)
                except Exception as r:
                    text = f"{r.__class__.__name__}: {r}"
                    await edit(args[0], text)

            except Exception as e:
                text = f"{e.__class__.__name__}: {e}"
                await edit(args[0], text)

    def registers(self, mod: "Module") -> None:
        for event, func in mod_funcs(mod, "on_"):
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


async def edit(arg: type, text: str) -> None:
    fmt = f"# <code>{html.escape(text)}</code>"

    with contextlib.suppress(Exception):
        if hasattr(arg, "edit_text"):
            await arg.edit_text(f"{fmt}\n\n{arg.content.markdown}")
        elif hasattr(arg, "edit_message_text"):
            await arg.edit_message_text(f"{fmt}\n\n{arg.content.markdown}")


def mod_funcs(mod: "Module", prefix: str) -> list:
    res = []

    for attr in dir(mod):
        if attr.startswith(prefix):
            func = getattr(mod, attr)

            if callable(func):
                res.append((attr[len(prefix) :], func))

    return res
