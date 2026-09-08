import asyncio
import datetime
import re

from pyrogram import filters
from pyrogram.errors import ChannelPrivate, PeerIdInvalid, RPCError
from pyrogram.types import Message

from selfbot.listener import handler, reply
from selfbot.module import Module

load = True
try:
    from pytgcalls import PyTgCalls
    from pytgcalls.types import GroupCallConfig, MediaStream
except Exception:
    load = False

pattern = re.compile(
    r"^call(?:\s-(start|end|join|leave))"
    r"(?:\s(@?[a-zA-Z][a-zA-Z0-9_]{2,31}[a-zA-Z0-9]|-100[1-9]\d{9}|[1-9]\d{1,9}))?"
    r"(?:\s-as\s(@?[a-zA-Z][a-zA-Z0-9_]{1,31}[a-zA-Z0-9]))?"
    r"(?:\s(-mute))?$"
)


class Call(Module):
    name = "Group Call"
    cmds = "call -{action} {chat}? (-as {peer})? (-mute)?"
    desc = {
        "action": "(join|leave|start|end)",
        "chat": "Chat ID or Username",
        "peer": "Username channel (join as)",
        "-mute": "Join dalam kondisi mute",
        "e.g.": "call -join @durov -mute",
    }

    async def on_loading(self) -> None:
        if not load:
            self.client.unload(self)
            return

        self.client.call = PyTgCalls(self.client.app)

    @handler(filters.regex(pattern) & ~reply, 1)
    async def on_message_out(self, event: Message) -> None:
        await event.edit_text("<code>...</code>")
        now, (action, chat_id, join_as, mute) = (
            datetime.datetime.now(datetime.UTC),
            pattern.match(event.text or event.caption).groups(),
        )

        if not chat_id:
            chat_id = event.chat.id
        else:
            try:
                chat = await event._client.get_chat(chat_id)
            except RPCError as e:
                await event.edit_text(f"❌ {e.__class__.__name__}: {e}")
                return
            chat_id = chat.id

        kwargs = {"chat_id": chat_id}
        join_as_id = None

        if action == "join":
            func = self.client.call.play
            head = "✅ Joined Call"
            if join_as:
                try:
                    peer = await event._client.resolve_peer(join_as)
                except RPCError as e:
                    await event.edit_text(f"❌ {e.__class__.__name__}: {e}")
                    return
                join_as_id = join_as
                kwargs["config"] = GroupCallConfig(join_as=peer)
        elif action == "leave":
            func = self.client.call.leave_call
            head = "👋 Left Call"
        elif action == "start":
            func = event._client.create_video_chat
            head = "🎤 Started Call"
        else:
            func = event._client.discard_group_call
            head = "🛑 Ended Call"

        try:
            await func(**kwargs)
        except RPCError as e:
            await event.edit_text(f"❌ {e.__class__.__name__}: {e}")
            return

        col = self.client.db["call_chats"]

        if action == "join":
            if mute:
                await self.client.call.mute(chat_id)
            else:
                await self.client.call.unmute(chat_id)

            await col.update_one(
                {"chat_id": chat_id},
                {"$set": {"chat_id": chat_id, "join_as": join_as_id, "mute": bool(mute)}},
                upsert=True,
            )
        elif action == "leave":
            await col.delete_one({"chat_id": chat_id})

        extra = []
        if join_as_id:
            extra.append(f"Join as: <code>{join_as_id}</code>")
        if mute:
            extra.append("Mute: <code>True</code>")

        dur = (datetime.datetime.now(datetime.UTC) - now).total_seconds()
        await event.edit_text(
            f"{head}\n" + ("\n".join(extra) + "\n" if extra else "")
            + f"<code>{dur:.2f}s</code>"
        )
