import ast
import asyncio
import builtins
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

# py {kode python} — hanya pesan keluar dari akun sendiri
pattern = re.compile(r"^py[ \t\u00a0]+([\s\S]+)$", re.IGNORECASE)

_ZERO_WIDTH = dict.fromkeys(map(ord, "\u200b\u200c\u200d\ufeff"), None)
_LINE_PREFIX = re.compile(r"^\s*py[ \t]+", re.IGNORECASE)


def _clean(raw: str) -> str:
    """Buang NBSP/zero-width (sisa copy-paste dari Telegram)."""
    lines = raw.replace("\u00a0", " ").translate(_ZERO_WIDTH).splitlines()
    # Kalau user paste blok dengan prefix "py " di tiap baris, buang prefix-nya
    rest = [ln for ln in lines[1:] if ln.strip()]
    if rest and all(_LINE_PREFIX.match(ln) for ln in rest):
        lines = [lines[0]] + [_LINE_PREFIX.sub("", ln) for ln in lines[1:]]
    return "\n".join(lines).strip()


def _compile_async(code: str):
    """Code → AST async function; expression terakhir otomatis jadi return value."""
    tree = ast.parse(code, "<py>", "exec")
    if tree.body and isinstance(tree.body[-1], ast.Expr):
        last = tree.body.pop()
        tree.body.append(ast.Return(value=last.value))
    args = ast.arguments(
        posonlyargs=[],
        args=[ast.arg(arg="g")],
        vararg=None,
        kwonlyargs=[],
        kw_defaults=[],
        kwarg=None,
        defaults=[],
    )
    fn = ast.AsyncFunctionDef(
        name="__exec__",
        args=args,
        body=tree.body or [ast.Pass()],
        decorator_list=[],
        returns=None,
        type_comment=None,
    )
    mod = ast.Module(body=[fn], type_ignores=[])
    return compile(ast.fix_missing_locations(mod), "<py>", "exec")


class Py(Module):
    name = "Py Exec"
    cmds = "py {python_code}"
    desc = {
        "Info": "Eksekusi kode Python langsung dari chat (hanya pesan sendiri).",
        "Vars": "client, event, replied, asyncio, print",
        "Note": "Akhiri dengan '!' supaya pesan perintahnya ikut dihapus.",
        "e.g.": "py 21 * 2",
    }

    @handler(filters.regex(pattern) & filters.outgoing, 1)
    async def on_message_out(self, event: Message) -> None:
        match = pattern.match(event.text or "")
        if not match:
            return
        code = _clean(match.group(1))
        silent = code.endswith("!")
        if silent:
            code = code[:-1].rstrip()
        if not code:
            await self.respond(event, "<code>Usage: py {python_code}</code>")
            return

        status = await self.respond(event, "<code>⚙️ Executing...</code>")
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

        try:
            exec(_compile_async(code), glb)  # noqa: S102
            with contextlib.redirect_stdout(buf):
                result = await glb["__exec__"](glb)
        except asyncio.CancelledError:
            raise
        except BaseException as e:  # noqa: BLE001
            err = "".join(traceback.format_exception_only(type(e), e)).strip()
            hint = ""
            if isinstance(e, SyntaxError) and "U+" in err:
                hint = "\n<i>(karakter tersembunyi dari copy-paste — ketik ulang manual)</i>"
            await self._finish(status, event, f"❌ <b>Error</b>\n\n<code>{html.escape(err[:1500])}</code>{hint}", now, silent)
            return

        out = buf.getvalue().rstrip()
        if result is not None:
            out = (out + "\n" if out else "") + repr(result)
        if not out:
            out = "[No output]"
        await self._finish(status, event, f"<code>{html.escape(out[:4000])}</code>", now, silent)

    def _print(self, buf: io.StringIO):
        def p(*args, **kwargs):
            kwargs.setdefault("file", buf)
            builtins.print(*args, **kwargs)

        return p

    async def _finish(self, status, event: Message, text: str, now, silent: bool) -> None:
        with contextlib.suppress(Exception):
            await status.delete()
        if silent:
            with contextlib.suppress(Exception):
                await event.delete()
        await self.respond(event, f"{text}\n\n<b><blockquote>{self.fmtsec(now)}</blockquote></b>")
