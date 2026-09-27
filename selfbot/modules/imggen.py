from __future__ import annotations

import contextlib
import datetime
import html
import io
import re

from pyrogram import filters
from pyrogram.types import Message

from selfbot.listener import handler
from selfbot.module import Module

# Generate gambar gratis dari Pollinations.ai (tanpa API key)
POLLINATIONS_URL = "https://image.pollinations.ai/prompt"


class ImgGen(Module):
    name = "ImgGen"
    cmds = ".img {prompt}"
    desc = {
        "Info": "Generate gambar dari teks pakai AI (Pollinations).",
        "e.g.": ".img seekor kucing lucu | .img anime girl --1024",
    }

    # .img <prompt>  |  opsional: --512 / --768 / --1024 buat ukuran
    pattern = re.compile(r"^\.?img\s+(.+)$", re.IGNORECASE | re.DOTALL)

    @handler(filters.regex(pattern) & filters.outgoing, 1)
    async def on_message_out(self, event: Message) -> None:
        m = self.pattern.match(str(event.text or event.caption or "").strip())
        if not m:
            return

        raw = m.group(1).strip()

        # ── Ambil ukuran dari flag --512 / --768 / --1024 ──────────────────
        size = 768
        size_m = re.search(r"--(512|768|1024)\b", raw)
        if size_m:
            size = int(size_m.group(1))
            raw = re.sub(r"--(?:512|768|1024)\b", "", raw).strip()

        if not raw:
            await self.respond(
                event,
                "<b>Cara pakai:</b> <code>.img {prompt}</code>\n"
                "<b>Contoh:</b> <code>.img seekor kucing lucu</code>\n"
                "<b>Ukuran:</b> tambahin <code>--512</code> / "
                "<code>--768</code> / <code>--1024</code>",
                reply=True,
            )
            return

        status = await self.respond(event, "<code>Lagi ngegambar...</code>", reply=True)

        try:
            data = await self._generate(raw, size)
        except Exception as e:
            await self._edit(
                status,
                f"<b>Gagal generate</b>\n<blockquote>{html.escape(str(e))[:200]}</blockquote>",
            )
            return

        if not data:
            await self._edit(
                status,
                "<b>Gagal generate</b>\n"
                "<blockquote>API lagi sibuk / timeout. Coba ulangi sebentar lagi.</blockquote>",
            )
            return

        # Kirim sebagai rich: foto + blok details (prompt & info) + tombol
        try:
            import richpyro as rp
            from pyrogram.enums import ButtonStyle
            from pyrogram.types import InputMediaPhoto

            buf = io.BytesIO(data)
            buf.name = "imggen.jpg"
            photo = InputMediaPhoto(buf)

            inner = [
                rp.para(f"Ukuran: {size}x{size}"),
                rp.para(f"Ukuran file: {len(data) / 1024:.1f} KB"),
                rp.para(f"Selesai: {datetime.datetime.now(datetime.UTC).strftime('%H:%M:%S')} UTC"),
            ]
            blocks = [
                rp.photo_block(photo),
                rp.details(rp.bold("🎨 Prompt"), rp.para(raw), *inner, is_open=False),
                rp.buttons(
                    rp.btn(rp.bold("🗑 Close"), callback_data=b"0", style=ButtonStyle.DANGER)
                ),
            ]
            if await self.send_rich_blocks(event, blocks, query_prefix="imggen"):
                with contextlib.suppress(Exception):
                    await status.delete()
                return
        except Exception as e:
            self.logger.warning(f"imggen rich failed, fallback: {e!r}")

        caption = (
            f"<b>🎨 Prompt</b>\n<blockquote>{html.escape(raw)}</blockquote>\n"
            f"<b>Ukuran:</b> <code>{size}x{size}</code>"
        )
        try:
            buf = io.BytesIO(data)
            buf.name = "imggen.jpg"
            with contextlib.suppress(Exception):
                await status.delete()
            await event.reply_photo(buf, caption=caption)
        except Exception as e:
            await self._edit(
                status,
                f"<b>Gagal kirim gambar</b>\n"
                f"<blockquote>{html.escape(str(e))[:200]}</blockquote>",
            )

    # ── Fetch ke Pollinations (dengan retry) ─────────────────────────────
    async def _generate(self, prompt: str, size: int, tries: int = 3) -> bytes | None:
        import urllib.parse

        url = (
            f"{POLLINATIONS_URL}/{urllib.parse.quote(prompt)}"
            f"?width={size}&height={size}&nologo=true"
            f"&seed={datetime.datetime.now(datetime.UTC).microsecond}"
        )

        last_err = None
        for attempt in range(tries):
            try:
                resp = await self.client.http.get(url, timeout=60)
                if resp.status_code == 200 and resp.content:
                    # pastiin beneran gambar, bukan JSON error
                    head = resp.content[:12]
                    if head[:3] == b"\xff\xd8\xff" or head[:8] == b"\x89PNG\r\n\x1a\n":
                        return resp.content
                    last_err = "API balikin bukan gambar"
                else:
                    last_err = f"HTTP {resp.status_code}"
            except Exception as e:
                last_err = str(e)
            if attempt < tries - 1:
                import asyncio

                await asyncio.sleep(2)

        raise RuntimeError(str(last_err) if last_err else "gagal")

    async def _edit(self, msg, text: str) -> None:
        with contextlib.suppress(Exception):
            await msg.edit(text)
