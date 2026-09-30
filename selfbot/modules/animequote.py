import contextlib
import datetime
import html
import random
import re

from pyrogram import filters
from pyrogram.types import Message

from selfbot.listener import handler
from selfbot.module import Module

ANIMECHAN_RANDOM = "https://api.animechan.io/v1/quotes/random"

pattern = re.compile(r"^animequote(?:\s+)?$", re.IGNORECASE)


class AnimeQuote(Module):
    name = "Anime Quote"
    cmds = "animequote"
    desc = {
        "Info": "Get random anime quote.",
        "e.g.": "animequote",
    }

    @handler(filters.regex(pattern), 1)
    async def on_message_out(self, event: Message) -> None:
        await self.respond(event, "<code>Fetching quote...</code>")
        now = datetime.datetime.now(datetime.UTC)
        now_ts = int(now.timestamp())

        try:
            resp = await self.client.http.get(ANIMECHAN_RANDOM, timeout=15)
            if resp.status_code != 200:
                raise RuntimeError(f"API error: HTTP {resp.status_code}")

            data = (resp.json() or {}).get("data") or {}
            quote = html.unescape(data.get("content", ""))
            char = html.unescape((data.get("character") or {}).get("name", "Unknown"))
            anime = html.unescape((data.get("anime") or {}).get("name", "Unknown"))
            episode = ""

            quote_id = await self._translate_id(quote)
            self._en_cache[now_ts] = quote
            if len(self._en_cache) > 50:
                for k in sorted(self._en_cache)[:-25]:
                    self._en_cache.pop(k, None)

            ep_text = f" • {episode}" if episode else ""
            try:
                import richpyro as rp
                from pyrogram.enums import ButtonStyle as _BS

                blocks = [
                    rp.heading(rp.bold("📖 Anime Quote"), size=2),
                    rp.divider(),
                    rp.para(rp.italic(f"“{quote_id}”")),
                    rp.para(rp.bold(f"— {char}")),
                    rp.para(rp.italic(f"{anime}{ep_text}")),
                    rp.buttons(
                        rp.btn(
                            rp.bold("🇬🇧 English"),
                            callback_data=f"animequote:en:{now_ts}".encode(),
                            style=_BS.DEFAULT,
                        ),
                        rp.btn(rp.bold("🗑 Tutup"), callback_data=b"0", style=_BS.DANGER),
                    ),
                ]
                if await self.send_rich_blocks(event, blocks, query_prefix="animequote"):
                    with contextlib.suppress(Exception):
                        await event.delete()
                    return
            except Exception:
                pass

            text = (
                f"<b>Anime Quote</b>\n\n"
                f"<blockquote><i>\"{html.escape(quote_id)}\"</i></blockquote>\n\n"
                f"— <b>{char}</b>\n"
                f"<code>{html.escape(anime)}{html.escape(ep_text)}</code>\n\n"
                f"<b><blockquote>{self.fmtsec(now)}</blockquote></b>"
            )

            await self.respond(event, text)
        except Exception as e:
            await self.respond(
                event,
                f"<b>AnimeQuote failed</b>\n\n<code>{html.escape(str(e)[:300])}</code>",
            )

    async def _translate_id(self, text: str) -> str:
        """EN → ID via Google Translate keyless; fallback ke teks asli."""
        try:
            resp = await self.client.http.get(
                "https://clients5.google.com/translate_a/t",
                params={"client": "dict-chrome-ex", "sl": "en", "tl": "id", "q": text},
                timeout=10,
            )
            data = resp.json()
            if isinstance(data, list) and data and isinstance(data[0], str):
                return data[0]
        except Exception:
            pass
        return text

    @handler(filters.regex(r"^animequote:en:(\d+)$"), 3)
    async def on_cb_english(self, event) -> None:
        from pyrogram.types import CallbackQuery

        if not isinstance(event, CallbackQuery):
            return
        await event.answer()
        # data: animequote:en:<ts> — ambil quote EN dari cache
        raw = self._en_cache.get(int(event.data.decode().rsplit(":", 1)[1]))
        if not raw:
            return
        import contextlib as _cl
        with _cl.suppress(Exception):
            await event.edit_message_text(
                f"<blockquote><i>\"{html.escape(raw)}\"</i></blockquote>"
            )

    # cache kecil: ts -> quote EN (dipakai tombol English)
    _en_cache: dict[int, str] = {}
