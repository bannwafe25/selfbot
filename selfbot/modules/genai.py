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


pattern = re.compile(r"^(?:(.+?)\s)?ai(?:\s-i)?$", flags=re.DOTALL | re.IGNORECASE)


class GenAI(Module):
    name = "AI Assistant"

    cmds = "{query} ai"
    desc = {
        "query": "String or <Reply>",
        "ai": "Ask AI",
        "e.g.": "Hello, World! ai",
    }

    MAX_HISTORY = 12
    MAX_PROMPT_LENGTH = 12000

    async def on_starting(self) -> None:
        # Priority: XKIRO (qwen free, gak ada quota harian ketat) → Gemini
        xk_key = await self.getvar("XKIRO_API_KEY")
        if xk_key:
            self.api_key = xk_key
            self.provider = "xkiro"
        else:
            self.api_key = await self.getvar("GEMINI_API_KEY")
            self.provider = "gemini"

        if not self.api_key:
            self.logger.error("XKIRO_API_KEY / GEMINI_API_KEY not configured")
            self.client.unload(self)
            return

        default_model = (
            "qwen/qwen3.7-max:free"
            if self.provider == "xkiro"
            else "gemini-3.5-flash"
        )
        self.model = (
            await self.getvar("AI_MODEL")
            or default_model
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

    async def send_rich_ai(
        self,
        event,
        title: str,
        rows: list,
        answer: str,
        query_prefix: str = "genai",
    ) -> bool:
        """Kartu jawaban AI gaya ChatGPT: judul + tabel meta + isi jawaban."""
        try:
            bot = self.client.bot
            import richpyro as rp
            from pyrogram.raw import functions as rawfn
            from pyrogram.raw.types import (
                InputBotInlineMessageRichMessage,
                InputBotInlineResult,
            )
            from selfbot.methods.format import Format
            from selfbot.methods.mdparser import md_to_blocks
            from pyrogram.enums import ButtonStyle

            blocks = [
                rp.heading(title, size=3),
                rp.divider(),
                # jawaban AI berformat markdown → render jadi blok rich asli
                *md_to_blocks(answer),
                rp.buttons(
                    rp.btn("Tutup", callback_data=b"0", style=ButtonStyle.DANGER)
                ),
            ]

            rich_raw = await rp.blocks_message(*blocks).write(client=bot)

            ping_mod = self.client.modules.get("Ping")
            if ping_mod is None:
                return False
            fmt = Format.__new__(Format)
            fmt.client = self.client
            fmt.logger = self.client.logger
            fmt._ensure_rich_handler(
                ping_mod, rawfn, InputBotInlineMessageRichMessage, InputBotInlineResult
            )
            if getattr(ping_mod, "_rich_route", None) is None:
                ping_mod._rich_route = {}
            ping_mod._rich_route[query_prefix] = (rich_raw, None)

            import datetime as _dt

            now = _dt.datetime.now(_dt.UTC)
            res = await event._client.get_inline_bot_results(
                bot.me.id, f"{query_prefix}{now.timestamp()}"
            )
            if not res or not res.results:
                return False

            await asyncio.gather(
                event.reply_inline_bot_result(res.query_id, res.results[0].id),
                event.delete(),
            )
            return True
        except Exception as e:
            self.logger.warning("shared rich genai failed: %r", e)
            return False

    async def ask(self, messages):
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.7,
            "stream": False,
        }

        if self.provider == "xkiro":
            # OpenAI-compatible endpoint di xkiro.com
            response = await self.client.http.post(
                "https://api.xkiro.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": messages,
                    "temperature": 0.7,
                    "stream": False,
                },
                timeout=120,
            )
            if response.status_code != 200:
                try:
                    error = response.json().get("error", response.text)
                except Exception:
                    error = response.text
                raise RuntimeError(
                    f"HTTP {response.status_code}: {error}"
                )
            data = response.json()
            try:
                return data["choices"][0]["message"]["content"]
            except (KeyError, IndexError):
                raise RuntimeError(
                    f"Format respons xKiro tidak dikenal: {data}"
                )

        if self.provider == "gemini":
            # Gemini native API: model di URL, key di header khusus,
            # body pakai contents bukan messages.
            gemini_url = (
                "https://generativelanguage.googleapis.com/v1beta/models/"
                f"{self.model}:generateContent"
            )
            contents = []
            for m in messages:
                role = "model" if m["role"] == "assistant" else "user"
                contents.append(
                    {"role": role, "parts": [{"text": m["content"]}]}
                )
            payload = {
                "contents": contents,
                "generationConfig": {"temperature": 0.7},
            }
            # flash-lite gak support thinkingBudget — hanya model pro/flash biasa
            headers = {"x-goog-api-key": self.api_key}

            # Retry utk error sementara (429 rate-limit / 503 high demand /
            # 400 lokasi yang kadang muncul acak) — coba 4x dengan jeda.
            import asyncio as _aio
            last_err = None
            for attempt in range(4):
                response = await self.client.http.post(
                    gemini_url,
                    headers=headers,
                    json=payload,
                    timeout=120,
                )
                if response.status_code == 429:
                    # Quota habis — jangan retry, langsung gagal
                    break
                if response.status_code in (503, 400) and attempt < 3:
                    self.logger.warning(
                        "gemini %d (attempt %d), retry ntar %ds",
                        response.status_code, attempt + 1, 2 * (attempt + 1),
                    )
                    await _aio.sleep(2 * (attempt + 1))
                    last_err = response
                    continue
                break
            else:
                response = last_err

            if response.status_code != 200:
                try:
                    error = response.json().get("error", response.text)
                except Exception:
                    error = response.text
                raise RuntimeError(
                    f"HTTP {response.status_code}: {error}"
                )
            data = response.json()
            try:
                return data["candidates"][0]["content"]["parts"][0]["text"]
            except (KeyError, IndexError):
                raise RuntimeError(
                    f"Format respons Gemini tidak dikenal: {data}"
                )

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

            rich_rows = [
                ("Model", self.model.split("/")[-1]),
                ("Panjang Jawaban", f"{len(answer)} karakter"),
            ]
            await self.send_rich_ai(
                event,
                "Jawaban AI",
                rich_rows,
                answer,
                query_prefix="genai",
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
                    "<b>AI Error</b>\n\n"
                    f"<code>{error}</code>"
                ),
            )
