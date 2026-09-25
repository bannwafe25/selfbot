import asyncio
import base64
import contextlib
import html
import random
import re
import struct
import sys

import pyrogram
from pyrogram import filters
from pyrogram.raw import functions as rawfn
from pyrogram.raw import types as rawtypes
from pyrogram.raw.types import (
    InputBotInlineMessageRichMessage,
    InputBotInlineResult,
)
from pyrogram.types import (
    CallbackQuery,
    InlineQuery,
    InputRichBlockParagraph,
    InputRichBlockPreformatted,
    InputRichBlockTable,
    InputRichBlockButtons,
    InputRichBlockList,
    InputRichBlockListItem,
    InputRichBlockDetails,
    InputRichBlockDivider,
    InputRichBlockAnchor,
    RichMessageButton,
    InputRichMessage,
    Message,
    ReplyParameters,
    RichBlockTableCell,
    RichTextAnchorLink,
    RichTextBold,
    RichTextCode,
    RichTextItalic,
)
from pyrogram.enums import ButtonStyle

from selfbot import __version__
from selfbot.listener import handler, reply
from selfbot.module import Module
from selfbot.apis import FERDEV_ANIMEQUOTE, FERDEV_APIKEY


from pyrogram import raw as _praw
from pyrogram.types.messages_and_media.rich_text import (
    RichText as _RichText,
    RichTextCode as RichTextFixed,
)


