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
            "pyrogram": pyrogram,
            "raw": pyrogram.raw,
            "enums": pyrogram.enums,
            "types": pyrogram.types,
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
                    else:
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
                    revoke=2.5,
                )

            return

        if event.content.endswith("#"):
            _, res = await asyncio.gather(
                self.respond(
                    event,
                    html.escape(event.content.markdown).removesuffix("#").rstrip(),
                ),
                event._client.get_inline_bot_results(
                    self.client.bot.me.id, "#", chat_id=event.chat.id
                ),
            )
            await event.reply_inline_bot_result(
                res.query_id,
                res.results[0].id,
                reply_parameters=ReplyParameters(message_id=event.id),
            )
            return

        cmd, msg = await asyncio.gather(
            self.respond(
                event, html.escape(event.content.markdown).removeprefix("e").lstrip()
            ),
            self.respond(event, "<code>...</code>", reply=True),
        )
        await self.execute(cmd, msg)

    @handler(filters.private & filters.self_destruct, 2)
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

        if msg.empty:
            await event.answer(r"¯\_(ツ)_/¯", show_alert=True)
            return

        await self.execute(msg, event)

    async def msgs(self, event: Update) -> tuple:
        cid, mid = self.ids(event.inline_message_id)
        msg, cmd = await asyncio.gather(
            self.client.app.get_replied_message(cid, mid),
            self.client.app.get_messages(cid, mid),
            return_exceptions=True,
        )
        if isinstance(msg, Exception):
            msg = None

        return msg, cmd

    async def execute(self, msg: Message, event: Update, btn: bool = False) -> None:
        ikb, out, rtt = [[("Del", b"0")]], "", ""
        if btn:
            code = event.query.removesuffix("#").rstrip()
            ikb[0].insert(0, ("Run", "switch_inline_query_current_chat", code))
        else:
            code = msg.content.markdown
            ikb[0].insert(0, ("Run", "1"))

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
                reply_markup=self.ikm(("Cancel", b"0"))
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

        await self.respond(
            event,
            f"<code>{html.escape(out)}</code>\n\n<b><blockquote>{rtt}</blockquote></b>",
            reply_markup=self.ikm(ikb),
        )
