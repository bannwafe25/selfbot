import base64
import datetime
import html
import io
import json
import re

import qrcode
from pyrogram import filters
from pyrogram.types import Message

from selfbot.listener import handler
from selfbot.module import Module

pattern = re.compile(r"^\.?qris(?:\s+(\d+))?$", re.IGNORECASE)

# Payload QRIS statis "kedai zp" — simpan sekali, generate ulang kapan aja
DEFAULT_PAYLOAD = (
    "00020101021126570011ID.DANA.WWW01189360091530327171690209032717169"
    "0303UMI51440014ID.CO.QRIS.WWW0215ID10265349766120303UMI52045611530"
    "33605802ID5908kedai zp6015Kab. Kepulauan 610592812630454B1"
)

STORAGE_FILE = "storage/qris.json"


def _crc16(data: str) -> str:
    crc = 0xFFFF
    for ch in data.encode():
        crc ^= ch << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return f"{crc:04X}"


def set_amount(payload: str, amount: int) -> str:
    """Sisipkan tag 54 (nominal) ke payload QRIS & hitung ulang CRC (tag 63)."""
    amount_tag = f"54{len(str(amount)):02d}{amount}"
    # Buang nominal lama kalau ada (tag 54)
    p = payload
    i = 0
    out = []
    while i < len(p):
        tag = p[i : i + 2]
        if len(p) < i + 4:
            break
        ln = int(p[i + 2 : i + 4])
        val = p[i + 4 : i + 4 + ln]
        if tag != "54" and tag != "63":
            out.append(p[i : i + 4 + ln])
        i += 4 + ln
    body = "".join(out)
    # Sisipkan tag 54 sebelum tag 58 (country code) kalau ada, else sebelum CRC
    pos = body.find("5802")
    if pos == -1:
        pos = body.find("6304")
        body = body[:pos] + amount_tag + body[pos:]
    else:
        body = body[:pos] + amount_tag + body[pos:]
    return body + "6304" + _crc16(body)


class QRIS(Module):
    name = "QRIS"
    cmds = "qris [nominal]"
    desc = {
        "qris": "Kirim QR kedai zp",
        "qris 25000": "QR dengan nominal Rp25.000",
    }

    def _payload(self) -> str:
        try:
            with open(STORAGE_FILE) as f:
                return json.load(f).get("payload") or DEFAULT_PAYLOAD
        except Exception:
            return DEFAULT_PAYLOAD

    async def _save_payload(self, payload: str) -> None:
        import os
        os.makedirs("storage", exist_ok=True)
        with open(STORAGE_FILE, "w") as f:
            json.dump({"payload": payload}, f)

    def _qr_png(self, payload: str) -> bytes:
        img = qrcode.make(payload, box_size=10, border=2)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    @handler(filters.regex(pattern) & filters.user([8974636194]), 0)
    async def on_message_out(self, event: Message) -> None:
        m = pattern.match(str(event.content).strip())
        amount = int(m.group(1)) if m and m.group(1) else None

        payload = self._payload()
        if amount:
            payload = set_amount(payload, amount)

        png = self._qr_png(payload)
        b64 = base64.b64encode(png).decode()
        label = f"Rp{amount:,}".replace(",", ".") if amount else "Nominal bebas"

        # Coba kartu rich dengan foto QR di dalamnya
        try:
            sent = await self.send_rich(
                event, "💳 QRIS Kedai ZP",
                [("Nominal", label), ("Merchant", "kedai zp"), ("Metode", "Semua app QRIS")],
                note="Scan pakai aplikasi apa pun yang berlogo QRIS.",
                media_file=png, media_type="photo", query_prefix="qris",
            )
            if sent:
                return
        except Exception:
            pass

        # Fallback: kirim foto + caption HTML
        await event._client.send_photo(
            event.chat.id,
            photo=png,
            caption=(
                "<b>💳 QRIS Kedai ZP</b>\n"
                f"<b>Nominal:</b> {html.escape(label)}\n"
                "<i>Scan pakai aplikasi berlogo QRIS.</i>"
            ),
        )
        await event.delete()
