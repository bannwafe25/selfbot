import datetime
import html
import re
from io import BytesIO
from secrets import token_hex
from urllib.parse import quote

from pyrogram import filters
from pyrogram.types import Message, ReplyParameters

from selfbot.listener import handler
from selfbot.module import Module

pattern = re.compile(r"^risearch(?:\s+([\s\S]+))?$", re.IGNORECASE)

SEARCH_ENGINES = {
    "lens": "https://lens.google.com/uploadbyurl?url={image}",
    "reverse": "https://www.google.com/searchbyimage?sbisrc=4chanx&image_url={image}&safe=off",
    "tineye": "https://www.tineye.com/search?url={image}",
    "bing": "https://www.bing.com/images/search?view=detailv2&iss=sbi&form=SBIVSP&sbisrc=UrlPaste&q=imgurl:{image}",
    "yandex": "https://yandex.com/images/search?source=collections&url={image}&rpt=imageview",
    "saucenao": "https://saucenao.com/search.php?db=999&url={image}",
}


class RISearch(Module):
    name = "Reverse Image Search"
    cmds = "risearch {engine?}"
    desc = {
        "engine": "Optional: lens|reverse|tineye|bing|yandex|saucenao|all|list",
        "Info": "Reply to an image then run command.",
        "e.g.": "risearch lens",
    }

    @handler(filters.regex(pattern), 1)
    async def on_message_out(self, event: Message) -> None:
        await self.respond(event, "<code>Processing image...</code>")
        now = datetime.datetime.now(datetime.UTC)

        args = (pattern.match(str(event.content).strip()).group(1) or "").strip().lower()
        engines = self._parse_engines(args)
        if engines is None:
            await self.respond(
                event,
                "<b>Available engines</b>\n\n"
                + "\n".join(f"• <code>{name}</code>" for name in SEARCH_ENGINES),
            )
            return

        replied = event.reply_to_message
        if not replied:
            await self.respond(
                event,
                "<code>Reply to a photo/image first. Example: risearch lens</code>",
            )
            return

        if not self._has_supported_media(replied):
            await self.respond(
                event,
                "<code>Reply must contain photo/image/gif/sticker.</code>",
            )
            return

        invalid = [e for e in engines if e not in SEARCH_ENGINES]
        if invalid:
            await self.respond(
                event,
                (
                    "<code>Invalid engine(s): "
                    f"{html.escape(', '.join(invalid))}. "
                    f"Available: {', '.join(SEARCH_ENGINES)}</code>"
                ),
            )
            return

        try:
            data = await replied.download(in_memory=True)
            if not data:
                await self.respond(event, "<code>Failed to download replied media.</code>")
                return

            raw = self.to_bytes(data)
            if not raw:
                await self.respond(event, "<code>Downloaded media is empty.</code>")
                return

            mime = self._detect_mime(replied)
            image_url = await self._upload_to_tmpfiles(raw, mime)
            if not image_url:
                await self.respond(event, "<code>Failed to upload image for search.</code>")
                return

            urls = {
                eng: SEARCH_ENGINES[eng].format(image=quote(image_url, safe=""))
                for eng in engines
            }

            try:
                shots = await self._capture_screenshots(urls)
            except ImportError:
                lines = [f"• <b>{k.capitalize()}</b>: <a href=\"{v}\">open</a>" for k, v in urls.items()]
                await self.respond(
                    event,
                    (
                        "<b>Reverse Image Search</b>\n\n"
                        + "\n".join(lines)
                        + "\n\n<code>Install playwright to send screenshots.</code>\n\n"
                        f"<b><blockquote>{self.fmtsec(now)}</blockquote></b>"
                    ),
                )
                return

            if not shots:
                lines = [f"• <b>{k.capitalize()}</b>: <a href=\"{v}\">{html.escape(v)}</a>" for k, v in urls.items()]
                await self.respond(
                    event,
                    (
                        "<b>Reverse Image Search</b>\n\n"
                        + "\n".join(lines)
                        + "\n\n<code>Failed to capture screenshots.</code>\n\n"
                        f"<b><blockquote>{self.fmtsec(now)}</blockquote></b>"
                    ),
                )
                return

            reply_params = ReplyParameters(message_id=event.reply_to_message_id or event.id)
            for engine_name, screen in shots:
                caption = (
                    f"<b>{engine_name.capitalize()} Result</b>\n"
                    f"<a href=\"{html.escape(urls[engine_name])}\">Open Search Result</a>\n\n"
                    f"<b><blockquote>{self.fmtsec(now)}</blockquote></b>"
                )
                await event.reply_photo(
                    photo=screen,
                    caption=caption,
                    reply_parameters=reply_params,
                )

            await event.delete()
        except Exception as e:
            await self.respond(
                event,
                f"<b>RISearch failed</b>\n\n<code>{html.escape(str(e)[:300])}</code>",
            )

    @staticmethod
    def _parse_engines(args: str) -> list[str] | None:
        if not args or args == "all":
            return list(SEARCH_ENGINES.keys())
        if args == "list":
            return None

        tokens = [t for t in re.split(r"[\s,]+", args) if t]
        if not tokens:
            return list(SEARCH_ENGINES.keys())

        # Keep order but remove duplicates.
        return list(dict.fromkeys(tokens))

    @staticmethod
    def _has_supported_media(message: Message) -> bool:
        if message.photo or message.animation or message.sticker:
            return True
        if message.document:
            mime = (message.document.mime_type or "").lower()
            return mime.startswith("image/") or mime in {"image/webp", "image/gif"}
        return False

    @staticmethod
    def _detect_mime(message: Message) -> str:
        if message.photo:
            return "image/jpeg"
        if message.animation:
            return "image/gif"
        if message.sticker:
            return "image/webp"
        if message.document and message.document.mime_type:
            return message.document.mime_type
        return "application/octet-stream"

    async def _upload_to_tmpfiles(self, raw: bytes, mime: str) -> str | None:
        files = {"file": ("image", raw, mime)}
        resp = await self.client.http.post(
            "https://tmpfiles.org/api/v1/upload",
            files=files,
            timeout=60,
        )
        if resp.status_code != 200:
            return None

        data = resp.json()
        url = (((data.get("data") or {}).get("url")) or "").strip()
        if not url:
            return None

        # Convert public page URL to direct download URL.
        if "tmpfiles.org/" in url and "/dl/" not in url:
            return url.replace("tmpfiles.org/", "tmpfiles.org/dl/")
        return url

    async def _capture_screenshots(self, urls: dict[str, str]) -> list[tuple[str, BytesIO]]:
        try:
            from playwright.async_api import async_playwright
        except ImportError as e:
            raise ImportError from e

        out: list[tuple[str, BytesIO]] = []
        async with async_playwright() as play:
            browser = await play.chromium.launch()
            page = await browser.new_page(viewport={"width": 1440, "height": 1024})
            try:
                for name, url in urls.items():
                    try:
                        await page.goto(url, wait_until="domcontentloaded", timeout=45000)
                        await page.wait_for_timeout(1200)
                        shot = await page.screenshot(full_page=True, type="png")
                    except Exception:
                        continue

                    bio = BytesIO(shot)
                    bio.name = f"risearch_{name}_{token_hex(4)}.png"
                    bio.seek(0)
                    out.append((name, bio))
            finally:
                await browser.close()

        return out
