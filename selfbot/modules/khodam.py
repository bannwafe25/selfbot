import hashlib
import html
import random
import re

from pyrogram import filters
from pyrogram.types import Message

from selfbot.listener import handler
from selfbot.module import Module

pattern = re.compile(r"^\.?(khodam|cek-khodam|cekkhodam)(?:\s+([\s\S]+))?$", re.IGNORECASE)

# Daftar khodam — hasil deterministik per nama (hash), jadi konsisten tiap dicek
KHODAM = [
    "Kucing Sunda", "Macan Putih", "Naga Biru", "Harimau Jawa", "Garuda Emas",
    "Ular Naga", "Kera Sakti", "Biawak Hitam", "Buaya Putih", "Rajawali Perak",
    "Kambing Gunung", "Ayam Jago", "Cicak Raksasa", "Kadal Naga", "Lele Raksasa",
    "Ikan Hiu", "Gurita Hitam", "Kalajengking Merah", "Laba-laba Emas", "Kepiting Sakti",
    "Pocong", "Kuntilanak", "Genderuwo", "Wewe Gombel", "Tuyul", "Jenglot", "Suster Ngesot",
    "Kuyang", "Leak Bali", "Sundel Bolong", "Babi Ngepet", "Jin Qorin", "Ratu Pantai Selatan",
    "Banaspati", "Raksasa Gunung", "Orang Bunian", "Siluman Ular", "Siluman Kera",
    "Dewi Sri", "Ki Joko Bodo", "Mbah Dukun", "Eyang Subur", "Raden Kian Santang",
    "Sunan Kalijaga", "Prabu Siliwangi", "Gajah Mada", "Patih Gajah Mada", "Damar Wulan",
    "Robot Gundam", "Transformer", "Ultraman", "Power Ranger", "Ksatria Baja Hitam",
    "Naruto", "Sasuke", "Goku", "Luffy", "Zoro", "Tanjiro", "Gojo Satoru", "Levi Ackerman",
    "Eren Yeager", "Saitama", "Anya Forger", "Doraemon", "Nobita", "Shinchan", "Upin Ipin",
    "Spongebob", "Patrick", "Squidward", "Tom Cat", "Jerry Mouse", "Mickey Mouse",
    "Kopi Susu", "Es Teh Manis", "Indomie Goreng", "Nasi Padang", "Martabak Manis",
    "Bakso Urat", "Sate Ayam", "Rendang", "Kerupuk Seblak", "Cilok", "Cireng",
    "WiFi Tetangga", "Sinyal Hilang", "Kuota Habis", "Baterai 1%", "Alarm Subuh",
    "Deadline", "Skripsi", "Ujian", "Dosen Killer", "Tagihan Listrik", "Cicilan Motor",
]

TINGKAT = [
    ("💀 Lemah Banget", "wkwk khodamnya lebih lemah dari sinyal di kosan"),
    ("😐 Lemah", "lumayan lah, masih bisa ngusir cicak"),
    ("🙂 Rata-rata", "standar, kayak khodam orang kebanyakan"),
    ("😎 Kuat", "siap-siap aja, ini lumayan serem"),
    ("🔥 Sangat Kuat", "gila sih ini mah, jangan macam-macam"),
    ("👑 Legendaris", "KERAMAT! Ini udah level eyang-eeyang semua"),
]


class Khodam(Module):
    name = "Cek Khodam"
    cmds = "khodam {nama}"
    desc = {
        "nama": "Nama yang mau dicek (atau reply pesan orang).",
        "e.g.": ".khodam Budi — atau reply pesan + <code>khodam</code>",
    }

    @handler(filters.regex(pattern) & filters.outgoing, 1)
    async def on_message_out(self, event: Message) -> None:
        m = pattern.match(str(event.content or "").strip())
        if not m:
            return
        nama = (m.group(2) or "").strip()

        # reply pesan → pakai nama pengirim
        target_user = None
        if not nama and event.reply_to_message:
            r = event.reply_to_message
            target_user = r.from_user
            nama = (
                " ".join(filter(None, [r.from_user.first_name, r.from_user.last_name]))
                if r.from_user
                else (r.chat.title if r.chat else "Anonim")
            )

        if not nama:
            await self.respond(
                event,
                "<b>Cara pakai:</b> <code>khodam {nama}</code>\n"
                "<i>atau reply pesan orang lalu ketik</i> <code>khodam</code>",
                revoke=8,
            )
            return

        # deterministik: nama yang sama → khodam yang sama
        seed = int(hashlib.md5(nama.lower().encode()).hexdigest(), 16)
        rng = random.Random(seed)
        khodam = rng.choice(KHODAM)
        idx = rng.randrange(len(TINGKAT))
        tingkat, komentar = TINGKAT[idx]
        kekuatan = 35 + (seed % 64)  # 35-98%

        bar_fill = int(kekuatan / 10)
        bar = "▰" * bar_fill + "▱" * (10 - bar_fill)

        await self.respond(
            event,
            f"<b>🔮 Cek Khodam</b>\n"
            f"<blockquote>"
            f"<b>Nama:</b> {html.escape(nama)}\n"
            f"<b>Khodam:</b> <b>{html.escape(khodam)}</b>\n"
            f"<b>Tingkat:</b> {tingkat}\n"
            f"<b>Kekuatan:</b> {bar} {kekuatan}%\n"
            f"<i>{html.escape(komentar)}</i>"
            f"</blockquote>",
        )

        if target_user:
            try:
                u = await self.client.app.get_users(target_user.id)
                await u.mention(f"☝️ khodam {nama}")
            except Exception:
                pass
