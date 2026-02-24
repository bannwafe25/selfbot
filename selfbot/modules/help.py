import asyncio
import html
import random
import re
import sys

import pyrogram
from pyrogram import filters
from pyrogram.types import CallbackQuery, InlineQuery, Message, ReplyParameters

from selfbot import __version__
from selfbot.listener import handler, reply
from selfbot.module import Module
from selfbot.apis import FERDEV_ANIMEQUOTE, FERDEV_APIKEY

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
            page.append((mod.__class__.__name__, "data", f"help/mod/{name}".encode()))
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
                            ("« Back", "data", f"help/page/{self.maps[name]}"),
                            ("Close", "data", b"0"),
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
                self.ikm(("Close", "data", b"0")),
                (
                    f"<code>No Module with Name '{name}'</code>\n\n"
                    f"<b>Available Modules:</b>\n{'\n'.join(names)}\n\n"
                    "Get with Prefix '<code>help/</code>'\n"
                    "<b>e.g.</b> <code>help/debug</code>"
                ),
            )
            return

        name = self.client.app.me.first_name or "Selfbot"
        quote = await self._get_quote()
        header = self._build_header(name, quote)
        await self.answer(event, self.ikm(self.build()), header)

    @handler(filters.regex(pattern), 4)
    async def on_inline_callback(self, event: CallbackQuery) -> None:
        act, val = pattern.match(event.data).groups()
        if act == "info":
            name = self.client.app.me.first_name or "Selfbot"
            await event.answer(
                (
                    f"{name} v{__version__}\n"
                    f"Pyrogram {pyrogram.__version__}\n"
                    f"Python {sys.version.split()[0]}\n"
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
                        ("« Back", "data", f"help/page/{page}".encode()),
                        ("Close", "data", b"0"),
                    ]
                ),
            )
            return

        name = self.client.app.me.first_name or "Selfbot"
        quote = await self._get_quote()
        header = self._build_header(name, quote)
        await self.respond(
            event, header, reply_markup=self.ikm(self.build(int(val)))
        )

    def _build_header(self, name: str, quote: str = "") -> str:
        header = (
            f"<b>{html.escape(name)} Modules</b>\n\n"
            f"<blockquote>"
            f"<code>Version </code> : <code>{__version__}</code>\n"
            f"<code>Pyrogram</code> : <code>{pyrogram.__version__}</code>\n"
            f"<code>Python  </code> : <code>{sys.version.split()[0]}</code>\n"
            f"<code>Modules </code> : <code>{len(self.client.modules)}</code>"
            f"</blockquote>"
        )
        if quote:
            header += f"\n\n<blockquote>{quote}</blockquote>"
        return header

    async def _get_quote(self) -> str:
        try:
            resp = await self.client.http.get(
                FERDEV_ANIMEQUOTE,
                params={"apikey": FERDEV_APIKEY},
                timeout=5,
            )
            if resp.status_code == 200:
                data = resp.json()
                results = data.get("result", [])
                if results:
                    q = random.choice(results)
                    text = html.escape(q.get("quote", ""))
                    char = html.escape(q.get("char", ""))
                    anime = html.escape(q.get("from_anime", ""))
                    return f"<i>\"{text}\"</i>\n— <b>{char}</b> ({anime})"
        except Exception:
            pass
        return ""

    def build(self, page: int = 0) -> list:
        idx = max(0, min(page, len(self.ikbs) - 1))
        ikb = self.ikbs[idx][:]
        ikb.append([("ℹ️ Info", "data", b"help/info")])
        nav = []
        if idx > 0:
            nav.append((f"« ({idx})", "data", f"help/page/{idx - 1}".encode()))

        nav.append(("Close", "data", b"0"))
        if idx < len(self.ikbs) - 1:
            nav.append((f"({idx + 2}) »", "data", f"help/page/{idx + 1}".encode()))

        ikb.append(nav)
        return ikb
