import asyncio
import contextlib
import datetime
import html
import io
import re
import traceback

from pyrogram import filters
from pyrogram.types import Message

from selfbot.listener import handler
from selfbot.module import Module

# Hanya pesan keluar dari akun sendiri: py {kode python}
pattern = re.compile(r"^py\s+([\s\S]+)$", re.IGNORECASE)


class Py(Module):
    name = "Py Exec"
    cmds = "py {python_code}"
    desc = {
        "Info": "Eksekusi kode Python langsung dari chat (hanya pesan sendiri).",
        "Vars": "client, event, replied, msg, asyncio, selfbot",
        "Note": "Trailing '!' = tanpa echo input. Gagal = kirim ulang kode via file.",
        "e.g.": "py print(await client.get_me().username)",
    }

    @handler(filters.regex(pattern) & filters.outgoing, 1)
    async def on_message_out(self, event: Message) -> None:
        match = pattern.match(event.text or "")
        if not match:
            return
        code = match.group(1).strip()
        silent = code.endswith("!")
        if silent:
            code = code[:-1].rstrip()

        await self.respond(event, "<code>⚙️ Executing...</code>")
        now = datetime.datetime.now(datetime.UTC)

        buf = io.StringIO()
        glb = {
            "asyncio": asyncio,
            "client": self.client,
            "selfbot": self.client,
            "event": event,
            "msg": event,
            "replied": event.reply_to_message,
            "print": self._print(buf),
        }
        loc: dict = {}

        try:
            body = self._wrap(code)
            exec(compile(body, "<py>", "exec"), glb, loc)  # noqa: S102
            result = None
            with contextlib.redirect_stdout(buf):
                if asyncio.iscoroutinefunction(loc.get("__exec__")):
                    result = await loc["__exec__"](glb)
                else:
                    # sync snippet
                    result = eval(compile(code, "<py>", "eval"), glb, loc)  # noqa: S102
            out = buf.getvalue().rstrip()
            if result is not None:
                out = (out + "\n" if out else "") + repr(result)
        except BaseException as e:  # noqa: BLE001
            err = "".join(traceback.format_exception_only(type(e), e)).strip()
            await self._reply(event, f"❌ <b>Error</b>\n\n<code>{html.escape(err)}</code>", now)
            return

        if not out:
            out = "[No output]"
        if silent:
            with contextlib.suppress(Exception):
                await event.delete()
        await self._reply(event, f"<code>{html.escape(out[:4000])}</code>", now)

    def _print(self, buf: io.StringIO):
        import builtins

        def p(*args, **kwargs):
            kwargs.setdefault("file", buf)
            builtins.print(*args, **kwargs)

        return p

    def _wrap(self, code: str) -> str:
        """Bungkus multi-baris/await dalam async function."""
        body = "\n".join("    " + line for line in code.splitlines())
        return f"async def __exec__(g):\n    g = g\n{body}"

    async def _reply(self, event: Message, text: str, now) -> None:
        text = (
            f"{text}\n\n<b><blockquote>{self.fmtsec(now)}</blockquote></b>"
        )
        await self.respond(event, text)
