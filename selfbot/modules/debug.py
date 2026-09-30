import asyncio
import contextlib
import datetime
import html
import io
import re
import traceback

import pyrogram
from pyrogram import filters
from pyrogram.types import (
    CallbackQuery,
    Message,
)

from selfbot.listener import handler
from selfbot.module import Module

# ── Trigger ──
#   e {kode}      → eksekusi (multi-baris boleh, ekspresi terakhir = output)
#   e {kode}!     → eksekusi lalu hapus pesan perintah
#   #  (reply)    → cancel task debug di pesan itu
#   #  (sendiri)  → cancel semua task debug
pattern = re.compile(r"^e\s([\s\S]+?)(!)?$", flags=re.DOTALL)


class Debug(Module):
    name = "Debug"
    cmds = "e {code}[!]"
    desc = {
        "code": "Python async — ekspresi terakhir otomatis jadi output.",
        "!": "Opsional: hapus pesan perintah setelah jalan.",
        "vars": "app bot db me event msg rep chat user music call MediaStream http asyncio io re",
        "e.g.": "e print(me.first_name)",
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
            "aexec": self.aexec,
            "shell": self.shell,
            "client": self.client,
            "db": self.client.db,
            "app": self.client.app,
            "bot": self.client.bot,
            "http": self.client.http,
            "loop": self.client.loop,
            "fmtsec": self.fmtsec,
            "listen": self.listen,
            "respond": self.respond,
            "progress": self.progress,
        }

    async def on_started(self) -> None:
        # music/VC: PyTgCalls assistant + MediaStream
        with contextlib.suppress(Exception):
            music = self.client.modules.get("Music")
            if music is not None and getattr(music, "call", None) is not None:
                from pytgcalls.types import MediaStream

                self.kwargs["music"] = music
                self.kwargs["call"] = music.call
                self.kwargs["MediaStream"] = MediaStream

    # ── Handlers ──────────────────────────────────────────────────────────
    @handler(filters.regex(pattern), 1)
    async def on_message_out(self, event: Message) -> None:
        content = str(event.content or "").strip()

        # "#" → cancel task debug
        if content == "#":
            target = (
                f"selfbot/{event.chat.id}/{event.reply_to_message_id}"
                if event.reply_to_message
                else None
            )
            killed = 0
            for task in asyncio.all_tasks():
                if not task.get_name().startswith("selfbot/"):
                    continue
                if target and task.get_name() != target:
                    continue
                task.cancel()
                killed += 1
            if killed:
                with contextlib.suppress(Exception):
                    await self.respond(event, f"🛑 Cancel {killed} task", revoke=5)
            return

        m = pattern.match(str(event.content or ""))
        if not m:
            return
        code, strip_cmd = m.group(1), bool(m.group(2))

        status = await self.respond(event, "<code>...</code>", reply=True)
        out, rtt = await self._run(code, event)
        with contextlib.suppress(Exception):
            await status.edit(
                self._fmt(out, rtt),
                reply_markup=self.ikm(("🗑 Del", "data", b"0")),
            )
        if strip_cmd:
            with contextlib.suppress(Exception):
                await event.delete()

    @handler(filters.regex(r"^0$"), 5)
    async def on_inline_callback(self, event: CallbackQuery) -> None:
        if not isinstance(event, CallbackQuery):
            return
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
        with contextlib.suppress(Exception):
            await event.answer("ok")
        cid, mid = self.ids(event.inline_message_id)
        with contextlib.suppress(Exception):
            await self.client.app.delete_messages(cid, mid)

    # ── Core ──────────────────────────────────────────────────────────────
    async def _run(self, code: str, event: Message) -> tuple[str, str]:
        """Eksekusi kode → (output, waktu)."""
        kw = dict(self.kwargs)
        kw.update(
            {
                "me": await self.client.app.get_me(),
                "event": event,
                "msg": event,
                "chat": getattr(event, "chat", None),
                "rep": getattr(event, "reply_to_message", None),
                "user": getattr(event, "from_user", None),
            }
        )
        buf = io.StringIO()
        now = datetime.datetime.now(datetime.UTC)
        with contextlib.redirect_stdout(buf):
            try:
                res = await self.aexec(code, kw)
            except BaseException as e:
                out = "".join(
                    traceback.format_exception(type(e), e, e.__traceback__)
                ).rstrip()
            else:
                printed = buf.getvalue().rstrip()
                out = printed if printed else ("" if res is None else str(res))
        return out or "(kosong)", self.fmtsec(now)

    def _fmt(self, out: str, rtt: str) -> str:
        text = f"<pre>{html.escape(out[:3800])}</pre>"
        if len(out) > 3800:
            text += f"\n<i>… terpotong ({len(out)} chars total)</i>"
        return f"{text}\n<b><blockquote>{rtt}</blockquote></b>"
