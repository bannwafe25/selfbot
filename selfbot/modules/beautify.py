import datetime
import html
import os
import random
import re
from io import BytesIO
from pathlib import Path
from secrets import token_hex
from urllib.parse import urlencode

from pyrogram import filters
from pyrogram.types import Message, ReplyParameters, User

from selfbot.listener import handler
from selfbot.module import Module

CARBON_PATTERN = re.compile(r"^(r?carbon)(?:\s+([\s\S]+))?$", re.IGNORECASE)
CCARBON_PATTERN = re.compile(r"^ccarbon(?:\s+([\s\S]+))?$", re.IGNORECASE)
RAYSO_PATTERN = re.compile(r"^rayso(?:\s+([\s\S]+))?$", re.IGNORECASE)

RAYSO_THEMES = [
    "meadow",
    "breeze",
    "raindrop",
    "candy",
    "crimson",
    "falcon",
    "sunset",
    "midnight",
]


class Beautify(Module):
    name = "Beautify"
    cmds = "{carbon|rcarbon|ccarbon|rayso} ..."
    desc = {
        "carbon": "Create carbon image (white background).",
        "rcarbon": "Create carbon image with random background.",
        "ccarbon": "Create carbon image with custom background color.",
        "rayso": "Create ray.so screenshot from code text.",
        "e.g.": "ccarbon #1F1F1F print('hello world')",
    }

    color_list = []

    async def on_starting(self) -> None:
        colors_path = Path(__file__).resolve().parents[2] / "resources" / "colorlist.txt"
        if colors_path.exists():
            with colors_path.open("r", encoding="utf-8", errors="ignore") as file:
                self.color_list = file.read().split()
        else:
            self.color_list = [
                "White",
                "Black",
                "Gray",
                "Blue",
                "Green",
                "Red",
                "#1F1F1F",
                "#2E3440",
                "#0f172a",
            ]

    @handler(filters.regex(CARBON_PATTERN), 1)
    async def on_message_out_carbon(self, event: Message) -> None:
        await self.respond(event, "<code>Processing...</code>")
        command, inline_code = CARBON_PATTERN.match(event.content).groups()

        if command.lower().startswith("r"):
            color = random.choice(self.color_list) if self.color_list else "White"
        else:
            color = "White"

        code = await self._extract_code(event, inline_code)
        if not code:
            await self.respond(
                event,
                "<code>Give code after command or reply to a text/file message.</code>",
            )
            return

        try:
            carbon = await self._build_carbon(code=code, color=color)
        except Exception as e:
            await self.respond(
                event,
                f"<b>Carbon failed</b>\n\n<code>{html.escape(str(e)[:400])}</code>",
            )
            return

        mention = self._mention_html(event.from_user)
        await event.reply_photo(
            carbon,
            caption=f"Carbonised by {mention}",
            reply_parameters=ReplyParameters(message_id=event.reply_to_message_id or event.id),
        )
        await event.delete()

    @handler(filters.regex(CCARBON_PATTERN), 1)
    async def on_message_out_ccarbon(self, event: Message) -> None:
        await self.respond(event, "<code>Processing...</code>")
        args = (CCARBON_PATTERN.match(event.content).group(1) or "").strip()
        if not args:
            await self.respond(
                event,
                "<code>Use: ccarbon {color} {code} or reply with: ccarbon {color}</code>",
            )
            return

        if event.reply_to_message:
            color = args
            code = await self._extract_code(event, None)
        else:
            parts = args.split(maxsplit=1)
            if len(parts) < 2:
                await self.respond(
                    event,
                    "<code>Use: ccarbon {color} {code}</code>",
                )
                return
            color, code = parts[0], parts[1]

        if not code:
            await self.respond(
                event,
                "<code>Reply to a text/file message or include code in command.</code>",
            )
            return

        try:
            carbon = await self._build_carbon(code=code, color=color)
        except Exception as e:
            await self.respond(
                event,
                f"<b>Carbon failed</b>\n\n<code>{html.escape(str(e)[:400])}</code>",
            )
            return

        mention = self._mention_html(event.from_user)
        await event.reply_photo(
            carbon,
            caption=f"Carbonised by {mention}",
            reply_parameters=ReplyParameters(message_id=event.reply_to_message_id or event.id),
        )
        await event.delete()

    @handler(filters.regex(RAYSO_PATTERN), 1)
    async def on_message_out_rayso(self, event: Message) -> None:
        await self.respond(event, "<code>Processing...</code>")
        args = (RAYSO_PATTERN.match(event.content).group(1) or "").strip()

        theme = None
        dark = True
        title = self._chat_title(event)
        code = None

        if args:
            split = args.split()
            if split[0].lower() == "list":
                await self.respond(
                    event,
                    "<b>Rayso Themes</b>\n\n" + "\n".join(f"• <code>{i}</code>" for i in RAYSO_THEMES),
                )
                return

            if split[0] in RAYSO_THEMES:
                theme = split[0]
                if len(split) > 1 and split[1].lower() in {"true", "false", "t", "f"}:
                    dark = split[1].lower() in {"true", "t"}
                if len(split) > 2:
                    code = args.split(maxsplit=2)[2]
            else:
                code = args

        if event.reply_to_message:
            code = self._text_from_message(event.reply_to_message)
            title = self._user_title(event.reply_to_message.from_user)

        if not code:
            await self.respond(
                event,
                "<code>Give code after command or reply to a text message.</code>",
            )
            return

        if not theme:
            theme = random.choice(RAYSO_THEMES)

        try:
            image_path = await self._build_rayso(code=code, title=title, theme=theme, dark=dark)
        except ImportError:
            await self.respond(
                event,
                "<code>playwright is not installed. Install it first to use rayso.</code>",
            )
            return
        except Exception as e:
            await self.respond(
                event,
                f"<b>Rayso failed</b>\n\n<code>{html.escape(str(e)[:400])}</code>",
            )
            return

        try:
            await event.reply_photo(
                image_path,
                reply_parameters=ReplyParameters(message_id=event.reply_to_message_id or event.id),
            )
            await event.delete()
        finally:
            try:
                os.remove(image_path)
            except FileNotFoundError:
                pass

    async def _build_carbon(self, code: str, color: str) -> BytesIO:
        payload = {
            "code": code,
            "backgroundColor": color,
        }
        resp = await self.client.http.post(
            "https://carbonara.solopov.dev/api/cook",
            json=payload,
            timeout=40,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"API error: HTTP {resp.status_code}")

        image = BytesIO(resp.content)
        image.name = f"carbon_{token_hex(6)}.png"
        image.seek(0)
        return image

    async def _build_rayso(self, code: str, title: str, theme: str, dark: bool) -> str:
        try:
            from playwright.async_api import async_playwright
        except ImportError as e:
            raise ImportError from e

        file_name = f"rayso_{token_hex(8)}.png"
        data = {"darkMode": dark, "theme": theme, "title": title}
        url = f"https://ray.so/#{urlencode(data)}"

        async with async_playwright() as play:
            browser = await play.chromium.launch()
            page = await browser.new_page()
            try:
                await page.goto(url, wait_until="domcontentloaded")
                await page.wait_for_timeout(1000)
                textarea = await page.query_selector("textarea")
                if textarea is None:
                    raise RuntimeError("Editor element not found on ray.so")
                await textarea.fill(code)
                button = await page.query_selector("button[class*='ExportButton']")
                if button is None:
                    raise RuntimeError("Export button not found on ray.so")
                async with page.expect_download() as dl:
                    await button.click()
                download = await dl.value
                await download.save_as(file_name)
            finally:
                await browser.close()

        return file_name

    async def _extract_code(self, event: Message, inline_code: str | None) -> str | None:
        if event.reply_to_message:
            msg = event.reply_to_message
            if msg.media:
                data = await msg.download(in_memory=True)
                if hasattr(data, "read"):
                    raw = data.read()
                else:
                    raw = bytes(data)
                if not raw:
                    return None
                try:
                    return raw.decode("utf-8")
                except UnicodeDecodeError:
                    return raw.decode("utf-8", errors="ignore")
            return self._text_from_message(msg)

        if inline_code:
            return inline_code.strip()
        return None

    @staticmethod
    def _text_from_message(message: Message) -> str | None:
        if not message:
            return None

        for attr in ("text", "caption"):
            value = getattr(message, attr, None)
            if value:
                return value

        content = getattr(message, "content", None)
        if not content:
            return None

        if isinstance(content, str):
            return content
        if hasattr(content, "markdown") and content.markdown:
            return content.markdown
        if hasattr(content, "html") and content.html:
            return content.html
        return str(content)

    @staticmethod
    def _mention_html(user: User | None) -> str:
        if not user:
            return "Unknown"
        name = html.escape(user.first_name or "User")
        return f"<a href=\"tg://user?id={user.id}\">{name}</a>"

    @staticmethod
    def _chat_title(event: Message) -> str:
        if event.chat.title:
            return event.chat.title
        if event.chat.first_name:
            return event.chat.first_name
        return "Untitled"

    @staticmethod
    def _user_title(user: User | None) -> str:
        if not user:
            return "Untitled"
        if user.last_name:
            return f"{user.first_name} {user.last_name}"
        return user.first_name or "Untitled"
