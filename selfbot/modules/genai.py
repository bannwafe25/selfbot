import asyncio
import base64
import collections
import datetime
import html
import re

from httpx import AsyncClient, Timeout
from pyrogram import filters
from pyrogram.enums import MessageMediaType, ParseMode
from pyrogram.types import ChosenInlineResult, InlineQuery, Message, Sticker, Update

from selfbot.listener import handler
from selfbot.module import Module

pattern = re.compile(r"^(?:(.+?)\s)?\!\?(?:\s-i)?$", flags=re.DOTALL)


class GenAI(Module):
    name = "Google Gemini"
    cmds = "{query} {infix} {suffix}?"
    desc = {
        "query": "String or <Reply or Quote>",
        "infix": "!?",
        "suffix": "-i (Ignore)",
        "?": "Optional",
        "e.g.": "Hello, World! !?",
    }

    async def on_starting(self) -> None:
        try:
            self.google = AsyncClient(
                headers={
                    "Content-Type": "application/json",
                    "x-goog-api-key": self.client.config["GEMINI_API_KEY"],
                },
                http2=True,
                timeout=Timeout(timeout=None),
                follow_redirects=True,
                base_url="https://generativelanguage.googleapis.com",
            )
        except Exception as e:
            self.logger.error(f"{e.__class__.__name__}: {e}")
            self.client.unload(self)
            return

        self.models = collections.deque(
            [
                "gemini-3-pro-preview",
                "gemini-3-flash-preview",
                "gemini-2.5-pro",
                "gemini-2.5-flash",
                "gemini-2.5-flash-lite",
                "gemini-2.5-flash-preview-09-25",
                "gemini-2.5-flash-lite-preview-09-25",
                "gemini-2.0-flash",
                "gemini-2.0-flash-lite",
                "gemini-2.0-flash-001",
                "gemini-2.0-flash-lite-001",
            ]
        )
        self.data = collections.deque(maxlen=16)
        self.lock = asyncio.Lock()

    async def on_started(self) -> None:
        self.client.config.pop("GEMINI_API_KEY", None)

    async def on_stopping(self) -> None:
        if hasattr(self, "google") and not self.google.is_closed:
            await self.google.aclose()

    @handler(filters.regex(pattern), 1)
    async def on_message_out(self, event: Message) -> None:
        await self.execute(event)

    @handler(filters.command("start"), 2)
    async def on_message_bot(self, event: Message) -> None:
        if (
            len(event.content.split()) == 2
            and event.content.split()[1].strip() == "clear"
        ):
            resp = await event.reply_sticker(
                self.client.config["STICKER_FILE_ID"],
                reply_parameters=ReplyParameters(message_id=event.id),
                reply_markup=self.ikm(("...", "switch_inline_query", "")),
            )
            async with self.lock:
                self.data.clear()
            await asyncio.gather(event.delete(), resp.delete())

    @handler(filters.regex(pattern), 3)
    async def on_inline_query(self, event: InlineQuery) -> None:
        await self.answer(
            event, switch_pm_text="Clear Conversation", switch_pm_parameter="clear"
        )

    @handler(filters.regex(pattern), 4)
    async def on_inline_result(self, event: ChosenInlineResult) -> None:
        await self.execute(event)

    async def gemini(self, attempt: int = 0) -> str:
        if attempt >= len(self.models):
            return "**Error**:\n  `Rate Limited`"

        model = self.models[0]
        try:
            resp = await self.google.post(
                f"/v1beta/models/{model}:generateContent",
                json={"contents": list(self.data), "tools": [{"google_search": {}}]},
            )
            resp.raise_for_status()
        except Exception:
            self.models.rotate(-1)
            return await self.gemini(attempt + 1)

        try:
            res = resp.json()
            if "candidates" not in res or not res["candidates"]:
                self.data.pop()
                return "**Error**:\n  `Empty Response`"

            candidates = res["candidates"][0]
            if "content" not in candidates:
                self.data.pop()
                return "**Error**:\n  `Empty Content`"

            data = candidates["content"]
            if "parts" not in data or not data["parts"]:
                self.data.pop()
                return "**Error**:\n  `Empty Parts`"

            parts = data["parts"][0]
            if "text" not in parts:
                self.data.pop()
                return "**Error**:\n  `Empty Text`"

            text = parts["text"]
        except Exception as e:
            self.data.pop()
            return f"**{e.__class__.__name__}**:\n  `{e}`"

        self.data.append(data)
        return text

    async def execute(self, event: Update) -> None:
        if isinstance(event, ChosenInlineResult):
            text = event.query
        else:
            text = event.content

        (query,) = pattern.match(text).groups()
        if query:
            await self.respond(event, f"`{query}`", parse_mode=ParseMode.MARKDOWN)
        else:
            if isinstance(event, ChosenInlineResult):
                await self.respond(
                    event,
                    "<code>Give a Query with Suffix '!?'</code>",
                    reply_markup=self.ikm(("Close", "data", b"0")),
                    revoke=2.5,
                )
                return

            await self.respond(event, "<code>...</code>")

        parts = []
        if query:
            parts.append({"text": query})

        if isinstance(event, Message):
            if event.quote and event.quote.text:
                parts.append({"text": event.quote.text})
            elif event.reply_to_message and event.reply_to_message.media:
                if event.reply_to_message.media in (
                    MessageMediaType.ANIMATION,
                    MessageMediaType.AUDIO,
                    MessageMediaType.DOCUMENT,
                    MessageMediaType.PHOTO,
                    MessageMediaType.STICKER,
                    MessageMediaType.VIDEO,
                    MessageMediaType.VOICE,
                ):
                    rep = event.reply_to_message
                    obj = getattr(rep, rep.media.value)
                    if obj.file_size > 32 * (1024**2):
                        await self.respond(
                            event,
                            "<code>Exceeded Size (Limit: 32 MB)</code>",
                            revoke=2.5,
                        )
                        return

                    mime = getattr(obj, "mime_type", "image/jpeg").lower().strip()
                    if isinstance(obj, Sticker) and obj.is_animated:
                        rep, mime = obj.thumbs[0].file_id, "image/jpeg"
                    elif mime.startswith("text"):
                        mime = "text/plain"

                    if not (
                        mime.startswith(("audio", "image", "text", "video"))
                        or mime == "application/pdf"
                    ):
                        await self.respond(
                            event,
                            f"<code>Unsupported '{obj.mime_type}' MIME Type</code>",
                            revoke=2.5,
                        )
                        return

                    parts.append(
                        {
                            "inline_data": {
                                "mime_type": mime,
                                "data": base64.b64encode(
                                    (
                                        await event._client.download_media(
                                            rep, in_memory=True
                                        )
                                    ).getvalue()
                                ).decode("ascii"),
                            }
                        }
                    )
                    if not query:
                        parts.append({"text": "Analyze"})
                elif event.reply_to_message.media == MessageMediaType.WEB_PAGE:
                    parts.append({"text": event.reply_to_message.content})
                else:
                    await self.respond(
                        event,
                        f"<code>Unsupported {html.escape(f'<{event.reply_to_message.media}>')}</code>",
                        revoke=2.5,
                    )
                    return
            elif (
                event.reply_to_message
                and event.reply_to_message.content
                and not event.content.endswith("-i")
            ):
                parts.append({"text": event.reply_to_message.content})
            elif not query:
                await self.respond(
                    event,
                    f"<code>Give a Query or {html.escape('<Reply or Quote>')}</code>",
                    revoke=2.5,
                )
                return

        ikb, now = [("Close", "data", b"0")], datetime.datetime.now(datetime.UTC)
        async with self.lock:
            self.data.append({"role": "user", "parts": parts})
            res = await self.gemini()
            rtt = self.fmtsec(now)
            if len(res) > 768:
                url, raw = await asyncio.gather(
                    self.client.http.post("https://paste.rs", data=res.encode()),
                    event._client.parser.parse(res, ParseMode.MARKDOWN),
                )
                url = f"{url.text.strip()}.md"
                if isinstance(event, ChosenInlineResult):
                    ikb.insert(0, ("Full", "url", url))
                else:
                    rtt = f"[{rtt}]({url})"

                res = f"{raw['message'][:512]}..."

            await self.respond(
                event,
                f"**{query if query else ''}**\n\n{res}\n\n> **{rtt}**",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=self.ikm(ikb),
            )