class RichTextCopyable(_RichText):
    """Monospace + tombol copy (raw TextCode, bukan TextFixed)."""

    def __init__(self, text: str):
        super().__init__()
        self.text = text

    async def write(self, client):
        return _praw.types.TextFixed(text=await _RichText._write(client, self.text))


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
            page.append((mod.__class__.__name__, "data", f"help/mod/{name}".encode(), "B"))
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
                self.client.bot.me.id, event.content
            ),
        )
        await asyncio.gather(
            event.reply_inline_bot_result(
                res.query_id,
                res.results[0].id,
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
                    "<b>Available Modules:</b>\n"
                    + "\n".join(names)
                    + "\n\n"
                    "Get with Prefix '<code>help/</code>'\n"
                    "<b>e.g.</b> <code>help/debug</code>"
                ),
            )
            return

        quote = await self._get_quote()
        try:
            await self._answer_rich(event, quote)
            return
        except Exception as e:
            with contextlib.suppress(Exception):
                import traceback as _tb
                self.logger.warning(f"help rich inline failed: {e!r}\n{_tb.format_exc()}")
        header = self._build_header(quote)
        await self.answer(event, self.ikm(self.build()), header)

    def _rich_blocks(self, quote: str, page: int = 0) -> list:
        mods = list(self.client.modules.values())
        per_page = 4
        chunks = [mods[i : i + per_page] for i in range(0, len(mods), per_page)]
        total_pages = max(len(chunks), len(self.ikbs))
        chunk = chunks[page] if page < len(chunks) else chunks[-1]

        def count_cmds(mod) -> int:
            d = mod.desc
            if isinstance(d, dict):
                return max(
                    sum(
                        1
                        for k, v in d.items()
                        if k not in ("e.g.", "?") and isinstance(v, str) and v
                    ),
                    1,
                )
            return 1

        rows = [
            [
                RichBlockTableCell(text=RichTextBold("Modul"), is_header=True),
                RichBlockTableCell(text=RichTextBold("Pattern"), is_header=True),
            ]
        ]
        offset = page * per_page
        for i, mod in enumerate(chunk, 1):
            rows.append(
                [
                    RichBlockTableCell(text=RichTextBold(mod.name)),
                    RichBlockTableCell(
                        text=RichTextFixed(getattr(mod, "cmds", "") or "-")
                    ),
                ]
            )
        blocks = [
            InputRichBlockParagraph(text=RichTextBold("📖 Menu Bantuan Userbot")),
            InputRichBlockParagraph(
                text=RichTextItalic(
                    f"Bagian {page + 1}/{total_pages} — Total {len(mods)} modul"
                    " — Prefix aktif: (tanpa prefix)"
                )
            ),
        ]
        # Details (accordion) per modul — bisa buka-tutup
        details_blocks = []
        for mod in chunk:
            det = [
                InputRichBlockPreformatted(
                    text=getattr(mod, "cmds", "") or "-",
                    language="text",
                )
            ]
            desc = getattr(mod, "desc", None)
            if isinstance(desc, dict) and desc:
                det.append(
                    InputRichBlockList(
                        items=[
                            InputRichBlockListItem(
                                blocks=[InputRichBlockParagraph(
                                    text=f"{k}: {v}"
                                    if isinstance(v, str)
                                    else str(k)
                                )]
                            )
                            for k, v in list(desc.items())[:6]
                        ]
                    )
                )
            details_blocks.append(
                InputRichBlockDetails(
                    summary=RichTextBold(mod.name),
                    blocks=det,
                )
            )
        for d in details_blocks:
            blocks.append(d)
        blocks.append(InputRichBlockDivider())
        # Tombol navigasi + Close (tombol modul dihapus — cukup accordion Details)
        nav_btns = []
        for row in self.ikm(self.build(page)).inline_keyboard:
            is_mod = any(
                getattr(b, "callback_data", b"") and b.callback_data.startswith(b"help/mod/")
                for b in row
            )
            if is_mod:
                continue
            if any(
                getattr(b, "callback_data", b"") == b"help/info" for b in row
            ):
                continue
            for b in row:
                kw = {"text": RichTextBold(b.text)}
                if b.callback_data is not None:
                    kw["callback_data"] = b.callback_data
                elif b.url is not None:
                    kw["url"] = b.url
                if b.callback_data == b"0" or "close" in b.text.lower():
                    kw["style"] = ButtonStyle.DANGER
                else:
                    kw["style"] = ButtonStyle.SUCCESS
                nav_btns.append(RichMessageButton(**kw))
        if nav_btns:
            blocks.append(InputRichBlockButtons(nav_btns[:8]))
        # Tombol channel (biru) — di bawah navigasi
        blocks.append(
            InputRichBlockButtons(
                [
                    RichMessageButton(
                        text=RichTextBold("📢 Channel"),
                        style=ButtonStyle.PRIMARY,
                        url="https://t.me/zpbaiq",
                    )
                ]
            )
        )
        if quote:
            blocks.append(
                InputRichBlockParagraph(
                    text=RichTextItalic(re.sub(r"<[^>]+>", "", quote))
                )
            )
        return blocks

    async def _answer_rich(self, event: InlineQuery, quote: str) -> None:
        bot = self.client.bot
        rich_raw = await InputRichMessage(
            blocks=self._rich_blocks(quote)
        ).write(client=bot)
        await bot.invoke(
            rawfn.messages.SetInlineBotResults(
                query_id=int(event.id),
                results=[
                    InputBotInlineResult(
                        id=str(event.id),
                        type="article",
                        title="Menu Bantuan Userbot",
                        send_message=InputBotInlineMessageRichMessage(
                            rich_message=rich_raw,
                        ),
                    )
                ],
                cache_time=0,
            )
        )

    @handler(filters.regex(pattern), 4)
    async def on_inline_callback(self, event: CallbackQuery) -> None:
        act, val = pattern.match(event.data).groups()

        # Rich path: callback dari rich message (inline_message_id, event.message=None)
        if event._client is self.client.bot and getattr(
            event, "inline_message_id", None
        ):
            await event.answer()
            try:
                if act == "info":
                    await event.answer()
                    with contextlib.suppress(Exception):
                        import pyrogram as _pg
                        await self._edit_inline_rich(
                            event,
                            await InputRichMessage(
                                blocks=[
                                    InputRichBlockParagraph(
                                        text=RichTextBold(f"ℹ️ Selfbot v{__version__}")
                                    ),
                                    InputRichBlockParagraph(
                                        text=(
                                            f"Pyrogram {_pg.__version__} · "
                                            f"Python {sys.version.split()[0]} · "
                                            f"{len(self.client.modules)} Modul · "
                                            f"{len(self.ikbs)} Halaman"
                                        )
                                    ),
                                ]
                            ).write(client=self.client.bot),
                            None,
                        )
                    return
                if act == "mod":
                    rich_raw = await InputRichMessage(
                        blocks=self._mod_rich_blocks(val)
                    ).write(client=self.client.bot)
                    # Detail modul polos: tanpa tombol apa pun
                    await self._edit_inline_rich(event, rich_raw, None)
                    return
                page = int(val)
                quote = await self._get_quote()
                rich_raw = await InputRichMessage(
                    blocks=self._rich_blocks(quote, page)
                ).write(client=self.client.bot)
                await self._edit_inline_rich(event, rich_raw, None)
                return
            except Exception as e:
                with contextlib.suppress(Exception):
                    self.logger.warning(f"help rich callback failed: {e!r}")
                # jalur HTML lama sebagai fallback
            return

        act, val = pattern.match(event.data).groups()
        if act == "info":
            await event.answer(
                (
                    f"Selfbot v{__version__}\n"
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
                        ("« Back", "data", f"help/page/{page}".encode(), "B"),
                        ("Close", "data", b"0"),
                    ]
                ),
            )
            return

        quote = await self._get_quote()
        header = self._build_header(quote)
        await self.respond(
            event, header, reply_markup=self.ikm(self.build(int(val)))
        )

    def _mod_rich_blocks(self, name: str) -> list:
        mod = self.client.modules.get(name)
        if mod is None:
            for key, m in self.client.modules.items():
                if key.lower() == name.lower():
                    mod = m
                    break
        blocks = [
            InputRichBlockParagraph(
                text=RichTextBold(mod.name if mod else name.title())
            ),
        ]
        if mod:
            blocks.append(
                InputRichBlockPreformatted(
                    text=RichTextCopyable(mod.cmds), language="bash"
                )
            )
            desc = mod.desc
            if isinstance(desc, dict):
                rows = [
                    [
                        RichBlockTableCell(text=RichTextBold(str(k))),
                        RichBlockTableCell(text=str(v)),
                    ]
                    for k, v in desc.items()
                ]
                if rows:
                    blocks.append(
                        InputRichBlockTable(
                            rows, is_bordered=True, is_striped=True, is_compact=False
                        )
                    )
            elif desc:
                blocks.append(InputRichBlockParagraph(text=str(desc)))
        return blocks

    async def _edit_inline_rich(self, event: CallbackQuery, rich, markup=None) -> None:
        from pyrogram.utils import unpack_inline_message_id

        inline_id = unpack_inline_message_id(event.inline_message_id)
        # markup bisa InlineKeyboardMarkup (biasa) atau blok rich — rich TIDAK
        # boleh di-.write(), langsung diteruskan ke rich_message utama
        if isinstance(markup, InputRichBlockButtons):
            markup_raw, rich_btn_block = None, rich
            rich.blocks.append(markup)
        else:
            markup_raw = await markup.write(self.client.bot) if markup else None
            rich_btn_block = None
        await self.client.bot.invoke(
            rawfn.messages.EditInlineBotMessage(
                id=inline_id,
                rich_message=rich,
                reply_markup=markup_raw,
            )
        )

    def _rich_from_ikm(self, ikm_markup):
        """Konversi InlineKeyboardMarkup jadi InputRichBlockButtons (rich)."""
        style_rev = {
            str(ButtonStyle.DANGER): ButtonStyle.DANGER,
            str(ButtonStyle.SUCCESS): ButtonStyle.SUCCESS,
            str(ButtonStyle.PRIMARY): ButtonStyle.PRIMARY,
        }
        rows_out = []
        for row in ikm_markup.inline_keyboard:
            for btn in row:
                kwargs = {"text": RichTextBold(btn.text)}
                if btn.callback_data is not None:
                    kwargs["callback_data"] = btn.callback_data
                elif btn.url is not None:
                    kwargs["url"] = btn.url
                else:
                    continue  # jenis tombol tak didukung rich, skip
                st = style_rev.get(str(btn.style))
                if st:
                    kwargs["style"] = st
                rows_out.append(RichMessageButton(**kwargs))
        # InputRichBlockButtons: SATU list datar (maks 8 tombol per baris)
        return InputRichBlockButtons(rows_out[:8])

    def _build_header(self, quote: str = "") -> str:
        header = (
            f"<b>Selfbot Modules</b>\n\n"
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
                if isinstance(data, list) and data:
                    q = random.choice(data)
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
            nav.append((f"« ({idx})", "data", f"help/page/{idx - 1}".encode(), "G"))

        nav.append(("Close", "data", b"0"))
        if idx < len(self.ikbs) - 1:
            nav.append((f"({idx + 2}) »", "data", f"help/page/{idx + 1}".encode(), "G"))

        ikb.append(nav)
        return ikb
