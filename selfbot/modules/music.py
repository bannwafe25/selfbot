import asyncio
import contextlib
import os
import re
import tempfile

from pyrogram import filters
from pyrogram.types import Message

from selfbot.listener import handler
from selfbot.module import Module

MUSIC_PATTERN = re.compile(
    r"^(?:play|vplay|skip|stop)(?:\s+([\s\S]+))?$", re.IGNORECASE
)

YT_SEARCH_URL = "https://www.youtube.com/results"


def _clean(s: str) -> str:
    """Bersihkan sisa JSON escape dari hasil scraping YouTube."""
    s = s.encode().decode("unicode_escape", "ignore")
    for junk in ('","navigationEndpoint', '{"', '\\u0026'):
        if junk in s:
            s = s.split(junk)[0]
    return s.strip()


def _yt_search(query: str) -> tuple[str, str, str] | None:
    """Cari video di YouTube: return (video_id, title, author) atau None."""
    import urllib.parse
    import urllib.request

    url = f"{YT_SEARCH_URL}?q={urllib.parse.quote(query)}"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        html_text = r.read().decode("utf-8", "ignore")

    m = re.search(
        r'"videoRenderer":\{"videoId":"(.{11})".*?"title":\{"runs":\[\{"text":"(.*?)"\}\].*?"ownerText":\{"runs":\[\{"text":"(.*?)"\}\]',
        html_text,
    )
    if not m:
        return None
    return m.group(1), _clean(m.group(2)), _clean(m.group(3))


