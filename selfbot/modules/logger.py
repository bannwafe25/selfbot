from __future__ import annotations

import asyncio
import collections
import contextlib
import datetime
import html
import logging
import re

from pyrogram import filters
from pyrogram.types import Message

from selfbot.listener import handler
from selfbot.module import Module

pattern = re.compile(r"^\.?log(?:/(on|off|status))?$", re.IGNORECASE)

WIB = datetime.timezone(datetime.timedelta(hours=7))


class _GroupHandler(logging.Handler):
    """Kirim record logging ke antrean, nanti dikirim ke grup log."""

    def __init__(self, queue: collections.deque, level=logging.WARNING) -> None:
        super().__init__(level=level)
        self.queue = queue

    def emit(self, record: logging.LogRecord) -> None:
        with contextlib.suppress(Exception):
            self.queue.append(record)


class Logger(Module):
    name = "Group Log"
    cmds = "log(/{on|off|status})?"
    desc = {
        "on": "Aktifin log ke grup",
        "off": "Matiin log ke grup",
        "status": "Cek status log",
        "e.g.": "log/status",
    }

    def __init__(self, client) -> None:
        super().__init__(client)
        self.chat_id = None
        self.enabled = True
        self.queue: collections.deque = collections.deque(maxlen=200)
        self._task = None

    async def on_starting(self) -> None:
        raw = self.client.config.get("LOG_GROUP")
        if raw:
            try:
                self.chat_id = int(raw)
            except (TypeError, ValueError):
                self.chat_id = raw if raw.startswith("@") else f"@{raw.lstrip('@')}"

        if not self.chat_id:
            self.logger.warning("LOG_GROUP belum di-set, log grup dimatiin")
            self.enabled = False
            return

        # Pasang handler error -> grup log
        self._handler = _GroupHandler(self.queue, logging.WARNING)
        logging.getLogger().addHandler(self._handler)
        self._task = asyncio.create_task(self._drain())

    async def on_stopping(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(Exception):
                await self._task
        if getattr(self, "_handler", None):
            logging.getLogger().removeHandler(self._handler)

    async def _drain(self) -> None:
        """Kuras antrean tiap 3 detik, kirim ke grup log."""
        while True:
            try:
                await asyncio.sleep(3)
                if not self.queue or not self.enabled or not self.chat_id:
                    continue
                lines = []
                while self.queue and len(lines) < 10:
                    rec = self.queue.popleft()
                    lines.append(
                        f"  <code>{html.escape(rec.name)}</code> : "
                        f"<code>{html.escape(str(rec.getMessage())[:300])}</code>"
                    )
                if not lines:
                    continue
                await self.send(
                    f"<b>⚠️ Error Log</b>\n"
                    f"<blockquote>{'<br>'.join(lines)}</blockquote>"
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                pass

    async def send(self, text: str) -> None:
        """Kirim pesan ke grup log (silent, ga pernah raise)."""
        if not self.chat_id or not self.enabled:
            return
        with contextlib.suppress(Exception):
            await self.client.bot.send_message(
                self.chat_id,
                text,
                disable_notification=True,
            )

    @handler(filters.regex(pattern), 1)
    async def on_message_out(self, event: Message) -> None:
        match = pattern.match(event.text.strip())
        mode = (match.group(1) or "status").lower() if match else "status"

        if mode == "on":
            self.enabled = True
            text = "✅ Log grup <b>ON</b>"
        elif mode == "off":
            self.enabled = False
            text = "🚫 Log grup <b>OFF</b>"
        else:
            text = (
                f"<b>📋 Group Log</b>\n"
                f"<blockquote>"
                f"<code>Status </code> : "
                f"<code>{'ON' if self.enabled else 'OFF'}</code>\n"
                f"<code>Target</code> : <code>{self.chat_id or '-'}</code>\n"
                f"<code>Antrean</code> : <code>{len(self.queue)}</code>"
                f"</blockquote>"
            )
        await self.respond(event, text)

    @handler(filters.outgoing & filters.text, -100)
    async def on_command(self, event: Message) -> None:
        """Catat tiap command yang dijalanin."""
        if not self.chat_id or not self.enabled:
            return
        text = (event.text or "").strip()
        if not text or text.startswith((".log", "log/")):
            return
        chat = event.chat.title if event.chat else "-"
        waktu = datetime.datetime.now(WIB).strftime("%H:%M:%S")
        with contextlib.suppress(Exception):
            await self.client.bot.send_message(
                self.chat_id,
                (
                    f"<b>▶️ Command</b> <code>{waktu}</code>\n"
                    f"<blockquote>"
                    f"<code>Chat</code> : <code>{html.escape(str(chat))}</code>\n"
                    f"<code>Cmd </code> : <code>{html.escape(text[:200])}</code>"
                    f"</blockquote>"
                ),
                disable_notification=True,
            )
