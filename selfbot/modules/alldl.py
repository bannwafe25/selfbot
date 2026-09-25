import asyncio
import contextlib
import datetime
import html
import json
import os
import re
from pathlib import Path

import yt_dlp

from pyrogram import filters
from pyrogram.types import Message, ReplyParameters

from selfbot.listener import handler
from selfbot.module import Module

url_pattern = re.compile(
    r"https?://(?:www\.|vm\.|vt\.|m\.|web\.)?"
    r"(tiktok\.com|instagram\.com|facebook\.com|fb\.watch|instagr\.am)/\S+",
    re.IGNORECASE,
)


class AllDL(Module):
    name = "All Download"
    cmds = "dl {url}"
    desc = {
        "url": "TikTok / Instagram / Facebook link.",
        "note": "Downloads video (no watermark for TikTok).",
        "e.g.": "dl https://vt.tiktok.com/xxxx",
    }

    @handler(filters.regex(url_pattern), 1)
    async def on_message_out(self, event: Message) -> None:
        text = str(event.content or "").strip()
        match = url_pattern.search(text)
        if not match:
            return
        url = match.group(0)
        await self._alldl(event, url)

    def _ytdlp_opts(self, outtmpl: str) -> dict:
        opts = {
            "format": "best/bestvideo+bestaudio/best",
            "outtmpl": outtmpl,
            "merge_output_format": "mp4",
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "js_runtimes": {"node": {"path": "/usr/local/bin/node"}, "deno": {}},
            "remote_components": ["ejs:github"],
        }
        cookie_file = os.environ.get("YTDLP_COOKIES") or "/home/agentuser/cookies.txt"
        if os.path.isfile(cookie_file):
            opts["cookiefile"] = cookie_file
        return opts

    async def _alldl(self, event: Message, url: str) -> None:
        await self.respond(event, "<code>Processing...</code>")
        now = datetime.datetime.now(datetime.UTC)
        media_file = None
        try:
            if "tiktok.com" in url.lower():
                media_file, title, provider = await self._tiktok(url)
            elif "instagram.com" in url.lower() or "instagr.am" in url.lower():
                media_file, title, provider = await self._ytdlp_dl(
                    url, "IG", {"format": "best/bestvideo+bestaudio/best"}
                )
            else:
                cookie_file = os.environ.get("YTDLP_COOKIES") or "/home/agentuser/cookies.txt"
                if not os.path.isfile(cookie_file):
                    raise RuntimeError(
                        "Facebook butuh cookies. Export cookies.txt facebook.com lalu kirim ke server."
                    )
                media_file, title, provider = await self._ytdlp_dl(url, "FB", {})
                provider = "FB"

            if not media_file or not media_file.exists() or media_file.stat().st_size == 0:
                raise RuntimeError("Download failed or is empty.")

            size_mb = media_file.stat().st_size / 1048576
            reply_parameters = ReplyParameters(
                message_id=event.reply_to_message_id or event.id
            )
            await event._client.send_video(
                chat_id=event.chat.id,
                video=str(media_file),
                caption=(
                    f"<b>{provider}</b> — {html.escape(title[:80])}\n"
                    f"<b>Size:</b> {size_mb:.1f} MB\n\n"
                    f"<b><blockquote>{self.fmtsec(now)}</blockquote></b>"
                ),
                supports_streaming=True,
                reply_parameters=reply_parameters,
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

    async def _ytdlp_dl(self, url: str, tag: str, extra: dict):
        loop = asyncio.get_running_loop()
        download_dir = Path("downloads")
        download_dir.mkdir(parents=True, exist_ok=True)
        base = download_dir / f"{tag.lower()}_{int(now_ts())}"
        outtmpl = str(base) + ".%(ext)s"

        def run():
            opts = self._ytdlp_opts(outtmpl)
            opts.update(extra)
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
            for p in base.parent.glob(base.name + ".*"):
                if p.is_file():
                    return p, info.get("title") or tag, tag.upper()
            raise RuntimeError("Download failed or is empty.")

        return await loop.run_in_executor(None, run)

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
