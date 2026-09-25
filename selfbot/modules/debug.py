import asyncio
import contextlib
import datetime
import html
import io
import re

import pyrogram
from pyrogram import filters
from pyrogram.types import (
    CallbackQuery,
    ChosenInlineResult,
    InlineQuery,
    InputMediaDocument,
    Message,
    ReplyParameters,
    Update,
)

from selfbot.listener import handler
from selfbot.module import Module

pattern = re.compile(r"^(?:e\s.+|.*#)$", flags=re.DOTALL)


class Debug(Module):
    name = "Code Execute"
    cmds = "{prefix}? {code} {suffix}?"
    desc = {
        "prefix": "e",
        "code": "String",
        "suffix": "# (Inline)",
        "?": "Optional",
        "e.g.": 'print("Hello, World!")#',
    }

    async def on_starting(self) -> None:
        self.kwargs = {
            "asyncio": asyncio,
            "datetime": datetime,
            "io": io,
            "re": re,
            "pyrogram": pyrogram,
            "raw": pyrogram.raw,
            "enums": pyrogram.enums,
            "types": pyrogram.types,
            "utils": pyrogram.utils,
            "self": self,
            "ikm": self.ikm,
            "aexec": self.aexec,
            "shell": self.shell,
            "client": self.client,
            "db": self.client.db,
            "app": self.client.app,
            "bot": self.client.bot,
            "http": self.client.http,
            "loop": self.client.loop,
            "fmtbar": self.fmtbar,
            "fmtexc": self.fmtexc,
            "fmtmsg": self.fmtmsg,
            "fmtsec": self.fmtsec,
            "listen": self.listen,
            "fmtbyte": self.fmtbyte,
            "respond": self.respond,
            "progress": self.progress,
        }

    async def on_started(self) -> None:
        if hasattr(self.client, "call"):
            self.kwargs["call"] = self.client.call

    @handler(filters.regex(pattern), 1)
    async def on_message_out(self, event: Message) -> None:
        if event.content.strip() == "#":
            now, res = datetime.datetime.now(datetime.UTC), 0
            for task in asyncio.all_tasks():
                name = task.get_name()
                if name.startswith("selfbot/"):
                    if event.reply_to_message:
                        if (
                            name
                            == f"selfbot/{event.chat.id}/{event.reply_to_message_id}"
                        ):
                            task.cancel()
                            await event.delete()
                            return

                    task.cancel()
                    res += 1

            if res > 0:
                await self.respond(
                    event,
                    self.fmtmsg(
                        "Cancel",
                        f"{res} Task{'' if res == 1 else 's'}",
                        self.fmtsec(now),
                    ),
                )

            return

        if event.content.endswith("#"):
            _, res = await asyncio.gather(
                self.respond(
                    event,
                    html.escape(event.content.markdown).removesuffix("#").rstrip(),
                ),
                event._client.get_inline_bot_results(
                    self.client.bot.me.id, "#"
                ),
            )
            await event.reply_inline_bot_result(
                res.query_id,
                res.results[0].id,
            )
            return

        cmd, msg = await asyncio.gather(
            self.respond(
                event, html.escape(event.content.markdown).removeprefix("e").lstrip()
            ),
            self.respond(event, "<code>...</code>", reply=True),
        )
        await self.execute(cmd, msg)

    @handler(filters.private & filters.self_destruction, 2)
    async def on_message_in(self, event: Message) -> None:
        func = getattr(self.client.bot, f"send_{event.media.value}")
        args, media = (func.__annotations__, getattr(event, event.media.value))
        await func(
            **{
                "chat_id": event._client.me.id,
                event.media.value: await event.download(in_memory=True),
            },
            **({"caption": event.content.html} if event.content else {}),
            **(
                {
                    "thumb": await event._client.download_media(
                        media.thumbs[0], in_memory=True
                    )
                }
                if media.thumbs and "thumb" in args
                else {}
            ),
            **{
                k: v
                for k, v in media.__dict__.items()
                if k in args and k not in ("ttl_seconds", "protect_content")
            },
            disable_notification=True,
            reply_markup=self.ikm(
                (
                    "Message",
                    "url",
                    f"tg://openmessage?user_id={event.from_user.id}&message_id={event.id}",
                    "B",
                )
            ),
        )

    @handler(filters.regex(pattern), 3)
    async def on_inline_query(self, event: InlineQuery) -> None:
        await self.answer(
            event,
            message_text=(
                event.query.removesuffix("#").rstrip()
                if len(event.query) > 1
                else "<code>...</code>"
            ),
        )

    @handler(filters.regex(pattern), 4)
    async def on_inline_result(self, event: ChosenInlineResult) -> None:
        btn, (msg, cmd) = False, await self.msgs(event)
        if not msg:
            if len(event.query) <= 1:
                await cmd.delete()
                return

            btn, msg = True, cmd
        elif len(event.query) > 1:
            btn, msg = True, cmd

        await self.execute(msg, event, btn)

    @handler(filters.regex(r"^[01]$"), 5)
    async def on_inline_callback(self, event: CallbackQuery) -> None:
        msg, cmd = await self.msgs(event)
        if event.data == "0":
            task = next(
                (
                    t
                    for t in asyncio.all_tasks()
                    if t.get_name() == f"selfbot/{event.inline_message_id}"
                ),
                None,
            )
            if task:
                task.cancel()
                return

            await cmd.delete()
            return

        if msg is None:
            # Kartu rich: inline_message_id menunjuk pesan via bot — proses langsung
            try:
                if event.data == b"0":
                    await event.message.delete() if hasattr(event, "message") and event.message else None
                    return
            except Exception:
                pass
            await event.answer(r"¯\_(ツ)_/¯", show_alert=True)
            return

        await self.execute(msg, event)

    async def msgs(self, event: Update) -> tuple:
        cid, mid = self.ids(event.inline_message_id)
        msg, cmd = await asyncio.gather(
            self.client.app.get_messages(cid, mid, reply=True),
            self.client.app.get_messages(cid, mid),
            return_exceptions=True,
        )
        if isinstance(msg, Exception):
            msg = None

        return msg, cmd

    async def execute(self, msg: Message, event: Update, btn: bool = False) -> None:
        ikb, out, rtt = [[("Del", "data", b"0")]], "", ""
        if btn:
            code = event.query.removesuffix("#").rstrip()
            ikb[0].insert(0, ("Run", "switch_inline_query_current_chat", code))
        else:
            code = msg.content.markdown
            ikb[0].insert(0, ("Run", "data", b"1"))

        self.kwargs.update(
            {
                "msg": msg,
                "rep": msg.external_reply or msg.reply_to_message,
                "chat": msg.chat,
                "user": (msg.reply_to_message or msg).from_user,
                "event": event,
            }
        )
        if not isinstance(event, Message):
            await event.edit_message_reply_markup(
                reply_markup=self.ikm(("Cancel", "data", b"0"))
            )

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            fut = asyncio.create_task(
                self.aexec(code, self.kwargs),
                name=(
                    f"selfbot/{event.chat.id}/{event.id}"
                    if isinstance(event, Message)
                    else f"selfbot/{event.inline_message_id}"
                ),
            )
            now = datetime.datetime.now(datetime.UTC)
            try:
                res = await fut
            except (asyncio.CancelledError, Exception):
                out = self.fmtexc()
            else:
                out = (buf.getvalue() or str(res)).rstrip()
            finally:
                rtt = self.fmtsec(now)

        if code.endswith("return"):
            return

        if len(out) > 768:
            with io.BytesIO(out.encode()) as doc:
                doc.name = "Out.TXT"
                await self.respond(
                    event,
                    InputMediaDocument(
                        doc,
                        caption=f"<code>{html.escape(out[:512])}...</code>\n\n<b><blockquote>{rtt}</blockquote></b>",
                    ),
                    reply_markup=self.ikm(ikb),
                )
                return

        # Kartu rich ala debug kynan: Output + tabel Task ID/Elapsed/Length + tombol
        try:
            from pyrogram.raw import functions as rawfn
            from pyrogram.raw.types import (
                InputBotInlineMessageRichMessage,
                InputBotInlineResult,
            )
            from pyrogram.types import (
                InputRichBlockButtons,
                InputRichBlockParagraph,
                InputRichBlockTable,
                InputRichMessage,
                RichBlockTableCell,
                RichMessageButton,
                RichTextBold,
                RichTextCode,
            )
            from pyrogram.enums import ButtonStyle as _BS

            import uuid as _uuid
            task_id = str(getattr(event, "id", "")) or _uuid.uuid4().hex[:16]
            elapsed = rtt
            length = str(len(out))

            rows = [
                [RichBlockTableCell(text="Key", is_header=True, align="center"),
                 RichBlockTableCell(text="Value", is_header=True, align="center")],
                [RichBlockTableCell(text="Task ID", align="center"),
                 RichBlockTableCell(text=task_id, align="center")],
                [RichBlockTableCell(text="Elapsed", align="center"),
                 RichBlockTableCell(text=elapsed, align="center")],
                [RichBlockTableCell(text="Length", align="center"),
                 RichBlockTableCell(text=length, align="center")],
            ]
            blocks = [
                InputRichBlockParagraph(
                    text=f"<code>{html.escape(out)}</code>"
                ),
                InputRichBlockTable(
                    rows, is_bordered=True, is_striped=True, is_compact=True
                ),
            ]

            rich_btns = InputRichBlockButtons(
                [
                    RichMessageButton(
                        text=RichTextBold("🗑 Del"),
                        style=_BS.DANGER,
                        callback_data=b"0",
                    ),
                ]
            )
            blocks.append(rich_btns)
            rich_raw = await InputRichMessage(blocks=blocks).write(client=self.client.bot)

            bot = self.client.bot
            from pyrogram.handlers import RawUpdateHandler
            from pyrogram.raw.types import UpdateBotInlineQuery as _UBIQ

            ping_mod = self.client.modules.get("Ping")
            route = getattr(ping_mod, "_rich_route", None) if ping_mod else None
            if route is None:
                route = {}
                if ping_mod is not None:
                    ping_mod._rich_route = route

            if getattr(self, "_dbg_handler", None) is None:
                async def _dbg_answer(_c, update, users, chats):
                    if not isinstance(update, _UBIQ):
                        return
                    q = str(update.query)
                    if not q.startswith("dbg"):
                        return
                    p_rich, p_close = route.get("dbg", (None, None))
                    if p_rich is None:
                        return
                    with contextlib.suppress(Exception):
                        await bot.invoke(
                            rawfn.messages.SetInlineBotResults(
                                query_id=update.query_id,
                                results=[
                                    InputBotInlineResult(
                                        id=str(update.query_id),
                                        type="article",
                                        title="Debug Result",
                                        send_message=InputBotInlineMessageRichMessage(
                                            rich_message=p_rich,
                                            reply_markup=p_close,
                                        ),
                                    )
                                ],
                                cache_time=0,
                            )
                        )

                self._dbg_handler = RawUpdateHandler(_dbg_answer)
                disp = bot.dispatcher
                if -2 not in disp.groups:
                    disp.groups[-2] = []
                    disp.groups = dict(sorted(disp.groups.items()))
                disp.groups[-2].append(self._dbg_handler)

            route["dbg"] = (rich_raw, None)

            app = self.client.app
            res = await app.get_inline_bot_results(
                bot.me.id, f"dbg{datetime.datetime.now(datetime.UTC).timestamp()}"
            )
            if res and res.results:
                await app.send_inline_bot_result(
                    msg.chat.id, res.query_id, res.results[0].id
                )
                return
        except Exception as rich_err:
            self.logger.warning(f"debug rich failed: {rich_err!r}")

        await self.respond(
            event,
            f"<code>{html.escape(out)}</code>\n\n<b><blockquote>{rtt}</blockquote></b>",
            reply_markup=self.ikm(ikb),
        )