def _onegrab_url(video_id: str, video: bool) -> str | None:
    """Ambil URL media langsung via OneGrab API (bypass bot-check YouTube)."""
    import json
    import urllib.parse
    import urllib.request

    api_key = os.getenv("ONEGRAB_API_KEY", "")
    if not api_key:
        return None
    url = (
        "https://api.onegrab.fun/api/track?url="
        + urllib.parse.quote(f"https://www.youtube.com/watch?v={video_id}")
        + f"&video={'true' if video else 'false'}"
    )
    req = urllib.request.Request(
        url,
        headers={"X-API-Key": api_key, "User-Agent": "Mozilla/5.0"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read().decode("utf-8", "ignore"))
    return data.get("cdnurl")


def _download_media(video_id: str, dest: str, video: bool) -> None:
    """Download media: OneGrab dulu, fallback yt-dlp."""
    import urllib.request

    cdn = _onegrab_url(video_id, True)  # selalu minta versi video (audio-only = t.me link, gak berguna)
    if not cdn:
        cdn = _onegrab_url(video_id, False)
    if cdn:
        last_err = None
        for attempt in range(3):
            try:
                req = urllib.request.Request(cdn, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=60) as r, open(dest, "wb") as f:
                    while True:
                        chunk = r.read(262144)
                        if not chunk:
                            break
                        f.write(chunk)
                if os.path.exists(dest) and os.path.getsize(dest) > 10000:
                    return
            except Exception as e:
                last_err = e
                with contextlib.suppress(Exception):
                    os.remove(dest)
                # CDN link kadang sekali pakai — minta URL baru
                cdn = _onegrab_url(video_id, True) or cdn
        raise last_err or RuntimeError("download gagal")

    import yt_dlp

    cookies = os.getenv("YTDLP_COOKIES", "")
    opts = {
        "format": "bestvideo+bestaudio/best" if video else "bestaudio[ext=m4a]/bestaudio",
        "outtmpl": dest,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
    }
    if cookies and os.path.exists(cookies):
        opts["cookiefile"] = cookies

    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([f"https://www.youtube.com/watch?v={video_id}"])


class Music(Module):
    name = "Music Assistant"
    cmds = "play|vplay <judul> | skip | stop"
    desc = {
        "play <judul>": "Assistant join VC & putar AUDIO dari YouTube.",
        "vplay <judul>": "Assistant join VC & putar VIDEO dari YouTube.",
        "skip": "Stop lagu sekarang (tetap di VC).",
        "stop": "Stop lagu & assistant keluar VC.",
        "e.g.": "play melukis senja | vplay melukis senja",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.call = None          # PyTgCalls instance (milik assistant)
        self.current_chat = None  # chat_id VC aktif
        self.play_token = 0       # naik setiap play baru (batal watcher lama)

    async def _wait_finish(self, chat_id: int, dest: str, token: int) -> None:
        """Tunggu durasi media habis (ffprobe) lalu assistant keluar VC."""
        dur = None
        with contextlib.suppress(Exception):
            proc = await asyncio.create_subprocess_exec(
                "ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "csv=p=0", dest,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
            )
            out, _ = await proc.communicate()
            dur = float(out.decode().strip())
        if dur and dur > 0:
            await asyncio.sleep(dur + 5)
        else:
            await asyncio.sleep(240)  # fallback
        # Kalau sudah ada play baru (token beda), jangan keluar
        if self.current_chat == chat_id and self.play_token == token:
            call = self.call
            with contextlib.suppress(Exception):
                await call.leave_call(chat_id)
            self.current_chat = None
        with contextlib.suppress(Exception):
            import shutil
            shutil.rmtree(os.path.dirname(dest), ignore_errors=True)

    # ------------------------------------------------------
    # PyTgCalls milik ASSISTANT
    # ------------------------------------------------------

    async def _get_call(self):
        if getattr(self.client, "assistant", None) is None:
            raise RuntimeError("Session assistant belum tersedia.")
        if self.call is None:
            from pytgcalls import PyTgCalls

            self.call = PyTgCalls(self.client.assistant)
            await self.call.start()
        return self.call

    # ------------------------------------------------------
    # Helpers
    # ------------------------------------------------------

    async def _status(self, event: Message, text: str):
        with contextlib.suppress(Exception):
            return await event.edit_text(text)

    def _is_group(self, chat) -> bool:
        t = str(getattr(chat, "type", "")).lower()
        return ("group" in t) or ("channel" in t) or ("supergroup" in t)

    def _resolve_chat(self, event: Message) -> int:
        if self._is_group(event.chat):
            return event.chat.id
        raise RuntimeError(
            "Command harus dari dalam grup, atau pakai: play @grup <judul>"
        )

    # ------------------------------------------------------
    # Handler
    # ------------------------------------------------------

    @handler(filters.regex(MUSIC_PATTERN), 1)
    async def on_message_out(self, event: Message) -> None:
        m = MUSIC_PATTERN.match(str(event.content).strip())
        if not m:
            return

        action = str(event.content).strip().split()[0].lower()
        query = (m.group(1) or "").strip()

        if action == "stop":
            await self._do_stop(event)
            return

        if action == "skip":
            await self._do_skip(event)
            return

        # play / vplay
        is_video = action == "vplay"
        if not query:
            await self._status(
                event, f"<b>Usage:</b> <code>{action} &lt;judul lagu&gt;</code>"
            )
            return

        # DM: first token bisa @grup
        chat_override = None
        if not self._is_group(event.chat):
            if query.startswith("@"):
                parts = query.split(None, 1)
                chat_override = parts[0]
                query = parts[1] if len(parts) > 1 else ""
            if not query:
                await self._status(event, f"<code>{action} @grup &lt;judul&gt;</code>")
                return

        status = await self._status(event, "<code>🔎 Mencari lagu...</code>")

        # 1. Search
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, _yt_search, query)
        except Exception as e:
            await self._status(event, f"❌ Search gagal: <code>{e}</code>")
            return
        if not result:
            await self._status(event, "<code>Lagu tidak ditemukan.</code>")
            return
        vid, title, author = result

        # 2. Resolve chat
        try:
            if chat_override:
                c = await self.client.app.get_chat(chat_override)
                chat_id = c.id
            else:
                chat_id = self._resolve_chat(event)
        except RuntimeError as e:
            await self._status(event, f"<code>{e}</code>")
            return
        except Exception as e:
            await self._status(event, f"❌ {e.__class__.__name__}: <code>{e}</code>")
            return

        # 3. Download
        kind = "video" if is_video else "audio"
        await self._status(event, f"<code>⬇️ Downloading {kind}:</code> {title}")
        tmp_dir = tempfile.mkdtemp(prefix="music_")
        ext = "mp4" if is_video else "m4a"
        dest = os.path.join(tmp_dir, f"{vid}.{ext}")
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, _download_media, vid, dest, is_video)
        except Exception as e:
            await self._status(event, f"❌ Download gagal: <code>{e}</code>")
            return

        if not os.path.exists(dest) or os.path.getsize(dest) < 10000:
            await self._status(event, "<code>❌ Media kosong / terlalu kecil.</code>")
            return

        # 3b. Mode audio: extract track audio dari MP4 → file murni audio
        if not is_video:
            audio_dest = os.path.join(tmp_dir, f"{vid}.m4a")
            try:
                proc = await asyncio.create_subprocess_exec(
                    "ffmpeg", "-y", "-i", dest, "-vn", "-acodec", "copy", audio_dest,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                await proc.wait()
                if os.path.exists(audio_dest) and os.path.getsize(audio_dest) > 10000:
                    dest = audio_dest
            except Exception:
                pass  # pakai MP4 saja kalau ffmpeg gagal

        # 4. Assistant join & play
        emoji = "🎬" if is_video else "🎵"
        await self._status(event, f"<code>{emoji} Joining VC & playing...</code>")
        try:
            call = await self._get_call()
            from pytgcalls.types import MediaStream

            if is_video:
                # Video + audio REQUIRED (jangan sampai video-only)
                stream = MediaStream(
                    dest,
                    audio_flags=MediaStream.Flags.REQUIRED,
                    video_flags=MediaStream.Flags.REQUIRED,
                )
            else:
                # Audio mode: file m4a murni audio → IGNORE video (kalau tidak, VC menampilkan video)
                stream = MediaStream(
                    dest,
                    audio_flags=MediaStream.Flags.REQUIRED,
                    video_flags=MediaStream.Flags.IGNORE,
                )
            await call.play(chat_id, stream)
            self.current_chat = chat_id
            self.current_file = dest
            self.play_token += 1
            asyncio.ensure_future(self._wait_finish(chat_id, dest, self.play_token))
        except Exception as e:
            await self._status(
                event, f"❌ PyTgCalls: <code>{e.__class__.__name__}: {e}</code>"
            )
            return

        yt_link = f"https://www.youtube.com/watch?v={vid}"

        # Durasi via ffprobe
        proc = await asyncio.create_subprocess_exec(
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "csv=p=0", dest,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
        )
        out, _ = await proc.communicate()
        dur_s = int(float(out.decode().strip() or 0))
        dur_txt = f"{dur_s // 60}:{dur_s % 60:02d}" if dur_s else "-"

        # Rich card ala TgMusic via send_rich_blocks; kalau gagal → HTML di bawah
        rich_done = False
        if isinstance(event, Message):
            try:
                import richpyro as rp

                trows = [
                    [rp.table_cell(rp.bold(f"{emoji} Now Playing"), is_header=True, colspan=2, align="center")],
                    [rp.table_cell(rp.bold("🎵 Title"), align="left"),
                     rp.table_cell(rp.link(title, yt_link), align="left")],
                    [rp.table_cell(rp.bold("⏱ Duration"), align="left"),
                     rp.table_cell(dur_txt, align="left")],
                    [rp.table_cell(rp.bold("📺 Channel"), align="left"),
                     rp.table_cell(author, align="left")],
                    [rp.table_cell(rp.bold("🎚 Mode"), align="left"),
                     rp.table_cell("Video" if is_video else "Audio", align="left")],
                    [rp.table_cell(rp.bold("🙋 Requested"), align="left"),
                     rp.table_cell("Assistant", align="left")],
                ]
                blocks = [rp.table(trows, bordered=True, striped=True, compact=False)]
                from pyrogram.enums import ButtonStyle as _BS
                blocks.append(rp.buttons(
                    rp.btn(rp.bold("⏭ Skip"), callback_data=b"music:skip", style=_BS.PRIMARY),
                    rp.btn(rp.bold("⏹ Stop"), callback_data=b"music:stop", style=_BS.DANGER),
                    rp.btn(rp.bold("🗑 Tutup"), callback_data=b"0", style=_BS.DANGER),
                ))
                rich_done = await self.send_rich_blocks(event, blocks, query_prefix="music")
            except Exception as e:
                with contextlib.suppress(Exception):
                    self.logger.warning(f"music rich failed: {e!r}")

        if rich_done:
            with contextlib.suppress(Exception):
                await event.delete()
            return

        await self._status(
            event,
            f"<b>{emoji} Now Playing</b>\n"
            f"<b>Title:</b> <a href=\"{yt_link}\">{title}</a>\n"
            f"<b>Duration:</b> {dur_txt}\n"
            f"<b>Channel:</b> {author}\n"
            f"<b>Mode:</b> {'Video' if is_video else 'Audio'}\n"
            f"<b>By:</b> Assistant",
        )

    @handler(filters.regex(r"^music:(skip|stop)$"), 1)
    async def on_inline_callback(self, event) -> None:
        """Callback tombol rich Skip/Stop dari kartu Now Playing."""
        from pyrogram.types import CallbackQuery

        if not isinstance(event, CallbackQuery):
            return
        action = (event.data if isinstance(event.data, str) else event.data.decode()).split(":", 1)[1]
        if action == "skip":
            await self._do_skip(event)
        elif action == "stop":
            await self._do_stop(event)

    async def _do_skip(self, event) -> None:
        try:
            call = await self._get_call()
            if self.current_chat:
                await call.leave_call(self.current_chat)
                self.current_chat = None
            await self._status(
                event, "<code>⏭ Skipped (kirim play lagi untuk masuk).</code>"
            )
        except Exception as e:
            await self._status(event, f"❌ <code>{e}</code>")

    async def _do_stop(self, event: Message) -> None:
        try:
            call = await self._get_call()
            if self.current_chat:
                await call.leave_call(self.current_chat)
                self.current_chat = None
            await self._status(event, "<code>⏹ Stopped. Assistant keluar VC.</code>")
        except Exception as e:
            await self._status(event, f"❌ <code>{e}</code>")
