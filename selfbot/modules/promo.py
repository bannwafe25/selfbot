import re

from pyrogram import filters
from pyrogram.raw.types import InputRichMessageHTML
from pyrogram.types import Message

from selfbot.listener import handler, reply
from selfbot.module import Module

pattern = re.compile(r"^promo$", re.IGNORECASE)

PROMO_HTML = """<table bordered striped>
  <caption>📢 <b>PROMO PAKET HEMAT (SATUAN)</b></caption>
  <tr align="center">
    <th>📦 Layanan</th>
    <th>💰 Harga</th>
  </tr>
  <tr align="center">
    <td><b>Plan Lite</b></td>
    <td><code>Rp 10.000</code></td>
  </tr>
  <tr align="center">
    <td><b>Plan Basic</b></td>
    <td><code>Rp 20.000</code></td>
  </tr>
  <tr align="center">
    <td><b>Plan Pro</b></td>
    <td><code>Rp 30.000</code></td>
  </tr>
</table>
<blockquote>Masa Aktif: 1 Bulan • Kami menjamin layanan yang stabil dan performa yang tinggi!</blockquote>

<table>
  <tr align="center">
    <td>🎯 <b>Hubungi Saya Contact Di Bawah Ini</b></td>
  </tr>
</table>"""


class Promo(Module):
    name = "Promo"
    cmds = "promo"
    desc = {"e.g.": "promo — kirim tabel promo dengan rich message native"}

    @handler(filters.regex(pattern) & ~reply, 1)
    async def on_message_out(self, event: Message) -> None:
        await event.delete()
        await event._client.send_rich_message(
            event.chat.id,
            InputRichMessageHTML(html=PROMO_HTML),
        )
