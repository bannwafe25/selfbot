import datetime
import re

from pyrogram import filters
from pyrogram.errors import RPCError
from pyrogram.types import Message

from selfbot.listener import handler, reply
from selfbot.module import Module


# ============================================================
# PyTgCalls
# ============================================================

load = True

try:
    from pytgcalls import PyTgCalls
    from pytgcalls.types import GroupCallConfig, MediaStream
except Exception:
    load = False


# ============================================================
# Command pattern
# ============================================================

pattern = re.compile(
    r"^call(?:\s-(start|end|join|leave))"
    r"(?:\s(@?[a-zA-Z][a-zA-Z0-9_]{2,31}[a-zA-Z0-9]|-100[1-9]\d{9}|[1-9]\d{1,9}))?"
    r"(?:\s-as\s(@?[a-zA-Z][a-zA-Z0-9_]{1,31}[a-zA-Z0-9]))?"
    r"(?:\s(-mute))?$"
)


# ============================================================
# Call Module
# ============================================================

class Call(Module):
    name = "Group Call"

    cmds = "call -{action} {chat}? (-as {peer})? (-mute)?"

    desc = {
        "action": "(join|leave|start|end)",
        "chat": "Chat ID or Username",
        "peer": "Username channel (join as)",
        "-mute": "Join dalam kondisi mute",
        "e.g.": "call -join @nama_grup -mute",
    }

    # --------------------------------------------------------
    # Init
    # --------------------------------------------------------

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Jangan simpan PyTgCalls di self.client.
        # Selfbot mungkin tidak mengizinkan attribute tambahan.
        self.call = None

    # --------------------------------------------------------
    # Safe message edit
    # --------------------------------------------------------

    async def _status(self, event: Message, text: str):
        """
        Edit command message.

        Jika Telegram mengembalikan MESSAGE_ID_INVALID,
        coba kirim reply baru sebagai fallback.
        """

        try:
            return await event.edit_text(text)

        except RPCError:
            try:
                return await event.reply_text(text)

            except RPCError:
                return None

        except Exception:
            try:
                return await event.reply_text(text)

            except Exception:
                return None

    # --------------------------------------------------------
    # Get / start PyTgCalls
    # --------------------------------------------------------

    async def _get_call(self):
        """
        Membuat PyTgCalls hanya sekali dan memastikan
        instance sudah di-start sebelum digunakan.
        """

        if not load:
            raise RuntimeError(
                "PyTgCalls tidak berhasil di-import."
            )

        if self.call is None:
            self.call = PyTgCalls(self.client.app)

            await self.call.start()

        return self.call

    # --------------------------------------------------------
    # Handler
    # --------------------------------------------------------

    @handler(filters.regex(pattern) & ~reply, 1)
    async def on_message_out(self, event: Message) -> None:

        # ----------------------------------------------------
        # Parse command
        # ----------------------------------------------------

        text = event.text or event.caption or ""

        match = pattern.match(text)

        if not match:
            return

        action, chat_id, join_as, mute = match.groups()

        # ----------------------------------------------------
        # Loading
        # ----------------------------------------------------

        await self._status(
            event,
            "<code>⏳ Processing...</code>"
        )

        now = datetime.datetime.now(datetime.UTC)

        # ----------------------------------------------------
        # Resolve chat
        # ----------------------------------------------------

        if not chat_id:
            chat_id = event.chat.id

        else:
            try:
                chat = await event._client.get_chat(chat_id)

                chat_id = chat.id

            except RPCError as e:
                await self._status(
                    event,
                    f"❌ {e.__class__.__name__}: {e}"
                )
                return

            except Exception as e:
                await self._status(
                    event,
                    f"❌ {e.__class__.__name__}: {e}"
                )
                return

        # ----------------------------------------------------
        # Arguments
        # ----------------------------------------------------

        kwargs = {
            "chat_id": chat_id
        }

        join_as_id = None

        # ----------------------------------------------------
        # JOIN
        # ----------------------------------------------------

        if action == "join":

            try:
                call = await self._get_call()

            except Exception as e:
                await self._status(
                    event,
                    f"❌ PyTgCalls Error:\n"
                    f"<code>{e.__class__.__name__}: {e}</code>"
                )
                return

            func = call.play

            head = "✅ Joined Call"

            # ------------------------------------------------
            # Join as
            # ------------------------------------------------

            if join_as:

                try:
                    peer = await event._client.resolve_peer(
                        join_as
                    )

                except RPCError as e:
                    await self._status(
                        event,
                        f"❌ {e.__class__.__name__}: {e}"
                    )
                    return

                except Exception as e:
                    await self._status(
                        event,
                        f"❌ {e.__class__.__name__}: {e}"
                    )
                    return

                join_as_id = join_as

                kwargs["config"] = GroupCallConfig(
                    join_as=peer
                )

        # ----------------------------------------------------
        # LEAVE
        # ----------------------------------------------------

        elif action == "leave":

            try:
                call = await self._get_call()

            except Exception as e:
                await self._status(
                    event,
                    f"❌ PyTgCalls Error:\n"
                    f"<code>{e.__class__.__name__}: {e}</code>"
                )
                return

            func = call.leave_call

            head = "👋 Left Call"

        # ----------------------------------------------------
        # START
        # ----------------------------------------------------

        elif action == "start":

            func = event._client.create_video_chat

            head = "🎤 Started Call"

        # ----------------------------------------------------
        # END
        # ----------------------------------------------------

        elif action == "end":

            func = event._client.discard_group_call

            head = "🛑 Ended Call"

        else:
            return

        # ----------------------------------------------------
        # Execute Telegram / PyTgCalls action
        # ----------------------------------------------------

        try:
            await func(**kwargs)

        except RPCError as e:
            await self._status(
                event,
                f"❌ {e.__class__.__name__}: {e}"
            )
            return

        except Exception as e:
            await self._status(
                event,
                f"❌ {e.__class__.__name__}:\n"
                f"<code>{e}</code>"
            )
            return

        # ----------------------------------------------------
        # Database
        # ----------------------------------------------------

        try:
            col = self.client.db["call_chats"]

        except Exception as e:
            await self._status(
                event,
                f"❌ Database Error:\n"
                f"<code>{e.__class__.__name__}: {e}</code>"
            )
            return

        # ----------------------------------------------------
        # JOIN database / mute
        # ----------------------------------------------------

        if action == "join":

            try:
                call = await self._get_call()

                if mute:
                    await call.mute(chat_id)

                else:
                    await call.unmute(chat_id)

            except Exception as e:
                await self._status(
                    event,
                    f"❌ Call audio error:\n"
                    f"<code>{e.__class__.__name__}: {e}</code>"
                )
                return

            # ------------------------------------------------
            # Save configuration
            # ------------------------------------------------

            try:
                await col.update_one(
                    {"chat_id": chat_id},
                    {
                        "$set": {
                            "join_as": join_as_id,
                            "mute": bool(mute),
                        }
                    },
                    upsert=True,
                )

            except Exception as e:
                await self._status(
                    event,
                    f"❌ Database Error:\n"
                    f"<code>{e.__class__.__name__}: {e}</code>"
                )
                return

        # ----------------------------------------------------
        # LEAVE database
        # ----------------------------------------------------

        elif action == "leave":

            try:
                await col.delete_one(
                    {
                        "chat_id": chat_id
                    }
                )

            except Exception as e:
                await self._status(
                    event,
                    f"❌ Database Error:\n"
                    f"<code>{e.__class__.__name__}: {e}</code>"
                )
                return

        # ----------------------------------------------------
        # Extra information
        # ----------------------------------------------------

        extra = []

        if join_as_id:

            extra.append(
                f"Join as: <code>{join_as_id}</code>"
            )

        if mute and action == "join":

            extra.append(
                "Mute: <code>True</code>"
            )

        # ----------------------------------------------------
        # Duration
        # ----------------------------------------------------

        dur = (
            datetime.datetime.now(datetime.UTC) - now
        ).total_seconds()

        # ----------------------------------------------------
        # Final response
        # ----------------------------------------------------

        result = (
            f"<b>{head}</b>\n"
            + (
                "\n".join(extra) + "\n"
                if extra
                else ""
            )
            + f"<code>{dur:.2f}s</code>"
        )

        await self._status(
            event,
            result
        )
