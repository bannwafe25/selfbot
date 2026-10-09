import asyncio
import contextlib
import html
import re

from pyrogram import filters
from pyrogram.enums import ChatType
from pyrogram.errors import (
    ChannelPrivate,
    ChatWriteForbidden,
    FloodWait,
    Forbidden,
    SlowmodeWait,
    UserBannedInChannel,
)
from pyrogram.types import Message

from selfbot.listener import handler
from selfbot.module import Module

BC_PATTERN = re.compile(
    r"^\.?bc(?:\s+(global|all|group|private|channel))?(?:\s+([\s\S]+))?\s*$",
    re.IGNORECASE,
)

CHAT_TYPES = {
    "global": [ChatType.CHANNEL, ChatType.GROUP, ChatType.SUPERGROUP],
    "all": [ChatType.GROUP, ChatType.SUPERGROUP, ChatType.PRIVATE],
    "group": [ChatType.GROUP, ChatType.SUPERGROUP],
    "private": [ChatType.PRIVATE],
    "channel": [ChatType.CHANNEL],
}


class Broadcast(Module):
    name = "Broadcast"
    cmds = "bc {global|all|group|private|channel}"
    desc = {
        "global": "Semua grup + channel (default)",
        "all": "Grup + private",
        "group": "Cuma grup",
        "private": "Cuma private chat",
        "channel": "Cuma channel",
        "reply": "Bisa reply pesan/media buat di-broadcast",
        "e.g.": "bc group promo hari ini",
    }

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._cancel = set()  # task id yang dibatalkan
        self._last_task = None

    @handler(filters.regex(BC_PATTERN), 1)
    async def on_message_out(self, event: Message) -> None:
        text = str(event.content).strip()
        m = BC_PATTERN.match(text)
        scope = (m.group(1) or "global").lower()
        inline_text = m.group(2)

        # Sumber isi broadcast: reply > teks setelah command
        target = event.reply_to_message
        if not target and not inline_text:
            await self.respond(
                event,
                "Pakai: <code>bc {scope} teks</code> atau <b>reply</b> pesan lalu <code>bc {scope}</code>",
            )
            return

        task_id = id(event) % 100000
        self._cancel.discard(task_id)
        self._last_task = task_id

        await self.respond(
            event,
            f"📡 <b>Broadcast dimulai</b> (scope: {scope})\n"
            f"Kirim <code>.bccancel</code> buat batalkan.",
        )

        chat_ids = await self._collect_chats(scope)
        done, failed = 0, 0
        errors: list[str] = []

        for chat_id in chat_ids:
            if task_id in self._cancel:
                await self.respond(event, f"⛔ <b>Broadcast dibatalkan.</b> Done: {done}, Failed: {failed}")
                return
            try:
                if target:
                    await target.copy(chat_id)
                else:
                    await self.client.app.send_message(chat_id, inline_text)
                done += 1
            except (FloodWait, SlowmodeWait) as e:
                await asyncio.sleep(min(getattr(e, "value", 5), 30))
                with contextlib.suppress(Exception):
                    if target:
                        await target.copy(chat_id)
                    else:
                        await self.client.app.send_message(chat_id, inline_text)
                    done += 1
            except ChannelPrivate:
                failed += 1
            except ChatWriteForbidden:
                failed += 1
                errors.append(f"dimute: {chat_id}")
            except Forbidden:
                failed += 1
                errors.append(f"antispam: {chat_id}")
            except UserBannedInChannel:
                failed += 1
                errors.append(f"akun limit: {chat_id}")
            except Exception as e:
                failed += 1
                errors.append(f"{chat_id}: {str(e)[:40]}")

            await asyncio.sleep(1.5)  # anti-flood jeda antar chat

        report = (
            f"✅ <b>Broadcast selesai</b>\n\n"
            f"  <b>Done</b>   : {done}\n"
            f"  <b>Failed</b> : {failed}\n"
            f"  <b>Scope</b>  : {scope}\n"
        )
        if errors:
            report += "\n<b>Detail gagal:</b>\n<code>" + html.escape("\n".join(errors[:10])) + "</code>"
        await self.respond(event, report)

    @handler(filters.regex(r"^\.?bccancel\s*$"), 2)
    async def on_cancel(self, event: Message) -> None:
        # batalkan broadcast aktif
        if self._last_task is not None:
            self._cancel.add(self._last_task)
        await self.respond(event, "🛑 <b>Mencancel broadcast...</b>")

    async def _collect_chats(self, scope: str) -> list[int]:
        wanted = CHAT_TYPES.get(scope, CHAT_TYPES["global"])
        ids = []
        async for dialog in self.client.app.get_dialogs():
            chat = dialog.chat
            if chat and chat.type in wanted:
                ids.append(chat.id)
        return ids
