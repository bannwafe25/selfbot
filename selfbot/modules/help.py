import asyncio
import html
import re

from pyrogram import filters
from pyrogram.types import CallbackQuery, InlineQuery, Message, ReplyParameters

from selfbot import __version__
from selfbot.listener import handler, reply
from selfbot.module import Module

pattern = re.compile(r"^help/?(mod|info|page)?(?:/(\d{1}|[a-zA-Z]+))?$")


class Help(Module):
    name = "Selfbot Help"
    cmds = "help(/{name})?"
    desc = {"name": "String", "?": "Optional", "e.g.": "help/debug"}
    mods, maps, ikbs = {}, {}, []

    async def on_started(self) -> None:
        mods, page = [mod for mod in self.client.modules.values()], []
        for i, mod in enumerate(mods):
            name = mod.__class__.__name__.lower()
            self.maps[name] = len(self.ikbs)
            self.mods[name] = (
                f"<b>{mod.name}</b>\n\n{' ' * 2}<b>Pattern</b>"
                f"\n{' ' * 4}<code>{html.escape(mod.cmds)}</code>"
                f"\n\n{self.fmthelp(mod.desc)}"
            )
            page.append(
                (mod.__class__.__name__, "data", f"help/mod/{name}".encode(), "B")
            )
            if len(page) == 4:
                self.ikbs.append([page[i : i + 2] for i in range(0, 4, 2)])
                page = []

        if page:
            self.ikbs.append([page[i : i + 2] for i in range(0, len(page), 2)])

    @handler(filters.regex(pattern) & ~reply, 1)
    async def on_message_out(self, event: Message) -> None:
        _, res = await asyncio.gather(
            self.respond(event, "<code>...</code>"),
            event._client.get_inline_bot_results(
                self.client.bot.me.id, event.content, chat_id=event.chat.id
            ),
        )
        await asyncio.gather(
            event.reply_inline_bot_result(
                res.query_id,
                res.results[0].id,
                reply_parameters=ReplyParameters(message_id=event.id),
            ),
            event.delete(),
        )

    @handler(filters.regex(pattern), 2)
    async def on_inline_query(self, event: InlineQuery) -> None:
        if len(event.query.split("/")) == 2:
            name = event.query.split("/")[1].strip().lower()
            if name in self.mods:
                await self.answer(
                    event,
                    self.ikm(
                        [
                            ("« Back", "data", f"help/page/{self.maps[name]}", "G"),
                            ("Close", "data", b"0", "R"),
                        ]
                    ),
                    self.mods[name],
                )
                return

            names = [
                f"  {n}. <code>{i}</code>" for n, i in enumerate(self.client.modules, 1)
            ]
            await self.answer(
                event,
                self.ikm(("Close", "data", b"0", "R")),
                (
                    f"<code>No Module with Name '{name}'</code>\n\n"
                    f"<b>Available Modules:</b>\n{'\n'.join(names)}\n\n"
                    "Get with Prefix '<code>help/</code>'\n"
                    "<b>e.g.</b> <code>help/debug</code>"
                ),
            )
            return

        await self.answer(event, self.ikm(self.build()), "<b>Selfbot Modules</b>")

    @handler(filters.regex(pattern), 4)
    async def on_inline_callback(self, event: CallbackQuery) -> None:
        act, val = pattern.match(event.data).groups()
        if act == "info":
            await event.answer(
                (
                    f"Selfbot Version {__version__}\n"
                    f"\n    {len(self.client.handlers)} Handlers"
                    f"\n    {len(self.client.listeners)} Listeners"
                    f"\n    {len(self.client.modules)} Modules"
                    f"\n\n{len(self.ikbs)} Pages"
                ),
                show_alert=True,
            )
            return

        if act == "mod":
            page = self.maps.get(val, 0)
            await self.respond(
                event,
                self.mods[val],
                reply_markup=self.ikm(
                    [
                        ("« Back", "data", f"help/page/{page}".encode(), "G"),
                        ("Close", "data", b"0", "R"),
                    ]
                ),
            )
            return

        await self.respond(
            event, "<b>Selfbot Modules</b>", reply_markup=self.ikm(self.build(int(val)))
        )

    def build(self, page: int = 0) -> list:
        idx = max(0, min(page, len(self.ikbs) - 1))
        ikb = self.ikbs[idx][:]
        ikb.append([("Selfbot Info", "data", b"help/info")])
        nav = []
        if idx > 0:
            nav.append((f"« ({idx})", "data", f"help/page/{idx - 1}".encode(), "G"))

        nav.append(("Close", "data", b"0", "R"))
        if idx < len(self.ikbs) - 1:
            nav.append((f"({idx + 2}) »", "data", f"help/page/{idx + 1}".encode(), "G"))

        ikb.append(nav)
        return ikb
