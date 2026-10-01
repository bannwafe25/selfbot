"""Parser markdown ringan → RichText nested untuk richpyro para/heading."""
import re
import richpyro as rp

# token: code(`...`), bold(**...** atau __...__), italic(*...* atau _..._), strike(~~...~~)
TOKEN = re.compile(
    r"(`[^`\n]+`)"                       # inline code
    r"(\*\*[^*\n]+\*\*)"
    r"(__[^_\n]+__)"
    r"(~~[^~\n]+~~)"
    r"(\*[^*\n]+\*)"
    r"(```)"                             # fence marker (ditangani terpisah)
)

def _inline(text):
    """string → list RichText"""
    out, pos = [], 0
    for m in TOKEN.finditer(text):
        if m.start() > pos:
            out.append(text[pos:m.start()])
        tok = m.group(0)
        if tok.startswith("`") and not tok.startswith("```"):
            out.append(rp.code(tok[1:-1]))
        elif tok.startswith("**"):
            out.append(rp.bold(tok[2:-2]))
        elif tok.startswith("__"):
            out.append(rp.underline(tok[2:-2]))
        elif tok.startswith("~~"):
            out.append(rp.strike(tok[2:-2]))
        else:  # *italic*
            out.append(rp.italic(tok[1:-1]))
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
