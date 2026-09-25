import asyncio
import datetime
import html
import sys
import traceback


class Format:
    def _ensure_rich_handler(self, ping_mod, rawfn, IMRichMsg, IBIR):
        """Pasang handler bersama group -2 di modul Ping (sekali saja)."""
        if getattr(ping_mod, "_rich_handler", None) is not None:
            return
        from pyrogram.raw.types import UpdateBotInlineQuery as _UBIQ
        from pyrogram.handlers import RawUpdateHandler

        bot = self.client.bot

        async def _shared_answer(_c, update, users, chats):
            if not isinstance(update, _UBIQ):
                return
            q = str(update.query)
            for mod, payload in getattr(ping_mod, "_rich_route", {}).items():
                if q.startswith(mod):
                    p_rich, p_close = payload
                    try:
                        await bot.invoke(
                            rawfn.messages.SetInlineBotResults(
                                query_id=update.query_id,
                                results=[
                                    IBIR(
                                        id=str(update.query_id),
                                        type="article",
                                        title="Result",
                                        send_message=IMRichMsg(
                                            rich_message=p_rich,
                                            reply_markup=p_close,
                                        ),
                                    )
                                ],
                                cache_time=0,
                            ),
                        )
                    except Exception as exc:
                        self.logger.warning(f"shared rich {mod} failed: {exc!r}")
                    return

        ping_mod._rich_route = getattr(ping_mod, "_rich_route", None) or {}
        ping_mod._rich_handler = RawUpdateHandler(_shared_answer)
        disp = bot.dispatcher
        if -2 not in disp.groups:
            disp.groups[-2] = []
            disp.groups = dict(sorted(disp.groups.items()))
        disp.groups[-2].append(ping_mod._rich_handler)

    async def send_rich(
        self,
        event,
        title: str,
        rows: list,
        note: str = "",
        query_prefix: str = "rich",
        buttons: list | None = None,
        extra_blocks: list | None = None,
    ) -> bool:
        """Kirim rich table via inline bot. rows = [(param, keterangan), ...].
        buttons = [(teks, callback_data, ButtonStyle|None), ...].
        Return True kalau sukses terkirim, False kalau perlu fallback HTML."""
        import datetime as _dt

        try:
            bot = self.client.bot
            from pyrogram.raw import functions as rawfn
            from pyrogram.raw.types import (
                InputBotInlineMessageRichMessage,
                InputBotInlineResult,
            )
            from pyrogram.types import (
                InputRichBlockExpandableBlockQuotation,
                InputRichBlockParagraph,
                InputRichBlockTable,
                InputRichMessage,
                RichBlockTableCell,
                RichTextBold,
                RichTextItalic,
            )

            trows = [
                [
                    RichBlockTableCell(text="Parameter", is_header=True, align="center"),
                    RichBlockTableCell(text="Keterangan", is_header=True, align="center"),
                ]
            ]
            for k, v in rows:
                trows.append(
                    [
                        RichBlockTableCell(text=str(k), align="left"),
                        RichBlockTableCell(text=str(v), align="left"),
                    ]
                )

            blocks = [InputRichBlockParagraph(text=RichTextBold(title)),
                      InputRichBlockTable(trows, is_bordered=True, is_striped=True, is_compact=True)]
            # Blok tambahan custom (misal list checkbox) — setelah tabel
            for eb in (extra_blocks or []):
                blocks.append(eb)
            if note:
                # Blockquote (garis biru vertikal) seperti contoh @OnlyDevRoBot
                blocks.append(InputRichBlockExpandableBlockQuotation(text=RichTextItalic(note)))

            # Tombol rich: Close (merah) + custom tambahan
            from pyrogram.enums import ButtonStyle
            from pyrogram.types import (
                InputRichBlockButtons,
                RichMessageButton,
                RichTextBold as _RB,
            )
            rich_btns = [
                RichMessageButton(
                    text=_RB("🗑 Close"),
                    style=ButtonStyle.DANGER,
                    callback_data=b"0",
                )
            ]
            for btext, bdata, bstyle in (buttons or []):
                rich_btns.append(
                    RichMessageButton(
                        text=_RB(btext),
                        style=bstyle or ButtonStyle.PRIMARY,
                        callback_data=bdata,
                    )
                )
            blocks.append(InputRichBlockButtons(rich_btns))

            rich_raw = await InputRichMessage(blocks=blocks).write(client=bot)

            # Daftarkan payload ke handler bersama milik Ping (group -2)
            # — helper send_rich juga bisa dipasang lebih awal oleh modul lain
            ping_mod = None
            try:
                ping_mod = self.client.modules.get("Ping")
            except Exception:
                pass
            if ping_mod is None:
                return False
            self._ensure_rich_handler(ping_mod, rawfn, InputBotInlineMessageRichMessage, InputBotInlineResult)
            if getattr(ping_mod, "_rich_route", None) is None:
                ping_mod._rich_route = {}
            ping_mod._rich_route[query_prefix] = (rich_raw, None)

            now = _dt.datetime.now(_dt.UTC)
            res = await event._client.get_inline_bot_results(
                bot.me.id, f"{query_prefix}{now.timestamp()}"
            )
            if res.results:
                await asyncio.gather(
                    event.reply_inline_bot_result(res.query_id, res.results[0].id),
                    event.delete(),
                )
                return True
            return False
        except Exception as e:
            self.logger.warning(f"send_rich failed, fallback html: {e.__class__.__name__}: {e}")
            return False

    def fmtbar(
        self,
        current: int,
        total: int,
        bars: int = 8,
        empty: str = chr(9633),
        fill: str = chr(9635),
    ) -> str:
        fillbar = round(current / total * bars)
        percent = f"{(current / total * 100):.2f}".rstrip("0").rstrip(".")
        return f"[ {fill * fillbar + empty * (bars - fillbar)} ] {percent}%"

    def fmtbyte(self, byte: int, si: bool = False) -> str:
        if si:
            units = (
                ("TB", 1000**4),
                ("GB", 1000**3),
                ("MB", 1000**2),
                ("KB", 1000),
                ("B", 1),
            )
        else:
            units = (
                ("TiB", 1024**4),
                ("GiB", 1024**3),
                ("MiB", 1024**2),
                ("KiB", 1024),
                ("B", 1),
            )

        for unit, factor in units:
            if byte >= factor:
                value = f"{(byte / factor):.2f}".rstrip("0").rstrip(".")
                return f"{value} {unit}"

        return "-"

    def fmtexc(self) -> str:
        exc = traceback.TracebackException(*sys.exc_info())
        fmt = exc.exc_type.__name__
        if exc._str:
            fmt += f":\n  {exc._str}"

        ftb = traceback.format_list(
            f for f in exc.stack if "/site-packages/" in f.filename
        )
        if ftb:
            fmt += f"\n\nTraceback:\n{''.join(ftb)}"

        return fmt

    def fmthelp(self, data: object) -> str:
        if isinstance(data, dict):
            res = [
                f"{' ' * 4}• <b>{k}</b>\n{' ' * 6}<code>{html.escape(v)}</code>"
                for k, v in data.items()
            ]
            return "\n".join(res)
        elif isinstance(data, list):
            return "\n".join([f"{' ' * 4}• <b>{i}</b>" for i in data])

        return f"{' ' * 4}<b>{data}</b>"

    def fmtmsg(
        self, head: str, data: object = None, foot: str = "", msgs: str = ""
    ) -> str:
        body = ""
        if isinstance(data, dict):
            padd = max((len(str(k)) for k in data.keys()), default=0)
            body = "\n".join(
                f"  <code>{html.escape(str(k)).ljust(padd)}</code> : <code>{html.escape(str(v))}</code>"
                for k, v in data.items()
            )
        elif isinstance(data, (list, set, tuple)):
            body = "\n".join(
                f"  <code>{n}</code>. <code>{html.escape(str(item))}</code>"
                for n, item in enumerate(data, start=1)
            )
        elif data:
            body = f"  <code>{html.escape(str(data))}</code>"

        text = [f"<b>{head}</b>"]
        if body:
            text.append(body)

        if msgs:
            text.append(f"<blockquote expandable>{html.escape(str(msgs))}</blockquote>")

        if foot:
            text.append(f"<b><blockquote>{html.escape(str(foot))}</blockquote></b>")

        return "\n\n".join(text)

    def fmtsec(self, sec: object, part: int = 3, human: bool = False) -> str:
        if isinstance(sec, datetime.timedelta):
            delta = sec
        elif isinstance(sec, datetime.datetime):
            delta = datetime.datetime.now(datetime.UTC) - sec.astimezone(datetime.UTC)
        elif isinstance(sec, (float, int)):
            delta = datetime.timedelta(seconds=sec)
        else:
            raise TypeError

        total = int(delta.total_seconds())
        micro = delta.microseconds
        units = (
            ("Week", 60**2 * 24 * 7),
            ("Day", 60**2 * 24),
            ("Hour", 60**2),
            ("Minute", 60),
            ("Second", 1),
        )
        parts = []
        for unit, second in units:
            value, total = divmod(total, second)
            if value:
                parts.append(f"{value} {unit}{'' if value == 1 else 's'}")

            if len(parts) >= part:
                break

        if len(parts) < part and not human:
            ms, us = divmod(micro, 1000)
            if ms:
                parts.append(f"{ms} ms")

            if us and len(parts) < part:
                parts.append(f"{us} µs")

        return ", ".join(parts) if parts else "-"
