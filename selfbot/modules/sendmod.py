import datetime
import html
import inspect
import re
from pathlib import Path

from pyrogram import filters
from pyrogram.types import Message

from selfbot.listener import handler
from selfbot.module import Module

pattern = re.compile(r"^(sendmod|sm)(?:\s+([a-zA-Z0-9_]+))?$", re.IGNORECASE)


class SendMod(Module):
    name = "Send Module"
    cmds = "sendmod|sm {module_name}"
    desc = {
        "module_name": "Module filename or class/module name.",
        "e.g.": "sendmod ping",
    }

    @handler(filters.regex(pattern), 1)
    async def on_message_out(self, event: Message) -> None:
        await self.respond(event, "<code>Dispatching...</code>")
        now = datetime.datetime.now(datetime.UTC)

        _, raw_name = pattern.match(str(event.content).strip()).groups()
        module_name = (raw_name or "").strip().lower()
        if not module_name:
            await self.respond(
                event,
                "<code>Usage: sendmod|sm {module_name}</code>",
            )
            return

        mod_obj, mod_path = self._resolve_module(module_name)
        if not mod_path:
            await self.respond(
                event,
                f"<code>Module '{html.escape(module_name)}' not found.</code>",
            )
            return

        caption = self._build_caption(mod_obj, mod_path, now)
        await event.reply_document(document=str(mod_path), caption=caption)
        await event.delete()

    def _resolve_module(self, query: str) -> tuple[Module | None, Path | None]:
        modules_dir = Path(__file__).resolve().parent
        file_map = {path.stem.lower(): path for path in modules_dir.glob("*.py")}
        file_map.pop("__init__", None)

        if query in file_map:
            file_path = file_map[query]
            mod_obj = self._find_module_obj(file_path.stem)
            return mod_obj, file_path

        mod_obj = self._find_module_obj(query)
        if mod_obj:
            try:
                file_path = Path(inspect.getfile(mod_obj.__class__)).resolve()
            except Exception:
                file_path = file_map.get(query)
            if file_path and file_path.exists():
                return mod_obj, file_path

        # fallback: prefix match by filename
        for stem, file_path in file_map.items():
            if stem.startswith(query):
                mod_obj = self._find_module_obj(stem)
                return mod_obj, file_path

        return None, None

    def _find_module_obj(self, query: str) -> Module | None:
        query = query.lower()
        for mod in self.client.modules.values():
            class_name = mod.__class__.__name__.lower()
            pretty_name = (mod.name or "").strip().lower()
            file_name = Path(inspect.getfile(mod.__class__)).stem.lower()
            if query in {class_name, pretty_name, file_name}:
                return mod
        return None

    def _build_caption(
        self, mod_obj: Module | None, mod_path: Path, now: datetime.datetime
    ) -> str:
        if mod_obj:
            body = (
                f"<b>{html.escape(mod_obj.name)}</b>\n\n"
                f"  <b>Pattern</b>\n"
                f"    <code>{html.escape(mod_obj.cmds)}</code>\n\n"
                f"{self.fmthelp(mod_obj.desc)}\n\n"
                f"<b><blockquote>{self.fmtsec(now)}</blockquote></b>"
            )
        else:
            body = (
                f"<b>{html.escape(mod_path.stem)}</b>\n\n"
                f"<code>Module file attached.</code>\n\n"
                f"<b><blockquote>{self.fmtsec(now)}</blockquote></b>"
            )

        # Telegram caption limit is 1024 chars.
        if len(body) > 1024:
            body = (
                f"<b>{html.escape(mod_path.stem)}</b>\n\n"
                f"<code>Module file attached.</code>\n\n"
                f"<b><blockquote>{self.fmtsec(now)}</blockquote></b>"
            )
        return body
