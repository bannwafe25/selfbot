import contextlib
import datetime
import io
import os
import re

import segno
from pyrogram import filters
from pyrogram.enums import ChatAction
from pyrogram.types import Message, ReplyParameters

from selfbot.listener import handler
from selfbot.module import Module

# .qris {teks} | .qris -qis {payload QRIS} — payload QRIS: urutan kolom "account" gak dipakai
pattern = re.compile(
    r"^\.?(qris)(?:\s+(?:(-qis)\s+)?([\s\S]+))?$",
    re.IGNORECASE | re.DOTALL,
)

# QRIS statis: ganti nominal & tambah dynamic kalau payload diawali "00020101"
EMV = re.compile(r"^00\d{2}01\d{2}")


def _make_qr(payload: str, box: int = 10) -> bytes | None:
    qr = segno.make(payload, error="m")
    buf = io.BytesIO()
    qr.save(buf, kind="png", scale=box, border=2, dark="#000000", light="#ffffff")
    return buf.getvalue()


class Qris(Module):
    name = "QRIS"
    cmds = ".qris {teks} | .qris -qis {payload} {nominal}?"
    desc = {
        "teks": "Teks/URL biasa → QR code PNG.",
        "-qis": "Payload QRIS (EMVCo string). Nominal opsional di akhir — "
        "payload statis otomatis jadi dinamis dengan nominal itu.",
        "e.g.": ".qris https://example.com · .qris -qis 00020101... 50000",
    }

    @handler(filters.regex(pattern) & filters.outgoing, 1)
    async def on_message_out(self, event: Message) -> None:
        match = pattern.match(event.text or "")
        if not match:
            return
        is_qis = bool(match.group(2))
        rest = (match.group(3) or "").strip()
        if not rest:
            await self.respond(
                event,
                "<b>Cara pakai:</b> <code>.qris {teks}</code> atau "
                "<code>.qris -qis {payload} {nominal}?</code>",
            )
            return

        amount = ""
        if is_qis:
            # nominal terakhir di angka
            m = re.search(r"\s(\d[\d,.]*)\s*$", rest)
            if m:
                amount = m.group(1).replace(".", "").replace(",", "")
                rest = rest[: m.start()].strip()
            payload = rest
            if not EMV.match(payload):
                await self.respond(
                    event,
                    "<b>Payload QRIS gak valid</b>\n<blockquote>Harus diawali EMVCo tag (000201...)</blockquote>",
                )
                return
            if amount:
                payload = self._inject_amount(payload, amount)
        else:
            payload = rest

        with contextlib.suppress(Exception):
            await event.edit("<code>⏳ Membuat QR...</code>")
        now = datetime.datetime.now(datetime.UTC)

        png = await self.client.loop.run_in_executor(
            None, lambda: _make_qr(payload)
        )
        if not png:
            await self.respond(event, "<b>Gagal generate QR.</b>")
            return

        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(png)
            path = f.name

        cap_lines = [f"<b>QR Code</b>"]
        if is_qis:
            cap_lines.append(f"💳 QRIS {'dinamis' if amount else 'statis'}")
            if amount:
                cap_lines.append(f"💰 Nominal: <b>Rp{int(amount):,}</b>".replace(",", "."))
        cap_lines.append(
            f"\n<b><blockquote>{self.fmtsec(now)}</blockquote></b>"
        )

        try:
            await event._client.send_photo(
                chat_id=event.chat.id,
                photo=path,
                caption="\n".join(cap_lines),
                reply_parameters=ReplyParameters(
                    message_id=event.reply_to_message_id or event.id
                ),
            )
            with contextlib.suppress(Exception):
                await event.delete()
        except Exception as e:
            await self.respond(event, f"<b>QRIS gagal:</b> <code>{str(e)[:200]}</code>")
        finally:
            with contextlib.suppress(OSError):
                os.remove(path)

    def _inject_amount(self, payload: str, amount: str) -> str:
        """Ubah QRIS statis → dinamis: set tag 54 (amount) sebelum tag 58/5809."""
        tag54 = f"54{len(amount):02d}{amount}"
        # cari posisi tag 58 atau 5809 (country code)
        m = re.search(r"(58\d{2})", payload)
        if m:
            return payload[: m.start()] + tag54 + payload[m.start() :]
        # fallback: tempel di akhir sebelum CRC (tag 63)
        m2 = re.search(r"(63\d{2})", payload)
        if m2:
            return payload[: m2.start()] + tag54 + payload[m2.start() :]
        return payload + tag54
