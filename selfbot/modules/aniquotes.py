import html
import random
import re

from pyrogram import filters
from pyrogram.types import Message, ReplyParameters

from selfbot.listener import handler
from selfbot.module import Module

pattern = re.compile(r"^(aniq|aq)(?:\s+([\s\S]+))?$", re.IGNORECASE)


class Aniquotes(Module):
    name = "AniQuotes"
    cmds = "aniq|aq {text}?"
    desc = {
        "text": "Optional. Can also be taken from replied text/caption.",
        "?": "Optional",
        "e.g.": "aq never give up",
    }

    @handler(filters.regex(pattern), 1)
    async def on_message_out(self, event: Message) -> None:
        await self.respond(event, "<code>Generating...</code>")
        _, inline_text = pattern.match(str(event.content).strip()).groups()
        query = self._resolve_query(event, inline_text)
        if not query:
            await self.respond(
                event,
                "<code>Please provide text or reply to a text/caption message.</code>",
            )
            return

        query = query[:512]
        try:
            result = await event._client.get_inline_bot_results(
                "@quotafbot", query, chat_id=event.chat.id
            )
            if not result.results:
                await self.respond(event, "<code>No results returned by @quotafbot.</code>")
                return

            selected = self._pick_result(result.results)
            await event.reply_inline_bot_result(
                result.query_id,
                selected.id,
                reply_parameters=ReplyParameters(
                    message_id=event.reply_to_message_id or event.id
                ),
            )
            await event.delete()
        except Exception as e:
            await self.respond(
                event,
                f"<b>AniQuotes failed</b>\n\n<code>{html.escape(str(e)[:300])}</code>",
            )

    @staticmethod
    def _pick_result(results: list) -> object:
        # Skip the first result when possible (matches legacy behavior).
        if len(results) >= 3:
            return random.choice(results[1:3])
        if len(results) >= 2:
            return random.choice(results[1:])
        return results[0]

    def _resolve_query(self, event: Message, inline_text: str | None) -> str:
        if event.reply_to_message:
            text = self._text_from_message(event.reply_to_message)
            if text:
                return text.strip()

        if inline_text:
            return inline_text.strip()
        return ""

    @staticmethod
    def _text_from_message(message: Message) -> str | None:
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
