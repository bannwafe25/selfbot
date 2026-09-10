import asyncio
import collections
import datetime
import html
import re

from pyrogram import filters
from pyrogram.enums import ParseMode
from pyrogram.types import Message, Update

from selfbot.listener import handler
from selfbot.module import Module


pattern = re.compile(
    r"^(?:(.+?)\s)?\!\?(?:\s-i)?$",
    flags=re.DOTALL,
)


class GenAI(Module):
    name = "AI Assistant"

    cmds = "{query} !?"
    desc = {
        "query": "String or <Reply>",
        "!?": "Ask AI",
        "e.g.": "Hello, World! !?",
    }

    API_URL = "https://www.zpkece.cloud/v1/chat/completions"
    DEFAULT_MODEL = "zp/deepseek/deepseek-v4-flash"

    MAX_HISTORY = 12
    MAX_PROMPT_LENGTH = 12000

    async def on_starting(self) -> None:
        self.api_key = (
            await self.getvar("AI_API_KEY")
            or await self.getvar("API_SERVER_KEY")
        )

        if not self.api_key:
            self.logger.error(
                "AI_API_KEY / API_SERVER_KEY not configured"
            )
            self.client.unload(self)
            return

        self.model = (
            await self.getvar("AI_MODEL")
            or self.DEFAULT_MODEL
        )

        self.history = collections.defaultdict(
            lambda: collections.deque(
                maxlen=self.MAX_HISTORY
            )
        )

        self.lock = asyncio.Lock()

        self.logger.info(
            "AI Assistant ready | model=%s",
            self.model,
        )

    async def on_started(self) -> None:
        pass

    def _chat_id(self, event: Message) -> str:
        if event.chat and event.chat.id:
            return str(event.chat.id)

        return str(
            getattr(
                event,
                "chat_id",
                "unknown",
            )
        )

    def _reply_text(self, event: Message):
        reply = getattr(
            event,
            "reply_to_message",
            None,
        )

        if not reply:
            return None

        text = getattr(
            reply,
            "text",
            None,
        )

        if not text:
            text = getattr(
                reply,
                "caption",
                None,
            )

        if not text:
            text = getattr(
                reply,
                "content",
                None,
            )

        if not text:
            return None

        return str(text)[
            :self.MAX_PROMPT_LENGTH
        ]

    async def ask(self, messages):
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.7,
            "stream": False,
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        response = await self.client.http.post(
            self.API_URL,
            headers=headers,
            json=payload,
            timeout=120,
        )

        if response.status_code != 200:
            try:
                data = response.json()
                error = data.get(
                    "error",
                    data,
                )
            except Exception:
                error = response.text

            raise RuntimeError(
                f"HTTP {response.status_code}: {error}"
            )

        data = response.json()

        choices = data.get("choices")

        if not choices:
            raise RuntimeError(
                "API tidak mengembalikan choices."
            )

        answer = (
            choices[0]
            .get("message", {})
            .get("content")
        )

        if isinstance(answer, list):
            parts = []

            for item in answer:
                if isinstance(item, dict):
                    text = item.get("text")

                    if text:
                        parts.append(
                            str(text)
                        )

            answer = "\n".join(parts)

        if not answer:
            raise RuntimeError(
                "Jawaban AI kosong."
            )

        return str(answer).strip()

    @handler(
        filters.regex(pattern),
        1,
    )
    async def on_message_out(
        self,
        event: Message,
    ) -> None:
        await self.execute(event)

    async def execute(
        self,
        event: Update,
    ) -> None:
        text = str(
            getattr(
                event,
                "content",
                "",
            )
        )

        match = pattern.match(text)

        if not match:
            return

        query = match.group(1)

        if query:
            query = query.strip()

        reply_text = None

        if isinstance(event, Message):
            reply_text = self._reply_text(event)

        if query:
            if reply_text:
                prompt = (
                    "Pesan yang direply:\n"
                    f"{reply_text}\n\n"
                    "Pertanyaan pengguna:\n"
                    f"{query}"
                )
            else:
                prompt = query

        elif reply_text:
            prompt = (
                "Tolong jawab atau jelaskan "
                "pesan berikut:\n\n"
                f"{reply_text}"
            )

        else:
            await self.respond(
                event,
                "<code>Give a Query or Reply a message with !?</code>",
                revoke=5,
            )
            return

        if len(prompt) > self.MAX_PROMPT_LENGTH:
            prompt = (
                prompt[
                    :self.MAX_PROMPT_LENGTH
                ]
                + "\n...[dipotong]"
            )

        chat_id = self._chat_id(event)

        system_prompt = (
            "Kamu adalah AI Assistant Telegram. "
            "Jawab dengan jelas, membantu, dan langsung. "
            "Gunakan bahasa yang sama dengan pengguna. "
            "Jangan memberikan jawaban yang tidak perlu."
        )

        async with self.lock:
            previous = list(
                self.history[chat_id]
            )

        messages = [
            {
                "role": "system",
                "content": system_prompt,
            }
        ]

        messages.extend(previous)

        messages.append(
            {
                "role": "user",
                "content": prompt,
            }
        )

        now = datetime.datetime.now(
            datetime.UTC
        )

        try:
            await self.respond(
                event,
                "<code>...</code>",
            )

            answer = await self.ask(
                messages
            )

            elapsed = self.fmtsec(now)

            async with self.lock:
                self.history[chat_id].append(
                    {
                        "role": "user",
                        "content": prompt,
                    }
                )

                self.history[chat_id].append(
                    {
                        "role": "assistant",
                        "content": answer,
                    }
                )

            # Telegram message limit.
            if len(answer) > 3500:
                answer = (
                    answer[:3500]
                    + "..."
                )

            await self.respond(
                event,
                (
                    f"{answer}\n\n"
                    f"> **{elapsed}**"
                ),
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=self.ikm(
                    ("Close", "data", b"0")
                ),
            )

        except Exception as e:
            self.logger.exception(
                "AI API error"
            )

            error = html.escape(
                str(e)
            )

            if len(error) > 1500:
                error = (
                    error[:1500]
                    + "..."
                )

            await self.respond(
                event,
                (
                    "❌ <b>AI Error</b>\n\n"
                    f"<code>{error}</code>"
                ),
            )
