import asyncio
import contextlib
import datetime
import re

from pyrogram import filters, raw
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
    r"^call(?:\s-(start|end|join|leave))?"
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
    # Rich native message (kurigram 2.2.26+)
    # --------------------------------------------------------

    async def _rich_status(self, event: Message, title: str, lines: list):
        """
        Kirim status dengan format HTML bersih.
        """
        text = f"<b>{title}</b>"
        for line in lines:
            if line:
                text += f"\n{line}"

        return await self._status(event, text)

    # --------------------------------------------------------
    # Final rich table via inline bot (pola ping.py)
    # --------------------------------------------------------

    async def _rich_final(self, event: Message, title: str, extra: list, dur: float, chat_label: str = "-"):
        """Kirim hasil call sebagai blok collapsible (details) + tombol Close."""
        import richpyro as rp
        from pyrogram.enums import ButtonStyle

        head = title.split(" ⚡ ")[0]

        # Tabel hasil call
        _icon = {"Chat": "💬", "Total Waktu": "⏱", "Status Akhir": "📶"}
        trows = [[rp.table_cell(rp.bold(head), is_header=True, colspan=2, align="center")]]
        trows.append([
            rp.table_cell(rp.bold("💬 Chat"), align="center"),
            rp.table_cell(chat_label, align="center"),
        ])
        for line in extra:
            plain = re.sub(r"<[^>]+>", "", line or "").strip()
            if plain and ":" in plain:
                k, v = plain.split(":", 1)
                trows.append([
                    rp.table_cell(rp.bold(_icon.get(k.strip(), "•") + " " + k.strip()), align="center"),
                    rp.table_cell(v.strip(), align="center"),
                ])
        trows.append([
            rp.table_cell(rp.bold("⏱ Total Waktu"), align="center"),
            rp.table_cell(f"{dur:.2f}s", align="center"),
        ])
        trows.append([
            rp.table_cell(rp.bold("📶 Status Akhir"), align="center"),
            rp.table_cell("✅ Selesai", align="center"),
        ])

        blocks = [
            rp.table(trows, bordered=True, striped=True, compact=False),
            rp.expandable_quote(rp.italic(f"Waktu eksekusi {dur:.2f}s")),
            rp.buttons(
                rp.btn(rp.bold("🗑 Close"), callback_data=b"0", style=ButtonStyle.DANGER)
            ),
        ]

        try:
            bot = self.client.bot
            from pyrogram.raw import functions as rawfn
            from pyrogram.raw.types import (
                InputBotInlineMessageRichMessage,
                InputBotInlineResult,
            )
            from pyrogram.handlers import RawUpdateHandler
            from pyrogram.raw.types import UpdateBotInlineQuery

            rich_raw = await rp.blocks_message(*blocks).write(client=bot)

            ping_mod = self.client.modules.get("Ping")
            route = getattr(ping_mod, "_rich_route", None) if ping_mod else None
            if route is None and ping_mod is not None:
                self._ensure_rich_handler(
                    ping_mod,
                    rawfn,
                    InputBotInlineMessageRichMessage,
                    InputBotInlineResult,
                )
                route = getattr(ping_mod, "_rich_route", None)
            if route is not None:
                route["call"] = (rich_raw, None)

                res = await event._client.get_inline_bot_results(
                    bot.me.id, f"call{datetime.datetime.now(datetime.UTC).timestamp()}"
                )
                if res and res.results:
                    await asyncio.gather(
                        event.reply_inline_bot_result(res.query_id, res.results[0].id),
                        event.delete(),
                    )
                    return
        except Exception as e:
            self.logger.warning(f"call rich failed, fallback html: {e!r}")

        lines = [f"  <code>{_l}</code>" for _l in extra]
        await self._rich_status(event, title, lines)

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

        # Default: `call` / `call @chat` = join langsung mute
        if action is None:
            action = "join"
            mute = mute or "-mute"

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
                if chat_id.lstrip("-").isdigit():
                    chat_id = int(chat_id)
                chat = await event._client.get_chat(chat_id)

                chat_id = chat.id

            except RPCError as e:
                self.logger.warning(f"resolve chat failed: {e!r}")
                await self._status(
                    event,
                    f"❌ {e.__class__.__name__}: {e}"
                )
                return

            except Exception as e:
                self.logger.warning(f"resolve chat failed: {e!r}")
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

        title = f"{head} ⚡ {dur:.2f}s"
        lines = list(extra) or [""]

        try:
            chat_label = getattr(chat, "title", None) or getattr(chat, "username", None) or str(chat_id)
        except Exception:
            chat_label = str(chat_id)

        await self._rich_final(event, title, extra, dur, chat_label=chat_label)

        # Auto-delete disabled at user request (Sep 23)
        # if action in ("join", "leave", "start", "end"):
        #     await asyncio.sleep(2)
        #     with contextlib.suppress(Exception):
        #         await event.delete()
