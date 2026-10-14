import asyncio
import contextlib
import html
import os
import re
import tempfile
import urllib.parse

from pyrogram import filters
from pyrogram.types import Message

from selfbot.listener import handler
from selfbot.module import Module

pattern = re.compile(r"^(?:ytmp3|song)(?:\s+([\s\S]+))?$", re.IGNORECASE)


def _yt_id_from_link(text: str) -> str | None:
    """Ambil video ID dari link YouTube (watch/shorts/youtu.be) atau return None."""
    m = re.search(
        r"(?:youtube\.com/(?:watch\?(?:.*&)?v=|shorts/)|youtu\.be/)([\w-]{11})",
        text,
    )
    return m.group(1) if m else None


def _yt_search(query: str) -> tuple[str, str, str] | None:
    """Cari video di YouTube via py-yt, fallback scrape HTML."""
    try:
        from py_yt import VideosSearch

        results = VideosSearch(query, limit=1).result()
        if results and results.get("result"):
            r0 = results["result"][0]
            vid = r0.get("id")
            if vid:
                return (
                    vid,
                    r0.get("title", ""),
                    (r0.get("channel") or {}).get("name", ""),
                )
    except Exception:
        pass

    import urllib.request

    url = "https://www.youtube.com/results?q=" + urllib.parse.quote(query)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        html_text = r.read().decode("utf-8", "ignore")
    m = re.search(r'"videoRenderer":\{"videoId":"(.{11})"', html_text)
    if not m:
        return None
    vid = m.group(1)
    t = re.search(r'"videoId":"%s".*?"title":\{"runs":\[\{"text":"(.*?)"\}\]' % vid, html_text)
    ch = re.search(r'"videoId":"%s".*?"ownerText":\{"runs":\[\{"text":"(.*?)"\}\]' % vid, html_text)

    def _clean(s: str) -> str:
        s = s.encode().decode("unicode_escape", "ignore")
        for junk in ('","navigationEndpoint', '{"', "\\u0026"):
            if junk in s:
                s = s.split(junk)[0]
        return s.strip()

    return vid, (_clean(t.group(1)) if t else ""), (_clean(ch.group(1)) if ch else "")


async def _shruti_download_async(video_id: str, dest: str) -> None:
    """Download audio via ShrutiBots API (async, streaming)."""
    import aiohttp

    api_key = os.getenv("SHRUTI_API_KEY", "")
    if not api_key:
        raise RuntimeError("SHRUTI_API_KEY belum di-set")
    params = {"url": video_id, "type": "audio", "api_key": api_key}
    timeout = aiohttp.ClientTimeout(total=300)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(
            "https://api.shrutibots.site/download", params=params
        ) as resp:
            if resp.status != 200:
                body = (await resp.text())[:200]
                raise RuntimeError(f"shruti HTTP {resp.status}: {body}")
            with open(dest, "wb") as f:
                async for chunk in resp.content.iter_chunked(131072):
                    f.write(chunk)
    if not os.path.exists(dest) or os.path.getsize(dest) < 10000:
        raise RuntimeError("file kecil/kosong")


class YtMp3(Module):
    name = "YT MP3"
    cmds = "ytmp3|song {link|judul}"
    desc = {
        "{link|judul}": "Link YouTube atau judul lagu — kirim audio ke chat.",
        "e.g.": "ytmp3 melukis senja",
    }

    @handler(filters.regex(pattern), 1)
    async def on_message_out(self, event: Message) -> None:
        query = (pattern.match(str(event.content).strip()).group(1) or "").strip()

        # Reply ke pesan berisi link?
        if not query and event.reply_to_message:
            query = (event.reply_to_message.text or event.reply_to_message.caption or "").strip()

        if not query:
            await self.respond(event, "<code>Usage: ytmp3 {link|judul}</code>")
            return

        status = await self.respond(event, "<code>Mencari...</code>")

        vid = _yt_id_from_link(query)
        if vid:
            title = query[:100]
            author = ""
        else:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, _yt_search, query)
            if not result:
                await self._edit(status, "<code>Lagu gak ketemu.</code>")
                return
            vid, title, author = result

        with contextlib.suppress(Exception):
            await status.edit(f"<code>Downloading: {html.escape(title or vid)}</code>")

        tmp_dir = tempfile.mkdtemp(prefix="ytmp3_")
        dest = os.path.join(tmp_dir, f"{vid}.m4a")
        try:
            await _shruti_download_async(vid, dest)
        except Exception as e:
            with contextlib.suppress(Exception):
                await status.edit(f"<code>Download gagal: {e}</code>")
            with contextlib.suppress(Exception):
                import shutil
                shutil.rmtree(tmp_dir, True)
            return

        dur_s = 0
        try:
            proc = await asyncio.create_subprocess_exec(
                "ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "csv=p=0", dest,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
            )
            out, _ = await proc.communicate()
            dur_s = int(float(out.decode().strip() or 0))
        except Exception:
            pass

        t = html.escape((title or vid)[:200])
        cap = f"<b>{t}</b>"
        if author:
            cap += f"\n{html.escape(author[:100])}"
        if dur_s:
            cap += f"\n{dur_s // 60}:{dur_s % 60:02d}"

        with contextlib.suppress(Exception):
            await status.delete()
        try:
            await self.client.app.send_audio(
                event.chat.id, dest, caption=cap,
                duration=dur_s or 0, performer=author or None,
                title=(title or vid)[:64],
            )
        except Exception as e:
            with contextlib.suppress(Exception):
                await self.respond(event, f"<code>Kirim gagal: {e}</code>")
        finally:
            with contextlib.suppress(Exception):
                import shutil
                shutil.rmtree(tmp_dir, True)
            with contextlib.suppress(Exception):
                await event.delete()

    async def _edit(self, msg, text: str) -> None:
        with contextlib.suppress(Exception):
            await msg.edit(text)
