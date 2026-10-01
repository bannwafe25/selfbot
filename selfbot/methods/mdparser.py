"""Parser markdown ringan → RichText nested untuk richpyro para/heading."""
import re
import richpyro as rp

# ===== monkeypatch bug library =====
# InputRichBlockListItem.write bawaan: (1) nerusin chat_id/photos/documents ke RichText*.write
# yang cuma nerima client → TypeError, (2) str polos di blocks gak dikonversi → AttributeError.
from pyrogram.types import InputRichBlockListItem, RichText  # noqa: E402
import pyrogram.raw as _raw  # noqa: E402


async def _item_write_fixed(self, *, client, chat_id=None, photos=None, documents=None, ordered=False):
    # RichText._write di sini dipanggil per-item — jangan sekali untuk seluruh list,
    # karena hasil list-nya TextConcat (salah tipe untuk field blocks).
    blocks = [await RichText._write(client, b) for b in self.blocks]
    if ordered:
        return _raw.types.PageListOrderedItemBlocks(
            checkbox=self.has_checkbox, checked=self.is_checked, blocks=blocks, value=self.value,
        )
    return _raw.types.PageListItemBlocks(blocks=blocks)


InputRichBlockListItem.write = _item_write_fixed
# ===== end monkeypatch =====

# token pakai alternasi (|) — grup: 1=fence 2=code 3=bold 4=strike 5=underline 6=italic
TOKEN = re.compile(
    r"(```)"                                # fence (ditangani pemanggil, di-skip di inline)
    r"|(`[^`\n]+`)"                          # inline code
    r"|(\*\*[^*\n]+\*\*)"                    # bold
    r"|(~~[^~\n]+~~)"                        # strike
    r"|(__[^_\n]+__)"                        # underline
    r"|(\*[^*\n]+\*)"                        # italic
)

def _inline(text):
    """string → list RichText (teks polos = str, format = RichText object)"""
    out, pos = [], 0
    for m in TOKEN.finditer(text):
        if m.start() > pos:
            out.append(text[pos:m.start()])
        fence, code, bold, strike, under, ital = m.groups()
        if fence:
            continue  # fence ditangani level blok
        if code:
            out.append(rp.code(code[1:-1]))
        elif bold:
            out.append(rp.bold(bold[2:-2]))
        elif strike:
            out.append(rp.strike(strike[2:-2]))
        elif under:
            out.append(rp.underline(under[2:-2]))
        else:
            out.append(rp.italic(ital[1:-1]))
        pos = m.end()
    if pos < len(text):
        out.append(text[pos:])
    return out or [""]

def md_to_blocks(md: str, max_len: int = 8000):
    """markdown jawaban AI → list blok: para / bullet_list / preformatted / heading."""
    blocks, buf = [], []

    def flush():
        if buf:
            blocks.append(rp.para(*_inline("\n".join(buf))))
            buf.clear()

    lines = md.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.strip().startswith("```"):
            flush()
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i]); i += 1
            code = "\n".join(code_lines)[:max_len]
            blocks.append(rp.preformatted(code))
            i += 1
            continue
        m = re.match(r"^(#{1,4})\s+(.*)", line)
        if m:
            flush()
            blocks.append(rp.heading(*_inline(m.group(2)), size=min(len(m.group(1)) + 2, 6)))
            i += 1
            continue
        m = re.match(r"^\s*[-*]\s+(.*)", line)
        if m:
            flush()
            blocks.append(rp.bullet_list(rp.list_item(*_inline(m.group(1)))))
            i += 1
            continue
        buf.append(line)
        i += 1
    flush()
    return blocks
