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
    InputMediaPhoto,
    InputRichBlockParagraph,
    InputRichBlockSectionHeading,
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


pattern = re.compile(r"^help/?(mod|info|page|cat)?(?:/([\w\-]+))?$")


class Help(Module):
    name = "Selfbot Help"
    cmds = "help(/{name})?"
    desc = {"name": "String", "?": "Optional", "e.g.": "help/debug"}
    mods, maps, ikbs = {}, {}, []

    # Kategori + emoji per modul (key = nama file modul, lowercase)
    # catatan: icon = EMOJI SAJA (jangan dikasih nama kategori, ntar dobel di tombol)
    CATEGORY = {
        # Tools & utilitas
        "admintool": ("🛠", "Admin Tools"),
        "purge": ("🛠", "Admin Tools"),
        "delete": ("🛠", "Admin Tools"),
        "afk": ("💬", "Chat"),
        "notes": ("💬", "Chat"),
        "quotly": ("💬", "Chat"),
        # Media & unduhan
        "alldl": ("📥", "Media & Unduhan"),
        "toss": ("📤", "Media & Unduhan"),
        "ytdl": ("📥", "Media & Unduhan"),
        "upload": ("📥", "Media & Unduhan"),
        "sticker": ("🎨", "Kreatif"),
        "brat": ("🎨", "Kreatif"),
        "beautify": ("🎨", "Kreatif"),
        "ppcouple": ("🎨", "Kreatif"),
        "screenshot": ("🎨", "Kreatif"),
        # Anime & hiburan
        "animepic": ("🌸", "Anime"),
        "animequote": ("🌸", "Anime"),
        "aniquotes": ("🌸", "Anime"),
        # Info & sistem
        "alive": ("📊", "Info & Sistem"),
        "info": ("📊", "Info & Sistem"),
        "ping": ("📊", "Info & Sistem"),
        "sysinfo": ("📊", "Info & Sistem"),
        "speedtest": ("📊", "Info & Sistem"),
        "sgb": ("🔍", "Riset & Pencarian"),
        "risearch": ("🔍", "Riset & Pencarian"),
        "genai": ("🤖", "AI"),
        # Sistem / dev
        "debug": ("⚙️", "Sistem"),
        "restart": ("⚙️", "Sistem"),
        "terminal": ("⚙️", "Sistem"),
        "sendmod": ("⚙️", "Sistem"),
        "call": ("📞", "Voice Call"),
        "help": ("📖", "Bantuan"),
    }

    @classmethod
    def _cat(cls, key: str) -> tuple:
        """Balikin (emoji_kategori, nama_kategori) buat modul."""
        icon, cname = cls.CATEGORY.get(key, ("📦", "Lainnya"))
        return (icon, cname)

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
        parts = event.query.split("/")
        # help/cat/<nama_kategori> -> daftar modul di kategori itu
        if len(parts) == 3 and parts[1] == "cat":
            cat_key = parts[2].strip().lower()
            quote = await self._get_quote()
            try:
                await self._answer_rich(event, quote, category=cat_key)
                return
            except Exception as e:
                with contextlib.suppress(Exception):
                    import traceback as _tb

                    self.logger.warning(
                        f"help cat rich failed: {e!r}\n{_tb.format_exc()}"
                    )
            return

        if len(event.query.split("/")) == 2 and parts[1] != "cat":
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

    def _rich_blocks(
        self, quote: str, page: int = 0, category: str = ""
    ) -> list:
        # Mode 2: daftar modul di satu kategori
        if category:
            return self._blocks_by_category(quote, category)

        # Mode 1 (utama): DAFTAR KATEGORI — klik salah satu buat lihat modulnya
        return self._blocks_category_index(quote)

    def _group_by_category(self) -> dict:
        """Kelompokkan modul: {nama_kategori: (icon, [modul, ...])}"""
        groups: dict = {}
        for mod in self.client.modules.values():
            icon, cname = self._cat(mod.__class__.__name__.lower())
            if cname not in groups:
                groups[cname] = (icon, [])
            groups[cname][1].append(mod)
        return groups

    def _blocks_category_index(self, quote: str) -> list:
        """Halaman utama: grid tombol per kategori."""
        import richpyro as rp

        groups = self._group_by_category()
        # urut alfabetis biar posisi tombol konsisten (ga loncat-loncat)
        ordered = sorted(groups.items(), key=lambda kv: kv[0].lower())
        total_mods = sum(len(v[1]) for _, v in ordered)

        blocks = [
            rp.heading(rp.bold("📖 Menu Bantuan Selfbot"), size=2),
            rp.para(
                rp.italic(
                    f"Pilih kategori — {len(ordered)} kategori, "
                    f"{total_mods} modul"
                )
            ),
            rp.divider(),
        ]

        # Banner: foto di atas menu (gantiin tabel biar kartu lebih ringkes)
        BANNER = "https://qu.ax/x/IsBaX.jpg"
        if BANNER:
            with contextlib.suppress(Exception):
                blocks.append(
                    rp.photo_block(
                        InputMediaPhoto(BANNER),
                        cap=rp.caption(rp.italic(f"{len(ordered)} kategori · {total_mods} modul")),
                    )
                )
            blocks.append(rp.divider())

        # Tombol kategori: 2 per baris, label DIPENDEKIN biar lebar mirip semua
        SHORT = {
            "Admin Tools": "Admin",
            "Media & Unduhan": "Media",
            "Riset & Pencarian": "Riset",
            "Info & Sistem": "Info",
            "Voice Call": "Voice",
        }
        btns = []
        for cname, (icon, mods) in ordered:
            key = cname.lower().replace(" ", "-").replace("&", "")
            label = SHORT.get(cname, cname)
            btns.append(
                rp.btn(
                    rp.bold(f"{icon} {label} ({len(mods)})"),
                    callback_data=f"help/cat/{key}".encode(),
                    style=rp.Style.PRIMARY,
                )
            )
        # 2 tombol per baris
        for i in range(0, len(btns), 2):
            blocks.append(rp.buttons(*btns[i : i + 2], align="center"))

        # Nav bawah: Close + Channel jadi 1 baris biar ga numpuk
        blocks.append(
            rp.buttons(
                rp.btn("🗑 ✕ Tutup", callback_data=b"0", style=rp.Style.DANGER),
                RichMessageButton(
                    text=rp.bold("📢 Channel"),
                    style=ButtonStyle.SUCCESS,
                    url="https://t.me/zpbaiq",
                ),
                align="center",
            )
        )
        if quote:
            blocks.append(rp.para(rp.spoiler(re.sub(r"<[^>]+>", "", quote))))
        return blocks

    def _blocks_by_category(self, quote: str, category: str) -> list:
        """Halaman kategori: accordion modul di kategori itu + tombol kembali."""
        import richpyro as rp

        groups = self._group_by_category()
        target, icon, cname_real = None, "📦", category.title()
        for cname, (ic, mods) in groups.items():
            if cname.lower().replace(" ", "-").replace("&", "") == category:
                target, icon, cname_real = mods, ic, cname
                break
        if target is None:
            target, cname_real = [], category.title()

        blocks = [
            rp.heading(rp.bold(f"{icon} {cname_real}"), size=2),
            rp.para(rp.italic(f"{len(target)} modul di kategori ini")),
        ]

        MAX_LINES, MAX_DESC, MAX_SUM = 8, 6, 40
        for mod in sorted(target, key=lambda x: str(x.name)):
            cmds_raw = (getattr(mod, "cmds", "") or "-").strip()
            cmds_lines = [l for l in cmds_raw.splitlines() if l.strip()][:MAX_LINES]
            det = [rp.preformatted("\n".join(cmds_lines) or "-", language="text")]
            desc = getattr(mod, "desc", None)
            if isinstance(desc, dict) and desc:
                det.append(
                    rp.bullet_list(
                        *[
                            rp.list_item(
                                rp.para(
                                    f"{k}: {v}" if isinstance(v, str) else str(k)
                                )
                            )
                            for k, v in list(desc.items())[:MAX_DESC]
                        ]
                    )
                )
            name = mod.name or "?"
            if len(name) > MAX_SUM:
                name = name[: MAX_SUM - 1] + "…"
            blocks.append(rp.details(name, *det))

        blocks.append(rp.divider())
        blocks.append(
            rp.buttons(
                rp.btn(
                    rp.bold("◀️ Kembali"),
                    callback_data=b"help/cat/back",
                    style=rp.Style.SUCCESS,
                ),
                rp.btn("🗑 ✕ Tutup", callback_data=b"0", style=rp.Style.DANGER),
                align="center",
            )
        )
        if quote:
            blocks.append(rp.para(rp.spoiler(re.sub(r"<[^>]+>", "", quote))))
        return blocks

    def _blocks_all_in_one(self, quote: str) -> list:
        """Semua kategori dalam SATU halaman — tiap kategori jadi accordion,
        isinya accordion modul (nested). Gak perlu bolak-balik klik."""
        import richpyro as rp

        groups = self._group_by_category()
        ordered = sorted(groups.items(), key=lambda kv: kv[0].lower())
        total_mods = sum(len(v[1]) for _, v in ordered)

        blocks = [
            rp.heading(rp.bold("📖 Menu Bantuan Selfbot"), size=2),
            rp.para(
                rp.italic(
                    f"Semua kategori terbuka — {len(ordered)} kategori, "
                    f"{total_mods} modul. Klik untuk expand/collapse."
                )
            ),
            rp.divider(),
        ]

        MAX_LINES, MAX_DESC, MAX_SUM = 8, 6, 40
        for cname, (icon, mods) in ordered:
            mod_accs = []
            for mod in sorted(mods, key=lambda x: str(x.name)):
                cmds_raw = (getattr(mod, "cmds", "") or "-").strip()
                cmds_lines = [
                    l for l in cmds_raw.splitlines() if l.strip()
                ][:MAX_LINES]
                det = [
                    rp.preformatted("\n".join(cmds_lines) or "-", language="text")
                ]
                desc = getattr(mod, "desc", None)
                if isinstance(desc, dict) and desc:
                    det.append(
                        rp.bullet_list(
                            *[
                                rp.list_item(
                                    rp.para(
                                        f"{k}: {v}"
                                        if isinstance(v, str)
                                        else str(k)
                                    )
                                )
                                for k, v in list(desc.items())[:MAX_DESC]
                            ]
                        )
                    )
                mname = mod.name or "?"
                if len(mname) > MAX_SUM:
                    mname = mname[: MAX_SUM - 1] + "…"
                mod_accs.append(rp.details(mname, *det))

            kname = f"{icon} {cname} ({len(mods)})"
            blocks.append(rp.details(kname, *mod_accs))

        blocks.append(rp.divider())
        blocks.append(
            rp.buttons(
                rp.btn("🗑 ✕ Tutup", callback_data=b"0", style=rp.Style.DANGER),
                RichMessageButton(
                    text=rp.bold("📢 Channel"),
                    style=ButtonStyle.SUCCESS,
                    url="https://t.me/zpbaiq",
                ),
                align="center",
            )
        )
        if quote:
            blocks.append(rp.para(rp.spoiler(re.sub(r"<[^>]+>", "", quote))))
        return blocks

    async def _answer_rich(
        self, event: InlineQuery, quote: str, category: str = ""
    ) -> None:
        bot = self.client.bot
        blocks = self._rich_blocks(quote, category=category)
        title = (
            "Menu Bantuan Selfbot"
            if not category
            else f"Bantuan: {category.title()}"
        )
        rich_raw = await InputRichMessage(blocks=blocks).write(client=bot)
        await bot.invoke(
            rawfn.messages.SetInlineBotResults(
                query_id=int(event.id),
                results=[
                    InputBotInlineResult(
                        id=str(event.id),
                        type="article",
                        title=title,
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
                if act == "cat":
                    if val == "back":
                        # Kembali ke index kategori
                        quote = await self._get_quote()
                        rich_raw = await InputRichMessage(
                            blocks=self._rich_blocks(quote)
                        ).write(client=self.client.bot)
                        await self._edit_inline_rich(event, rich_raw, None)
                        return
                    # Buka halaman kategori
                    quote = await self._get_quote()
                    rich_raw = await InputRichMessage(
                        blocks=self._rich_blocks(quote, category=val)
                    ).write(client=self.client.bot)
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
