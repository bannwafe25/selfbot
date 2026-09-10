import asyncio
import html
import time
from collections import defaultdict, deque

from selfbot.listener import handler
from selfbot.module import Module


class Assistant(Module):
    name = "AI Assistant"

    API_URL = "https://www.zpkece.cloud/v1/chat/completions"
    DEFAULT_MODEL = "zp/qwen/qwen3.5-flash:free"

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
            self.log.info(
                "AI Assistant ready | model=%s",
                self.model,
            )
        else:
            self.log.warning(
                "AI_API_KEY / API_SERVER_KEY belum tersedia."
            )

        if not getattr(self.client, "assistant", None):
            self.log.warning(
                "Telegram Assistant account belum aktif."
            )

    def _chat_id(self, message):
        chat = getattr(message, "chat", None)

        if chat and getattr(chat, "id", None):
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

        return str(text)[:self.MAX_PROMPT_LENGTH]

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
        r"^(?:ai|assistant)(?:\s+([\s\S]+))?$",
        outgoing=True,
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

        prompt = match.group(1)

        if not prompt:
            await message.edit(
                "<b>🤖 AI Assistant</b>\n\n"
                "<code>.ai pertanyaan</code>\n"
                "<code>.assistant pertanyaan</code>\n\n"
                "Atau reply pesan lalu gunakan "
                "<code>.ai</code>."
            )
            return

        prompt = str(prompt).strip()

        if len(prompt) > self.MAX_PROMPT_LENGTH:
            prompt = (
                prompt[:self.MAX_PROMPT_LENGTH]
                + "\n...[dipotong]"
            )

        chat_id = self._chat_id(message)

        reply_context = await self._reply_text(
            message
        )

        if reply_context:
            prompt = (
                "Pesan yang direply:\n"
                f"{reply_context}\n\n"
                "Pertanyaan pengguna:\n"
                f"{prompt}"
            )

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

            # Kirim jawaban menggunakan AKUN 2.
            await self.client.assistant.send_message(
                chat_id=int(chat_id),
                text=answer,
            )

            await message.edit(
                "✅ <b>AI Assistant</b>\n\n"
                "Jawaban sudah dikirim oleh "
                "<b>akun Assistant</b>.\n\n"
                f"⏱ {elapsed:.1f}s"
            )

        except Exception as e:
            self.log.exception(
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
        r"^(?:aiclear|aiclearall)$",
        outgoing=True,
    )
    async def clear(
        self,
        client,
        message,
        match,
    ):
        chat_id = self._chat_id(message)

        async with self.lock:
            self.history.pop(
                chat_id,
                None,
            )

        await message.edit(
            "🧹 <b>AI history dibersihkan.</b>"
        )
