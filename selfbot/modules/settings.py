import asyncio
import datetime
import html
import math
import os
import re
import shlex

from pyrogram import filters
from pyrogram.types import CallbackQuery, InlineQuery, Message, ReplyParameters

from selfbot.listener import handler, reply
from selfbot.module import Module

MESSAGE_PATTERN = re.compile(r"^settings(?:\s+([\s\S]+))?$", re.IGNORECASE)
INLINE_PATTERN = re.compile(r"^settings$", re.IGNORECASE)
CALLBACK_PATTERN = re.compile(
    r"^settings/(menu|vars|var|reset)(?:/([a-f0-9]{10}))?(?:/(\d+))?$", re.IGNORECASE
)

KEY_PATTERN = re.compile(r"^[A-Z0-9_]{1,64}$")
PAGE_SIZE = 8


class Settings(Module):
    name = "Settings"
    cmds = "{settings|/settings} [menu|list|get|add|update|set|reset] ..."
    desc = {
        "settings": "Open inline settings panel.",
        "/settings": "Open settings panel from bot chat.",
        "settings list [filter]": "List DB vars.",
        "settings get {key}": "Read var from DB/config/env.",
        "settings add {key} {value}": "Add new DB var (fails if exists).",
        "settings update {key} {value}": "Update existing DB var.",
        "settings set {key} {value}": "Upsert DB var.",
        "settings reset {key}": "Delete DB var.",
        "e.g.": 'settings add GEMINI_API_KEY "your_key"',
    }

    async def on_starting(self) -> None:
        self._token_to_key: dict[str, str] = {}
        self._key_to_token: dict[str, str] = {}

    @handler(filters.regex(MESSAGE_PATTERN) & ~reply, 1)
    async def on_message_out(self, event: Message) -> None:
        text = str(event.content).strip()
        match = MESSAGE_PATTERN.match(text)
        if not match:
            return

        raw_args = (match.group(1) or "").strip()
        if not raw_args or raw_args.lower() in {"menu", "panel", "ui"}:
            await self._open_inline_panel(event)
            return

        await self._run_text_command(event, raw_args)

    @handler(filters.command("settings"), 2)
    async def on_message_bot(self, event: Message) -> None:
        command = getattr(event, "command", None) or []
        raw_args = " ".join(command[1:]).strip()
        if not raw_args or raw_args.lower() in {"menu", "panel", "ui"}:
            await self._send(
                event,
                await self._main_text(),
                reply_markup=self._main_keyboard(),
            )
            return

        await self._run_text_command(event, raw_args)

    @handler(filters.regex(INLINE_PATTERN), 2)
    async def on_inline_query(self, event: InlineQuery) -> None:
        await self.answer(
            event,
            self._main_keyboard(),
            await self._main_text(),
            cache_time=0,
        )

    @handler(filters.regex(CALLBACK_PATTERN), 4)
    async def on_inline_callback(self, event: CallbackQuery) -> None:
        data = event.data.decode() if isinstance(event.data, bytes) else str(event.data)
        match = CALLBACK_PATTERN.match(data)
        if not match:
            return

        action, token, page_raw = match.groups()
        page = int(page_raw or 0)

        if action == "menu":
            await self.respond(
                event,
                await self._main_text(),
                reply_markup=self._main_keyboard(),
            )
            return

        if action == "vars":
            rows = await self.listvars()
            await self.respond(
                event,
                self._vars_text(rows, page),
                reply_markup=self._vars_keyboard(rows, page),
            )
            return

        if action == "var":
            key = self._token_to_key.get(token or "")
            if not key:
                await event.answer("Var tidak ditemukan, refresh list dulu.", show_alert=True)
                rows = await self.listvars()
                await self.respond(
                    event,
                    self._vars_text(rows, page),
                    reply_markup=self._vars_keyboard(rows, page),
                )
                return

            await self.respond(
                event,
                await self._var_text(key),
                reply_markup=self._var_keyboard(key, page),
            )
            return

        if action == "reset":
            key = self._token_to_key.get(token or "")
            if not key:
                await event.answer("Var tidak ditemukan, refresh list dulu.", show_alert=True)
                rows = await self.listvars()
                await self.respond(
                    event,
                    self._vars_text(rows, page),
                    reply_markup=self._vars_keyboard(rows, page),
                )
                return

            deleted = await self.delvar(key)
            await event.answer(
                f"{key} {'direset' if deleted else 'sudah kosong'}",
                show_alert=False,
            )
            rows = await self.listvars()
            await self.respond(
                event,
                self._vars_text(rows, page),
                reply_markup=self._vars_keyboard(rows, page),
            )

    async def _open_inline_panel(self, event: Message) -> None:
        await self.respond(event, "<code>Opening settings...</code>")
        try:
            res = await event._client.get_inline_bot_results(
                self.client.bot.me.id, "settings", chat_id=event.chat.id
            )
            if not res.results:
                raise RuntimeError("Inline result kosong.")

            await asyncio.gather(
                event.reply_inline_bot_result(
                    res.query_id,
                    res.results[0].id,
                    reply_parameters=ReplyParameters(
                        message_id=event.reply_to_message_id or event.id
                    ),
                ),
                event.delete(),
            )
        except Exception as e:
            await self.respond(
                event,
                f"<b>Settings</b>\n\n<code>{html.escape(str(e)[:300])}</code>",
            )

    async def _run_text_command(self, event: Message, raw_args: str) -> None:
        try:
            args = shlex.split(raw_args)
        except ValueError as e:
            await self._send(
                event, f"<code>Invalid arguments: {html.escape(str(e))}</code>"
            )
            return

        if not args:
            await self._send(event, self._usage_text())
            return

        action = args[0].lower()

        if action in {"list", "vars"}:
            key_filter = args[1] if len(args) > 1 else ""
            rows = await self.listvars(key_filter)
            await self._send(event, self._list_text(rows, key_filter))
            return

        if action in {"get", "show"}:
            if len(args) < 2:
                await self._send(event, "<code>Usage: settings get {KEY}</code>")
                return

            key = self._normalize_key(args[1])
            if not key:
                await self._send(event, "<code>Invalid key format.</code>")
                return

            value, source = await self._resolve_value(key)
            if value is None:
                await self._send(event, f"<code>{key} not found.</code>")
                return

            shown = self.mask_value(value) if self.is_secret_key(key) else str(value)
            await self._send(
                event,
                self.fmtmsg(
                    "Settings Get",
                    {"Key": key, "Value": shown, "Source": source},
                    self.fmtsec(datetime.datetime.now(datetime.UTC)),
                ),
            )
            return

        if action in {"add", "update", "set"}:
            if len(args) < 3:
                await self._send(
                    event,
                    f"<code>Usage: settings {action} {{KEY}} {{VALUE}}</code>",
                )
                return

            key = self._normalize_key(args[1])
            if not key:
                await self._send(event, "<code>Invalid key format.</code>")
                return

            value = " ".join(args[2:]).strip()
            if not value:
                await self._send(event, "<code>Value tidak boleh kosong.</code>")
                return

            exists = await self._db_has_key(key)
            if action == "add" and exists:
                await self._send(
                    event,
                    f"<code>{key} already exists. Use: settings update {key} ...</code>",
                )
                return

            if action == "update" and not exists:
                await self._send(
                    event,
                    f"<code>{key} not found. Use: settings add {key} ...</code>",
                )
                return

            await self.setvar(key, value)
            await self._send(
                event,
                self.fmtmsg(
                    "Settings Saved",
                    {
                        "Action": action.upper(),
                        "Key": key,
                        "Value": (
                            self.mask_value(value)
                            if self.is_secret_key(key)
                            else self._short_value(value)
                        ),
                    },
                    self.fmtsec(datetime.datetime.now(datetime.UTC)),
                ),
            )
            return

        if action in {"reset", "del", "delete", "rm"}:
            if len(args) < 2:
                await self._send(event, "<code>Usage: settings reset {KEY}</code>")
                return

            key = self._normalize_key(args[1])
            if not key:
                await self._send(event, "<code>Invalid key format.</code>")
                return

            deleted = await self.delvar(key)
            await self._send(
                event,
                self.fmtmsg(
                    "Settings Reset",
                    {"Key": key, "Status": "Deleted" if deleted else "Not found"},
                    self.fmtsec(datetime.datetime.now(datetime.UTC)),
                ),
            )
            return

        await self._send(event, self._usage_text())

    async def _main_text(self) -> str:
        total = await self.client.db.settings_vars.count_documents({})
        return self.fmtmsg(
            "Settings Manager",
            {
                "Stored Vars": total,
                "Scope": "DB overrides config/env",
                "Command": "settings add KEY VALUE",
            },
            self.fmtsec(datetime.datetime.now(datetime.UTC)),
        )

    def _main_keyboard(self):
        return self.ikm(
            [
                [("Vars", "data", b"settings/vars/0", "B")],
                [
                    ("Add", "copy", "settings add KEY VALUE", "G"),
                    ("Update", "copy", "settings update KEY VALUE", "B"),
                ],
                [("Close", "data", b"0")],
            ]
        )

    def _vars_text(self, rows: list[dict], page: int) -> str:
        if not rows:
            return (
                "<b>Settings Vars</b>\n\n"
                "<code>Belum ada var di DB.</code>\n\n"
                "Gunakan <code>settings add KEY VALUE</code>."
            )

        pages = max(1, math.ceil(len(rows) / PAGE_SIZE))
        idx = max(0, min(page, pages - 1))
        start = idx * PAGE_SIZE
        chunk = rows[start : start + PAGE_SIZE]
        lines = []
        for i, row in enumerate(chunk, start=start + 1):
            key = str(row.get("key", ""))
            value = row.get("value", "")
            shown = self.mask_value(value) if self.is_secret_key(key) else self._short_value(value)
            lines.append(
                f"<code>{i:02d}.</code> <code>{html.escape(key)}</code> = <code>{html.escape(shown)}</code>"
            )

        return (
            "<b>Settings Vars</b>\n\n"
            + "\n".join(lines)
            + f"\n\n<b>Page:</b> <code>{idx + 1}/{pages}</code>"
        )

    def _vars_keyboard(self, rows: list[dict], page: int):
        if not rows:
            return self.ikm(
                [
                    [("Back", "data", b"settings/menu")],
                    [("Close", "data", b"0")],
                ]
            )

        pages = max(1, math.ceil(len(rows) / PAGE_SIZE))
        idx = max(0, min(page, pages - 1))
        start = idx * PAGE_SIZE
        chunk = rows[start : start + PAGE_SIZE]

        button_rows = []
        pair = []
        for row in chunk:
            key = str(row.get("key", ""))
            token = self._tokenize_key(key)
            pair.append((self._short_key(key), "data", f"settings/var/{token}/{idx}".encode()))
            if len(pair) == 2:
                button_rows.append(pair)
                pair = []
        if pair:
            button_rows.append(pair)

        nav = []
        if idx > 0:
            nav.append((f"<< {idx}", "data", f"settings/vars/{idx - 1}".encode()))
        nav.append(("Menu", "data", b"settings/menu"))
        if idx < pages - 1:
            nav.append((f"{idx + 2} >>", "data", f"settings/vars/{idx + 1}".encode()))

        button_rows.append(nav)
        button_rows.append([("Close", "data", b"0")])
        return self.ikm(button_rows)

    async def _var_text(self, key: str) -> str:
        value, source = await self._resolve_value(key)
        if value is None:
            return (
                "<b>Settings Var</b>\n\n"
                f"<code>{html.escape(key)}</code>\n\n"
                "<code>Value: (empty)</code>\n"
                "<code>Source: -</code>"
            )

        shown = self.mask_value(value) if self.is_secret_key(key) else self._short_value(value)
        return (
            "<b>Settings Var</b>\n\n"
            f"<code>Key:</code> <code>{html.escape(key)}</code>\n"
            f"<code>Value:</code> <code>{html.escape(shown)}</code>\n"
            f"<code>Source:</code> <code>{html.escape(source)}</code>\n\n"
            "<i>Pilih aksi di bawah: Add / Update / Reset</i>"
        )

    def _var_keyboard(self, key: str, page: int):
        token = self._tokenize_key(key)
        return self.ikm(
            [
                [
                    ("Add", "copy", f"settings add {key} VALUE", "G"),
                    ("Update", "copy", f"settings update {key} VALUE", "B"),
                    ("Reset", "data", f"settings/reset/{token}/{page}".encode(), "R"),
                ],
                [
                    ("Back", "data", f"settings/vars/{page}".encode()),
                    ("Close", "data", b"0"),
                ],
            ]
        )

    def _list_text(self, rows: list[dict], key_filter: str = "") -> str:
        if not rows:
            suffix = f" untuk filter '{key_filter}'" if key_filter else ""
            return f"<code>Tidak ada var{html.escape(suffix)}.</code>"

        lines = []
        for row in rows[:30]:
            key = str(row.get("key", ""))
            value = row.get("value", "")
            shown = self.mask_value(value) if self.is_secret_key(key) else self._short_value(value)
            lines.append(f"<code>{html.escape(key)}</code> = <code>{html.escape(shown)}</code>")

        extra = ""
        if len(rows) > 30:
            extra = f"\n\n<code>... and {len(rows) - 30} more</code>"

        head = "<b>Settings Vars</b>"
        if key_filter:
            head += f"\n<code>Filter: {html.escape(key_filter)}</code>"

        return f"{head}\n\n" + "\n".join(lines) + extra

    def _usage_text(self) -> str:
        return (
            "<b>Settings Usage</b>\n\n"
            "<code>settings</code>\n"
            "<code>/settings</code>\n"
            "<code>settings list [filter]</code>\n"
            "<code>settings get KEY</code>\n"
            "<code>settings add KEY VALUE</code>\n"
            "<code>settings update KEY VALUE</code>\n"
            "<code>settings set KEY VALUE</code>\n"
            "<code>settings reset KEY</code>"
        )

    async def _send(
        self, event: Message, text: str, reply_markup=None
    ) -> None:
        if getattr(event, "outgoing", False):
            await self.respond(event, text, reply_markup=reply_markup)
            return

        await event.reply_text(
            text,
            reply_parameters=ReplyParameters(message_id=event.id),
            reply_markup=reply_markup,
        )

    def _normalize_key(self, key: str) -> str | None:
        norm = self.normalize_key(key)
        if not KEY_PATTERN.fullmatch(norm):
            return None
        return norm

    def _short_key(self, key: str, limit: int = 18) -> str:
        if len(key) <= limit:
            return key
        return f"{key[:limit - 3]}..."

    def _short_value(self, value: object, limit: int = 96) -> str:
        text = str(value)
        if len(text) <= limit:
            return text
        return f"{text[: limit - 3]}..."

    async def _resolve_value(self, key: str) -> tuple[object | None, str]:
        row = await self.client.db.settings_vars.find_one({"key": key})
        if row and row.get("value") not in (None, ""):
            return row["value"], "db"

        cfg = self.client.config.get(key)
        if cfg not in (None, ""):
            return cfg, "config"

        env = os.environ.get(key)
        if env:
            return env, "env"

        return None, "-"

    async def _db_has_key(self, key: str) -> bool:
        row = await self.client.db.settings_vars.find_one({"key": key})
        return bool(row and row.get("value") not in (None, ""))

    def _tokenize_key(self, key: str) -> str:
        token = self._key_to_token.get(key)
        if token:
            return token

        # 10 hex chars keeps callback_data short and deterministic enough for UI mapping.
        base = format(abs(hash(key)) & 0xFFFFFFFFFF, "010x")
        token = base
        counter = 0
        while token in self._token_to_key and self._token_to_key[token] != key:
            counter += 1
            token = f"{base[:8]}{counter % 100:02d}"

        self._token_to_key[token] = key
        self._key_to_token[key] = token
        return token
