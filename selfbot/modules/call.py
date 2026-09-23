import asyncio
import base64
import contextlib
import datetime
import re
import struct

from pyrogram import filters, raw
from pyrogram.errors import RPCError
from pyrogram.types import (
    InputRichBlockParagraph,
    InputRichBlockTable,
    InputRichBlockButtons,
    RichMessageButton,
    InputRichMessage,
    Message,
    RichBlockTableCell,
    RichTextBold,
    RichTextCode,
)
from pyrogram.enums import ButtonStyle

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
    # Rich native table via inline bot (kurigram 2.2.26+)
    # --------------------------------------------------------

    async def _rich_status_table(
        self, event: Message, title: str, lines: list
    ):
        """
        Coba kirim status sebagai rich table via inline bot
        (muncul atas nama user, via @bot). Fallback ke HTML.
        """
        try:
            import re as _re

            bot = self.client.bot
            # buka inline query dari userbot ke bot
            res = await event._client.get_inline_bot_results(
                bot.me.id, "call_status"
            )
            if not res.results:
                raise RuntimeError("no inline results")

            rows = [[RichBlockTableCell(text=RichTextBold(title), is_header=True)]]
            for line in lines:
                plain = _re.sub(r"<[^>]+>", "", line or "").strip()
                if plain:
                    rows.append([RichBlockTableCell(text=plain)])

            rich = InputRichMessage(
                blocks=[
                    InputRichBlockParagraph(text=RichTextBold(title)),
                    InputRichBlockTable(
                        cells=rows, is_bordered=True, is_striped=True
                    ),
                    InputRichBlockButtons(
                        [
                            RichMessageButton(
                                text=RichTextBold("🗑 Close"),
                                style=ButtonStyle.DANGER,
                                callback_data=b"0",
                            )
                        ]
                    ),
                ]
            )
            rich_raw = await rich.write(client=bot)

            from pyrogram.raw import functions as rawfn
            from pyrogram.raw.types import (
                InputBotInlineMessageRichMessage,
                InputBotInlineResult,
            )

            await bot.invoke(
                rawfn.messages.SetInlineBotResults(
                    query_id=res.query_id,
                    results=[
                        InputBotInlineResult(
                            id=datetime.datetime.now(datetime.UTC).timestamp().hex(),
                            type="rich",
                            send_message=InputBotInlineMessageRichMessage(
                                rich_message=rich_raw,
                            ),
                        )
                    ],
                    cache_time=0,
                )
            )
            await event.reply_inline_bot_result(
                res.query_id, res.results[0].id
            )
            with contextlib.suppress(Exception):
                await event.delete()
            return
        except Exception as e:
            with contextlib.suppress(Exception):
                self.logger.warning(f"call rich inline failed: {e!r}")

        return await self._rich_status(event, title, lines)

    # --------------------------------------------------------
    # Final rich table via inline bot (pola ping.py)
    # --------------------------------------------------------

    async def _rich_final(self, event: Message, title: str, extra: list, dur: float, chat_label: str = "-"):
        """Kirim hasil call sebagai rich table via inline bot (fallback HTML)."""
        import html as _html

        try:
            bot = self.client.bot
            from pyrogram.raw import functions as rawfn
            from pyrogram.raw.types import (
                InputBotInlineMessageRichMessage,
                InputBotInlineResult,
            )
            from pyrogram.raw.types import UpdateBotInlineQuery
            from pyrogram.handlers import RawUpdateHandler

            import contextlib as _cl

            rows = [
                [
                    RichBlockTableCell(text="Parameter", is_header=True),
                    RichBlockTableCell(text="Keterangan", is_header=True),
                ],
                [
                    RichBlockTableCell(text="Aksi"),
                    RichBlockTableCell(text=_html.unescape(re.sub(r"<[^>]+>", "", title.split(" ⚡ ")[0]))),
                ],
                [
                    RichBlockTableCell(text="Chat"),
                    RichBlockTableCell(text=chat_label),
                ],
            ]
            for line in extra:
                plain = re.sub(r"<[^>]+>", "", line or "").strip()
                if ":" in plain:
                    k, v = plain.split(":", 1)
                    rows.append(
                        [RichBlockTableCell(text=k.strip()), RichBlockTableCell(text=v.strip())]
                    )
            rows.append(
                [
                    RichBlockTableCell(text="Total Waktu"),
                    RichBlockTableCell(text=f"{dur:.2f}s"),
                ]
            )
            rows.append(
                [
                    RichBlockTableCell(text="Status Akhir"),
                    RichBlockTableCell(text="✅ Selesai"),
                ]
            )

            blocks = [
                InputRichBlockParagraph(text=RichTextBold(title.split(" ⚡ ")[0])),
                InputRichBlockTable(
                    rows, is_bordered=True, is_striped=True, is_compact=True
                ),
                # Tombol rich Close (merah) — di dalam kartu
                InputRichBlockButtons(
                    [
                        RichMessageButton(
                            text=RichTextBold("🗑 Close"),
                            style=ButtonStyle.DANGER,
                            callback_data=b"0",
                        )
                    ]
                ),
            ]

            rich_raw = await InputRichMessage(blocks=blocks).write(client=bot)
            close_raw = None

            # Daftarkan payload ke handler BERSAMA milik ping (group -2),
            # satu-satunya raw handler yang terpasang di dispatcher bot.
            self._rich_payload = (rich_raw, close_raw)

            async def _h(_c, update, users, chats):
                pass

            ping_mod = getattr(self.client, "ping_module", None)
            route = getattr(ping_mod, "_rich_route", None) if ping_mod else None
            if route is None:
                # Fallback: cari module instance "Ping" di extender
                try:
                    ping_mod = self.client.modules.get("Ping")
                    route = getattr(ping_mod, "_rich_route", None) if ping_mod else None
                except Exception:
                    route = None
            if route is not None:
                route["call"] = self._rich_payload
            handler_ready = route is not None

            res = None
            if handler_ready:
                res = await event._client.get_inline_bot_results(
                    bot.me.id, f"call{datetime.datetime.now(datetime.UTC).timestamp()}"
                )

            if res.results:
                await asyncio.gather(
                    event.reply_inline_bot_result(res.query_id, res.results[0].id),
                    event.delete(),
                )
                return
        except Exception as e:
            with contextlib.suppress(Exception):
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
