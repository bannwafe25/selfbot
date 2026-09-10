import asyncio
import html
import logging
import time
from collections import defaultdict, deque

from pyrogram import filters

from selfbot.listener import handler
from selfbot.module import Module


logger = logging.getLogger(__name__)


class Assistant(Module):
    name = "AI Assistant"

    API_URL = "https://www.zpkece.cloud/v1/chat/completions"
    DEFAULT_MODEL = "zp/deepseek/deepseek-v4-flash"

    MAX_HISTORY = 12
    MAX_PROMPT_LENGTH = 12000

    def __init__(self, client):
        super().__init__(client)

        self.api_key = None
        self.model = self.DEFAULT_MODEL

        self.history = defaultdict(
            lambda: deque(
                maxlen=self.MAX_HISTORY
            )
        )

        self.lock = asyncio.Lock()

    async def on_starting(self):
        self.api_key = (
            await self.getvar("AI_API_KEY")
            or await self.getvar("API_SERVER_KEY")
        )

        self.model = (
            await self.getvar("AI_MODEL")
            or self.DEFAULT_MODEL
        )

        if self.api_key:
            logger.info(
                "AI Assistant ready | model=%s",
                self.model,
            )
        else:
            logger.warning(
                "AI_API_KEY / API_SERVER_KEY belum tersedia."
            )

        if not getattr(
            self.client,
            "assistant",
            None,
        ):
            logger.warning(
                "Telegram Assistant account belum aktif."
            )

    def _chat_id(self, message):
        chat = getattr(
            message,
            "chat",
            None,
        )

        if chat and getattr(
            chat,
            "id",
            None,
        ):
            return str(chat.id)

        return str(
            getattr(
                message,
                "chat_id",
                "unknown",
            )
        )

    async def _reply_text(self, message):
        reply = getattr(
            message,
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
            return None

        return str(text)[
            :self.MAX_PROMPT_LENGTH
        ]

    async def _ask(self, messages):
        if not self.api_key:
            raise RuntimeError(
                "API key AI belum dikonfigurasi."
            )

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.7,
            "stream": False,
        }

        headers = {
            "Authorization": (
                f"Bearer {self.api_key}"
            ),
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
                f"HTTP {response.status_code}: "
                f"{error}"
            )

        data = response.json()

        choices = data.get(
            "choices"
        )

        if not choices:
            raise RuntimeError(
                "API tidak mengembalikan choices."
            )

        answer = (
            choices[0]
            .get("message", {})
            .get("content")
        )

        if isinstance(
            answer,
            list,
        ):
            parts = []

            for item in answer:
                if isinstance(
                    item,
                    dict,
                ):
                    text = item.get(
                        "text"
                    )

                    if text:
                        parts.append(
                            str(text)
                        )

            answer = "\n".join(
                parts
            )

        if not answer:
            raise RuntimeError(
                "Jawaban AI kosong."
            )

        return str(
            answer
        ).strip()

    async def _send_answer(
        self,
        chat_id,
        answer,
        reply_to_message_id=None,
    ):
        assistant = getattr(
            self.client,
            "assistant",
            None,
        )

        if not assistant:
            raise RuntimeError(
                "Telegram Assistant account belum aktif."
            )

        kwargs = {
            "chat_id": int(chat_id),
            "text": answer,
        }

        if reply_to_message_id:
            kwargs[
                "reply_to_message_id"
            ] = reply_to_message_id

        try:
            return await assistant.send_message(
                **kwargs
            )

        except TypeError:
            kwargs.pop(
                "reply_to_message_id",
                None,
            )

            return await assistant.send_message(
                **kwargs
            )

    @handler(
        filters.regex(
            r"^(?:ai|assistant)(?:\s+([\s\S]+))?$"
        ),
        1,
    )
    async def ai(
        self,
        client,
        message,
        match,
    ):
        """
        .ai pertanyaan
        .assistant pertanyaan

        Reply pesan:

        .ai
        .assistant
        """

        if not getattr(
            self.client,
            "assistant",
            None,
        ):
            await message.edit(
                "❌ <b>Assistant account belum aktif.</b>\n\n"
                "Set <code>ASSISTANT_SESSION_STRING</code> "
                "di .env terlebih dahulu."
            )
            return

        prompt = (
            match.group(1)
            if match
            else None
        )

        if prompt:
            prompt = str(
                prompt
            ).strip()

        reply_context = await self._reply_text(
            message
        )

        # .ai pada pesan reply tanpa prompt.
        if not prompt and reply_context:
            prompt = (
                "Tolong jawab atau jelaskan "
                "pesan berikut:\n\n"
                f"{reply_context}"
            )

        if not prompt:
            await message.edit(
                "<b>🤖 AI Assistant</b>\n\n"
                "<code>.ai pertanyaan</code>\n"
                "<code>.assistant pertanyaan</code>\n\n"
                "Atau reply pesan lalu gunakan "
                "<code>.ai</code>."
            )
            return

        if len(prompt) > self.MAX_PROMPT_LENGTH:
            prompt = (
                prompt[
                    :self.MAX_PROMPT_LENGTH
                ]
                + "\n...[dipotong]"
            )

        # Reply + pertanyaan.
        if (
            reply_context
            and not prompt.startswith(
                "Tolong jawab atau jelaskan "
                "pesan berikut:"
            )
        ):
            prompt = (
                "Pesan yang direply:\n"
                f"{reply_context}\n\n"
                "Pertanyaan pengguna:\n"
                f"{prompt}"
            )

        chat_id = self._chat_id(
            message
        )

        system_prompt = (
            "Kamu adalah AI Assistant Telegram. "
            "Jawab dengan jelas, membantu, dan langsung. "
            "Gunakan bahasa yang sama dengan pengguna. "
            "Jangan memberikan jawaban yang tidak perlu. "
            "Jika pengguna menggunakan bahasa Indonesia, "
            "jawab dalam bahasa Indonesia."
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

        messages.extend(
            previous
        )

        messages.append(
            {
                "role": "user",
                "content": prompt,
            }
        )

        started = time.monotonic()

        try:
            await message.edit(
                "🤖 <b>AI sedang berpikir...</b>"
            )

            answer = await self._ask(
                messages
            )

            elapsed = (
                time.monotonic()
                - started
            )

            async with self.lock:
                self.history[
                    chat_id
                ].append(
                    {
                        "role": "user",
                        "content": prompt,
                    }
                )

                self.history[
                    chat_id
                ].append(
                    {
                        "role": "assistant",
                        "content": answer,
                    }
                )

            message_id = getattr(
                message,
                "id",
                None,
            )

            await self._send_answer(
                chat_id=chat_id,
                answer=answer,
                reply_to_message_id=message_id,
            )

            await message.edit(
                "✅ <b>AI Assistant</b>\n\n"
                "Jawaban sudah dikirim oleh "
                "<b>akun Assistant</b>.\n\n"
                f"🤖 <code>{html.escape(self.model)}</code>\n"
                f"⏱ <code>{elapsed:.1f}s</code>"
            )

        except Exception as e:
            logger.exception(
                "AI Assistant error"
            )

            error = html.escape(
                str(e)
            )

            if len(error) > 1500:
                error = (
                    error[:1500]
                    + "..."
                )

            await message.edit(
                "❌ <b>AI Assistant Error</b>\n\n"
                f"<code>{error}</code>"
            )

    @handler(
        filters.regex(
            r"^aiclear$"
        ),
        1,
    )
    async def clear(
        self,
        client,
        message,
        match,
    ):
        chat_id = self._chat_id(
            message
        )

        async with self.lock:
            existed = (
                chat_id
                in self.history
            )

            self.history.pop(
                chat_id,
                None,
            )

        if existed:
            await message.edit(
                "🧹 <b>AI history chat ini "
                "berhasil dibersihkan.</b>"
            )
        else:
            await message.edit(
                "🧹 <b>Tidak ada AI history "
                "di chat ini.</b>"
            )

    @handler(
        filters.regex(
            r"^aiclearall$"
        ),
        1,
    )
    async def clear_all(
        self,
        client,
        message,
        match,
    ):
        async with self.lock:
            count = len(
                self.history
            )

            self.history.clear()

        await message.edit(
            "🧹 <b>Semua AI history "
            "berhasil dibersihkan.</b>\n\n"
            f"Chat dibersihkan: <code>{count}</code>"
        )
