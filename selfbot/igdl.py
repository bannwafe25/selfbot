"""Instagram downloader via embed page — no login needed."""
import re
import subprocess
import html


def _curl(url: str, extra: list[str] | None = None) -> str:
    cmd = ["curl", "-s", "-m", "30", "-A",
           "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"]
    if extra:
        cmd += extra
    cmd.append(url)
    return subprocess.run(cmd, capture_output=True).stdout.decode("utf-8", "replace")


def _unescape(raw: str) -> str:
    B = chr(92)
    s = raw.rstrip(B)
    for _ in range(6):
        s = s.replace(B + B, B).replace(B + "/", "/")
    s = re.sub("u00([0-9a-fA-F]{2})", lambda m: chr(int(m.group(1), 16)), s)
    return html.unescape(s)


def igdl(url: str, out_file: str) -> tuple[str, int]:
    """Download IG reel/p video. Returns (shortcode, size_bytes). Raises on failure."""
    m = re.search(r"instagram\.com/(?:reel|p|reels)/([A-Za-z0-9_-]+)", url)
    code = m.group(1) if m else url.rstrip("/").split("/")[-1].split("?")[0]

    page = _curl(f"https://www.instagram.com/reel/{code}/embed/captioned/")
    if "video_url" not in page:
        raise RuntimeError(
            "IG embed: no video_url (private, deleted, atau IG rate-limit). Coba lagi / pakai cookies."
        )

    i = page.find("video_url")
    frag = page[i:]
    j = frag.find("https")
    end = j
    while end < len(frag) and frag[end] not in ('"', "'", "}", " ", ">"):
        end += 1
    media = _unescape(frag[j:end])

    r = subprocess.run(
        ["curl", "-sL", "-o", out_file, "-w", "%{http_code} %{size_download}",
         "-A", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
         "-H", "Referer: https://www.instagram.com/", media],
        capture_output=True,
    )
    parts = r.stdout.decode().split()
    http_code, size = int(parts[0]), int(parts[1])
    if http_code != 200 or size == 0:
        raise RuntimeError(f"IG download failed: HTTP {http_code}")
    return code, size
