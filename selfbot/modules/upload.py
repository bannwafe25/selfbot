import asyncio
import datetime
import re

from pyrogram import filters
from pyrogram.errors import RPCError
from pyrogram.types import Message, ReplyParameters

from selfbot.listener import fltrep, handler
from selfbot.module import Module

pattern = re.compile(
    r"^ul\s(.+?)(?:\s-to\s"
    r"(me|@?[a-zA-Z][a-zA-Z0-9_]{2,31}[a-zA-Z0-9]|-100[1-9]\d{9}|[1-9]\d{1,9}))?$"
)


class Upload(Module):
    name = "Upload Document"
    cmds = "ul {path} (-to {chat})?"
    desc = {
        "path": "String",
        "chat": "Chat ID or Username",
        "?": "Optional",
        "e.g.": "ul /root/temp.bin",
    }

    @handler(filters.regex(pattern) & ~fltrep, 1)
    async def on_message_out(self, event: Message) -> None:
        await self.respond(event, "<code>...</code>")
        rep_msg, (document, chat_id) = None, pattern.match(event.content).groups()
        if not chat_id:
            chat_id = event.chat.id
            rep_msg = ReplyParameters(message_id=event.id)

        fut = asyncio.create_task(
            event._client.send_document(
                chat_id,
                document,
                reply_parameters=rep_msg,
                progress=self.progress,
                progress_args=(event, "Uploading..."),
            ),
            name=f"selfbot/{event.chat.id}/{event.id}",
        )
        now = datetime.datetime.now(datetime.UTC)
        try:
            res = await fut
        except (asyncio.CancelledError, RPCError) as e:
            await self.respond(
                event,
                self.fmtmsg(
                    e.__class__.__name__,
                    (
                        e.MESSAGE.format(value=e.value)
                        if isinstance(e, RPCError)
                        else str(e)
                    ),
                    self.fmtsec(now),
                ),
                revoke=2.5,
            )
        else:
            await self.respond(
                event,
                self.fmtmsg(
                    "Document Uploaded",
                    {
                        "Chat ID": f"{res.chat.id}\n",
                        "File Name": res.document.file_name,
                        "File Size": f"{self.fmtbyte(res.document.file_size)}\n",
                        "MIME Type": res.document.mime_type,
                    },
                    self.fmtsec(now),
                ),
            )
