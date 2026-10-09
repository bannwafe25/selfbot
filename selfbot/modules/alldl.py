import asyncio
import contextlib
import datetime
import html
import json
import os
import re
import shutil
from pathlib import Path


from pyrogram import filters
from pyrogram.types import Message, ReplyParameters

from selfbot.listener import handler
from selfbot.module import Module

url_pattern = re.compile(
    r"https?://(?:www\.|vm\.|vt\.|m\.|web\.)?"
    r"(tiktok\.com|instagram\.com|instagr\.am|youtube\.com|youtu\.be)/\S+",
    re.IGNORECASE,
)


class AllDL(Module):
    name = "All Download"
    cmds = "dl {url}"
    desc = {
        "url": "TikTok / Instagram / YouTube link.",
        "note": "Downloads video (no watermark for TikTok).",
        "e.g.": "dl https://youtu.be/xxxx",
    }

    @handler(filters.regex(url_pattern), 1)
    async def on_message_out(self, event: Message) -> None:
        text = str(event.content or "").strip()
        match = url_pattern.search(text)
        if not match:
            return
        url = match.group(0)
        await self._alldl(event, url)

    async def _alldl(self, event: Message, url: str) -> None:
        await self.respond(event, "<code>Processing...</code>")
        now = datetime.datetime.now(datetime.UTC)
        media_file = None
        try:
            if "tiktok.com" in url.lower():
                media_file, title, provider = await self._tiktok(url)
            elif "instagram.com" in url.lower() or "instagr.am" in url.lower():
                media_file, title, provider = await self._ig(url)
            elif "youtube.com" in url.lower() or "youtu.be" in url.lower():
                media_file, title, provider = await self._youtube(url)
            else:
                raise RuntimeError(
                    "URL tidak didukung. Hanya TikTok, Instagram & YouTube."
                )

            if not media_file or not media_file.exists() or media_file.stat().st_size == 0:
                raise RuntimeError("Download failed or is empty.")

            size_mb = media_file.stat().st_size / 1048576
            dur_s = media_file.stat().st_mtime - now.timestamp()
            # Kartu rich: Download Selesai
            rich_rows = [
                ("Sumber", provider),
                ("Judul", title[:60] or "-"),
                ("Ukuran", f"{size_mb:.1f} MB"),
                ("Format", "MP4"),
            ]
            await self.send_rich(
                event,
                "Download Selesai",
                rich_rows,
                query_prefix=f"alldl{now_ts()}",
                media_file=str(media_file),
                media_type="video",
            )
            await event.delete()
        except Exception as e:
            self.logger.error(f"AllDL error: {e}")
            await self.respond(
                event,
                f"<b>AllDL failed</b>\n\n<code>{html.escape(str(e)[:300])}</code>",
            )
        finally:
            if media_file:
                with contextlib.suppress(OSError):
                    if media_file.exists():
                        media_file.unlink()

    async def _tiktok(self, url: str):
        async def fetch(host: str):
            resp = await self.client.http.get(
                f"https://{host}/api/",
                params={"url": url, "hd": "1"},
                timeout=60,
            )
            if resp.status_code != 200:
                raise RuntimeError(f"tikwm HTTP {resp.status_code}")
            return json.loads(resp.text)

        data = await fetch("www.tikwm.com")
        if data.get("code") != 0 or not data.get("data"):
            data = await fetch("tikwm.com")
            if data.get("code") != 0 or not data.get("data"):
                raise RuntimeError(f"tikwm: {data.get('msg')}")

        d = data["data"]
        title = d.get("title") or "TikTok"
        play = d.get("hdplay") or d.get("play") or d.get("wmplay")
        if not play:
            raise RuntimeError("No video URL from tikwm.")

        download_dir = Path("downloads")
        download_dir.mkdir(parents=True, exist_ok=True)
        out = download_dir / f"tiktok_{d.get('id', int(datetime.datetime.now(datetime.UTC).timestamp()))}.mp4"
        await self._download(str(play), out)
        return out, title, "TikTok"

    async def _ig(self, url: str):
        # Highlight/story link → convert ke /p/ shortcode biar API bisa resolve
        m = re.search(r"story_media_id=(\d+)", url)
        if m:
            alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
            n = int(m.group(1).split("_")[0])
            code = ""
            while n:
                code = alphabet[n % 64] + code
                n //= 64
            url = f"https://www.instagram.com/p/{code}/"

        download_dir = Path("downloads")
        download_dir.mkdir(parents=True, exist_ok=True)
        out = download_dir / f"ig_{int(now_ts())}.mp4"

        async def fetch():
            r = await self.client.http.post(
                "https://ig.parth.qzz.io/v1/download",
                json={"url": url},
                timeout=120,
            )
            return json.loads(r.text)

        data = (await fetch()).get("data") or {}
        media = data.get("downloadUrl")
        if not media:
            raise RuntimeError(
                "IG: API gagal (private, deleted, atau post gak tersedia)."
            )

        async def dl():
            async with self.client.http.stream("GET", media, timeout=300) as resp:
                if resp.status_code != 200:
                    raise RuntimeError(f"IG download failed: HTTP {resp.status_code}")
                with out.open("wb") as handle:
                    async for chunk in resp.aiter_bytes(chunk_size=65536):
                        if chunk:
                            handle.write(chunk)

        await dl()
        code = data.get("shortcode") or "instagram"
        title = (data.get("caption") or f"Instagram {code}")[:200]
        return out, title, "Instagram"

    async def _youtube(self, url: str):
        """YouTube via yt-dlp (client android — SABR 403 workaround)."""
        m = re.search(r"(?:v=|youtu\.be/|shorts/|embed/)([\w-]{11})", url)
        if not m:
            raise RuntimeError("YouTube: video ID gak ketemu di URL.")
        vid = m.group(1)

        ytdlp = shutil.which("yt-dlp")
        fallback = os.path.expanduser("~/apps/selfbot/.venv/bin/yt-dlp")
        if (not ytdlp or not Path(ytdlp).exists()) and Path(fallback).exists():
            ytdlp = fallback
        if not ytdlp or not Path(ytdlp).exists():
            raise RuntimeError("yt-dlp gak ada di server.")

        download_dir = Path("downloads")
        download_dir.mkdir(parents=True, exist_ok=True)
        out = download_dir / f"yt_{vid}_%(ext)s"

        fmt = "(bv*[height<=720][ext=mp4]+ba[ext=m4a])/b[height<=720]/b"
        cookie_file = os.path.expanduser("~/apps/selfbot/cookies.txt")
        cookie_args = ["--cookies", cookie_file] if Path(cookie_file).exists() else []
        proc = await asyncio.create_subprocess_exec(
            ytdlp, "--no-warnings", "--no-playlist", "--geo-bypass",
            *cookie_args,
            "--extractor-args", "youtube:player_client=android,web_safari",
            "-f", fmt, "--merge-output-format", "mp4",
            "--print", "after_move:%(title)s",
            "-o", str(out), f"https://www.youtube.com/watch?v={vid}",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=600)
        if proc.returncode != 0:
            err = (stderr or b"").decode("utf-8", "ignore").strip().splitlines()
            raise RuntimeError(f"YouTube: {err[-1][:200] if err else f'exit {proc.returncode}'}")

        files = sorted(download_dir.glob(f"yt_{vid}_*"), key=lambda p: p.stat().st_mtime)
        if not files or files[-1].stat().st_size == 0:
            raise RuntimeError("YouTube: download empty.")
        title = stdout.decode("utf-8", "ignore").strip().splitlines()
        return files[-1], (title[-1] if title else "YouTube"), "YouTube"

    async def _download(self, url: str, out_file: Path) -> None:
        async with self.client.http.stream("GET", url, timeout=300) as resp:
            if resp.status_code != 200:
                raise RuntimeError(f"Download failed: HTTP {resp.status_code}")
            with out_file.open("wb") as handle:
                async for chunk in resp.aiter_bytes(chunk_size=65536):
                    if chunk:
                        handle.write(chunk)


def now_ts() -> int:
    return int(datetime.datetime.now(datetime.UTC).timestamp())
