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
    r"^(?:play|vplay|stop|pause|resume|skip|playlist|volume)(?:\s+([\s\S]+))?$",
    re.IGNORECASE,
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
    """Cari video di YouTube via py-yt (library), fallback scrape HTML."""
    try:
        from py_yt import VideosSearch

        results = VideosSearch(query, limit=1).result()
        if results and results.get("result"):
            r0 = results["result"][0]
            vid = r0.get("id")
            if vid:
                return vid, r0.get("title", ""), (r0.get("channel") or {}).get("name", "")
    except Exception:
        pass

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


def _arc_request(path: str, params: dict) -> dict:
    """Request ke Arc API (api.arcmusic.fun) dengan api_key."""
    import json
    import urllib.parse
    import urllib.request

    api_key = os.getenv("ARC_API_KEY", "")
    if not api_key:
        raise RuntimeError("ARC_API_KEY belum di-set di .env")
    params = {**params, "api_key": api_key}
    url = "https://api.arcmusic.fun" + path + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8", "ignore"))


def _ytdlp_download(video_id: str, dest: str, video: bool) -> None:
    """Download via yt-dlp (butuh deno runtime buat challenge solver YouTube)."""
    import shutil
    import subprocess

    ytdlp = os.path.expanduser("~/apps/selfbot/.venv/bin/yt-dlp")
    if not os.path.exists(ytdlp):
        ytdlp = shutil.which("yt-dlp")
    if not ytdlp:
        raise RuntimeError("yt-dlp gak ada")

    deno = os.path.expanduser("~/.deno/bin")
    env = dict(os.environ)
    if os.path.isdir(deno):
        env["PATH"] = deno + os.pathsep + env.get("PATH", "")

    fmt = (
        "(bestvideo[height<=?720][ext=mp4]+bestaudio/best[height<=?720])/best"
        if video
        else "bestaudio/best"
    )
    cookie_file = os.path.expanduser("~/apps/selfbot/cookies.txt")
    cookie_args = ["--cookies", cookie_file] if os.path.exists(cookie_file) else ["--no-cookies"]
    cmd = [
        ytdlp, *cookie_args, "-f", fmt, "--no-playlist", "--geo-bypass",
        "--extractor-args", "youtube:player_client=android,web_safari",
        "--no-warnings", "--quiet", "-o", dest,
        f"https://www.youtube.com/watch?v={video_id}",
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=600, env=env)
    if not os.path.exists(dest) or os.path.getsize(dest) < 10000:
        raise RuntimeError(f"yt-dlp gagal: {(r.stderr or r.stdout or 'kosong')[-150:]}")


def _arc_cdn(video_id: str, video: bool) -> str | None:
    """Ambil cdn dari Arc API (bisa URL langsung atau link t.me)."""
    d = _arc_request(
        "/youtube/v2/download",
        {"query": video_id, "isVideo": "true" if video else "false"},
    )
    if d.get("job_id") is None and d.get("result", {}).get("success"):
        return d["result"].get("cdn")
    return None


def _download_media(video_id: str, dest: str, video: bool) -> None:
    """Download media: Arc (cdn langsung) dulu, yt-dlp (cookies) cadangan.
    Link t.me dari Arc ditangani _download_via_userbot() di sisi async."""
    try:
        cdn = _arc_cdn(video_id, video)
        if cdn and not cdn.startswith("https://t.me/"):
            _arc_fetch(cdn, dest)
            if os.path.exists(dest) and os.path.getsize(dest) > 10000:
                return
    except Exception:
        with contextlib.suppress(Exception):
            os.remove(dest)

    # yt-dlp (cadangan, pakai cookies)
    _ytdlp_download(video_id, dest, video)


def _arc_fetch(cdn: str, dest: str) -> None:
    """Unduh file dari CDN langsung Arc (bukan link t.me)."""
    import urllib.request

    req = urllib.request.Request(cdn, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=180) as r, open(dest, "wb") as f:
        while True:
            chunk = r.read(262144)
            if not chunk:
                break
            f.write(chunk)


class Music(Module):
    name = "Music Assistant"
    cmds = "play|vplay <judul> | pause | resume | skip | playlist | volume <1-200> | stop"
    desc = {
        "play <judul>": "Assistant join VC & putar AUDIO dari YouTube.",
        "vplay <judul>": "Assistant join VC & putar VIDEO dari YouTube.",
        "pause": "Pause lagu yang sedang diputar.",
        "resume": "Lanjutkan lagu yang di-pause.",
        "skip": "Lewati lagu, putar berikutnya di queue.",
        "playlist": "Lihat lagu sekarang + antrian.",
        "volume <n>": "Set volume 1-200.",
        "stop": "Stop lagu & assistant keluar VC.",
        "e.g.": "play melukis senja | volume 150",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.call = None          # PyTgCalls instance (milik assistant)
        self.current_chat = None  # chat_id VC aktif
        self.play_token = 0       # naik setiap play baru (batal watcher lama)
        self.queue = []           # antrian: list f_info dict
        self.paused = False

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
        # Kalau sudah ada play baru manual (token beda), watcher ini batal
        if self.play_token != token:
            with contextlib.suppress(Exception):
                import shutil
                shutil.rmtree(os.path.dirname(dest), ignore_errors=True)
            return
        # Hapus lagu ini dari queue head
        with contextlib.suppress(Exception):
            if self.queue and self.queue[0].get("vid") and self.queue:
                self.queue.pop(0)
        # Masih ada antrian → auto-next, jangan keluar VC
        if self.queue and self.current_chat == chat_id:
            nxt = self.queue[0]
            with contextlib.suppress(Exception):
                await self._play_file(None, nxt)
            return
        # Assistant keluar VC
        if self.current_chat == chat_id:
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

    async def _arc_tme_download(self, tme_link: str, dest: str) -> bool:
        """Unduh file dari link t.me Arc API pakai userbot assistant."""
        import re as _re

        try:
            assistant = getattr(self.client, "assistant", None) or self.client.app
            m = _re.search(r"t\.me/([^/]+)/(\d+)", tme_link)
            if not m:
                return False
            chat, msg_id = m.group(1), int(m.group(2))
            msg = await assistant.get_messages(chat, msg_id)
            if msg is None:
                return False
            path = await assistant.download_media(msg, file_name=dest)
            return bool(path) and os.path.exists(dest) and os.path.getsize(dest) > 10000
        except Exception as e:
            with contextlib.suppress(Exception):
                self.logger.warning(f"arc t.me download gagal: {e!r}")
            return False

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

    async def _status(self, event: Message, text: str, revoke: int = 0):
        if event is None:
            # auto-next tanpa event → kirim ke chat VC
            if self.current_chat:
                with contextlib.suppress(Exception):
                    sent = await self.client.app.send_message(self.current_chat, text)
                    if revoke and sent:
                        await asyncio.sleep(revoke)
                        with contextlib.suppress(Exception):
                            await sent.delete()
                    return sent
            return None
        with contextlib.suppress(Exception):
            edited = await event.edit_text(text)
            if revoke and edited:
                await asyncio.sleep(revoke)
                with contextlib.suppress(Exception):
                    await edited.delete()
            return edited
        with contextlib.suppress(Exception):
            edited = await event.edit_message_text(text)
            if revoke and edited:
                await asyncio.sleep(revoke)
                with contextlib.suppress(Exception):
                    await edited.delete()
            return edited
        with contextlib.suppress(Exception):
            cid = getattr(getattr(event, "message", None), "chat", None) or getattr(event, "chat", None)
            if cid:
                sent = await self.client.app.send_message(cid.id, text)
                if revoke and sent:
                    await asyncio.sleep(revoke)
                    with contextlib.suppress(Exception):
                        await sent.delete()
                return sent
        return None

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

        # kontrol VC simpel
        if action == "pause":
            await self._do_pause(event)
            return
        if action == "resume":
            await self._do_resume(event)
            return
        if action == "volume":
            await self._do_volume(event, query)
            return
        if action == "playlist":
            await self._do_playlist(event)
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

        status = await self._status(event, "<code>Mencari lagu...</code>")

        # 1. Search
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, _yt_search, query)
        except Exception as e:
            await self._status(event, f"Search gagal: <code>{e}</code>")
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
            await self._status(event, f"{e.__class__.__name__}: <code>{e}</code>")
            return

        # 3. Download
        kind = "video" if is_video else "audio"

        # Kalau VC lagi jalan di chat ini → masuk antrian, bukan main langsung
        if self.current_chat == chat_id and self.queue:
            url = f"https://www.youtube.com/watch?v={vid}"
            req_by = getattr(getattr(event, "from_user", None), "first_name", None) or "Assistant"
            self.queue.append({"vid": vid, "title": title, "author": author,
                               "is_video": is_video, "url": url,
                               "dur": "-", "req_by": req_by})
            pos = len(self.queue)
            rich_done = False
            if isinstance(event, Message):
                try:
                    import richpyro as rp

                    trows = [
                        [rp.table_cell("Title", align="left"),
                         rp.table_cell(title, align="left")],
                        [rp.table_cell("Channel", align="left"),
                         rp.table_cell(author, align="left")],
                        [rp.table_cell("Posisi", align="left"),
                         rp.table_cell(f"#{pos}", align="left")],
                    ]
                    blocks = [
                        rp.table([
                            [rp.table_cell("Masuk Antrian", is_header=True,
                                           colspan=2, align="center")],
                        ], bordered=False, compact=False),
                        rp.divider(),
                        rp.table(trows, bordered=True, striped=True),
                    ]
                    from pyrogram.enums import ButtonStyle as _BS
                    blocks.append(rp.buttons(
                        rp.btn("Playlist", callback_data=b"music:playlist", style=_BS.PRIMARY),
                        rp.btn("Tutup", callback_data=b"0", style=_BS.DANGER),
                    ))
                    await self.send_rich_blocks(event, blocks, query_prefix="music")
                except Exception as e:
                    with contextlib.suppress(Exception):
                        self.logger.warning(f"music rich failed: {e!r}")
            with contextlib.suppress(Exception):
                await event.delete()
            return

        await self._status(event, f"<code>Downloading {kind}:</code> {title}")
        tmp_dir = tempfile.mkdtemp(prefix="music_")
        ext = "mp4" if is_video else "m4a"
        dest = os.path.join(tmp_dir, f"{vid}.{ext}")
        try:
            # Arc dulu — kalau cdn-nya link t.me, unduh via userbot assistant
            arc_cdn = None
            with contextlib.suppress(Exception):
                arc_cdn = _arc_cdn(vid, is_video)
            downloaded = False
            if arc_cdn and arc_cdn.startswith("https://t.me/"):
                downloaded = await self._arc_tme_download(arc_cdn, dest)
            if not downloaded:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, _download_media, vid, dest, is_video)
        except Exception as e:
            await self._status(event, f"Download gagal: <code>{e}</code>")
            return

        if not os.path.exists(dest) or os.path.getsize(dest) < 10000:
            await self._status(event, "<code>Media kosong / terlalu kecil.</code>")
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
        emoji = "" if is_video else ""
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
                event, f"PyTgCalls: <code>{e.__class__.__name__}: {e}</code>"
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

        # Daftarkan sebagai "now playing" (queue[0])
        req_by = getattr(getattr(event, "from_user", None), "first_name", None) or "Assistant"
        self.queue.insert(0, {"vid": vid, "title": title, "author": author,
                              "is_video": is_video, "url": yt_link, "dur": dur_txt,
                              "req_by": req_by})

        # Rich card ala TgMusic via send_rich_blocks; kalau gagal → HTML di bawah
        rich_done = False
        if isinstance(event, Message):
            try:
                import richpyro as rp

                trows = [
                    [rp.table_cell("Title", align="left"),
                     rp.table_cell(title, align="left")],
                    [rp.table_cell("Duration", align="left"),
                     rp.table_cell(dur_txt, align="left")],
                    [rp.table_cell("Channel", align="left"),
                     rp.table_cell(author, align="left")],
                    [rp.table_cell("Mode", align="left"),
                     rp.table_cell("Video" if is_video else "Audio", align="left")],
                    [rp.table_cell("Requested", align="left"),
                     rp.table_cell(req_by, align="left")],
                ]
                blocks = [
                    rp.table([
                        [rp.table_cell("Now Playing", is_header=True,
                                       colspan=2, align="center")],
                    ], bordered=False, compact=False),
                    rp.divider(),
                    rp.table(trows, bordered=True, striped=True, compact=False),
                ]
                from pyrogram.enums import ButtonStyle as _BS
                blocks.append(rp.buttons(
                    rp.btn("Stop", callback_data=b"music:stop", style=_BS.DANGER),
                    rp.btn("Skip", callback_data=b"music:skip", style=_BS.PRIMARY),
                    rp.btn("Pause", callback_data=b"music:pause", style=_BS.DEFAULT),
                    rp.btn("Tutup", callback_data=b"0", style=_BS.DANGER),
                ))
                rich_done = await self.send_rich_blocks(event, blocks, query_prefix="music")
            except Exception as e:
                with contextlib.suppress(Exception):
                    self.logger.warning(f"music rich failed: {e!r}")

        if rich_done:
            with contextlib.suppress(Exception):
                await event.delete()

    @handler(filters.regex(r"^music:(stop|pause|resume|skip)$"), 1)
    async def on_inline_callback(self, event) -> None:
        """Callback tombol rich dari kartu Now Playing."""
        from pyrogram.types import CallbackQuery

        if not isinstance(event, CallbackQuery):
            return
        action = (event.data if isinstance(event.data, str) else event.data.decode()).split(":", 1)[1]
        if action == "stop":
            await self._do_stop(event)
        elif action == "pause":
            await self._do_pause(event)
        elif action == "resume":
            await self._do_resume(event)
        elif action == "skip":
            await self._do_skip(event)
        elif action == "playlist":
            await self._do_playlist(event)

    async def _delete_now_playing(self) -> None:
        """Hapus kartu Now Playing yang nyangkut di chat VC."""
        msg = getattr(self, "np_msg", None)
        if msg and self.current_chat:
            with contextlib.suppress(Exception):
                await self.client.app.delete_messages(
                    self.current_chat, [msg.id], revoke=True
                )
            self.np_msg = None

    async def _do_stop(self, event) -> None:
        try:
            if self.current_chat:
                self.play_token += 1
                call = await self._get_call()
                with contextlib.suppress(Exception):
                    await call.leave_call(self.current_chat)
                self.current_chat = None
            self.queue.clear()
            self.paused = False
            # hapus kartu Now Playing yang nyangkut
            await self._delete_now_playing()
            await self._status(event, "<code>Stopped. Assistant keluar VC.</code>", revoke=5)
        except Exception as e:
            await self._status(event, f"<code>{e}</code>")

    # ------------------------------------------------------
    # Queue & kontrol
    # ------------------------------------------------------

    def _now(self) -> dict | None:
        return self.queue[0] if self.queue else None

    async def _do_pause(self, event) -> None:
        if not self.current_chat:
            return await self._status(event, "<code>Gak ada media yang diputar.</code>")
        try:
            await (await self._get_call()).pause(self.current_chat)
            self.paused = True
            now = self._now() or {}
            await self._status(event, f"<code>Paused: {now.get('title', '-')}</code>")
        except Exception as e:
            await self._status(event, f"<code>{e}</code>")

    async def _do_resume(self, event) -> None:
        if not self.current_chat:
            return await self._status(event, "<code>Gak ada media yang diputar.</code>")
        try:
            await (await self._get_call()).resume(self.current_chat)
            self.paused = False
            now = self._now() or {}
            await self._status(event, f"<code>▶Resumed: {now.get('title', '-')}</code>")
        except Exception as e:
            await self._status(event, f"<code>{e}</code>")

    async def _do_volume(self, event, query: str) -> None:
        if not self.current_chat:
            return await self._status(event, "<code>Gak ada media yang diputar.</code>")
        try:
            val = int((query or "").strip().rstrip("%"))
        except ValueError:
            return await self._status(event, "<code>Usage: volume 1-200</code>")
        if not 1 <= val <= 200:
            return await self._status(event, "<code>Volume harus 1-200.</code>")
        try:
            await (await self._get_call()).change_volume(self.current_chat, val)
            await self._status(event, f"<code>Volume: {val}%</code>")
        except Exception as e:
            await self._status(event, f"<code>{e}</code>")

    async def _do_playlist(self, event) -> None:
        if not self.queue:
            return await self._status(event, "<code>Queue kosong.</code>")
        now = self.queue[0]
        lines = ["<b>Now Playing</b>",
                 f"{now.get('title', '-')}",
                 f"{now.get('dur', '-')} | {now.get('author', '-')}", ""]
        if len(self.queue) > 1:
            lines.append("<b>Queue</b>")
            for i, t in enumerate(self.queue[1:], 1):
                lines.append(f"{i}. {t.get('title', '-')} ({t.get('dur', '-')})")
        await self._status(event, "\n".join(lines))

    async def _do_skip(self, event) -> None:
        if not self.queue:
            return await self._status(event, "<code>Queue kosong.</code>")
        skipped = self.queue.pop(0)
        if not self.queue:
            await self._do_stop(event)
            return
        nxt = self.queue[0]
        await self._status(event, f"<code>Skipped: {skipped.get('title', '-')}</code>")
        await self._play_file(event, nxt)

    async def _play_file(self, event, info: dict) -> None:
        """Download + play sebuah item queue (dict dengan vid/title/author/is_video)."""
        status = await self._status(event, f"<code>Downloading: {info['title']}</code>")
        vid = info["vid"]
        is_video = info.get("is_video", False)
        tmp_dir = tempfile.mkdtemp(prefix="music_")
        ext = "mp4" if is_video else "m4a"
        dest = os.path.join(tmp_dir, f"{vid}.{ext}")
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, _download_media, vid, dest, is_video)
        except Exception as e:
            await self._status(event, f"Download gagal: <code>{e}</code>")
            return
        if not is_video:
            audio_dest = os.path.join(tmp_dir, f"{vid}.m4a")
            with contextlib.suppress(Exception):
                proc = await asyncio.create_subprocess_exec(
                    "ffmpeg", "-y", "-i", dest, "-vn", "-acodec", "copy", audio_dest,
                    stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
                await proc.wait()
                if os.path.exists(audio_dest) and os.path.getsize(audio_dest) > 10000:
                    dest = audio_dest
        try:
            from pytgcalls.types import MediaStream
            call = await self._get_call()
            stream = MediaStream(
                dest,
                audio_flags=MediaStream.Flags.REQUIRED,
                video_flags=MediaStream.Flags.REQUIRED if is_video else MediaStream.Flags.IGNORE,
            )
            await call.play(self.current_chat, stream)
            self.paused = False
            self.play_token += 1
            asyncio.ensure_future(self._wait_finish(self.current_chat, dest, self.play_token))
        except Exception as e:
            await self._status(event, f"PyTgCalls: <code>{e}</code>")
            return

        # Update durasi hasil ffprobe
        dur_txt = info.get("dur", "-")
        try:
            proc = await asyncio.create_subprocess_exec(
                "ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "csv=p=0", dest,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
            )
            out, _ = await proc.communicate()
            dur_s = int(float(out.decode().strip() or 0))
            if dur_s:
                dur_txt = f"{dur_s // 60}:{dur_s % 60:02d}"
                info["dur"] = dur_txt
        except Exception:
            pass
        if self.queue and self.queue[0].get("vid") == vid:
            self.queue[0] = info

        # Kartu rich " Now Playing" (juga untuk auto-next via event=None)
        yt_link = info.get("url") or f"https://www.youtube.com/watch?v={vid}"
        emoji = "" if is_video else ""
        rich_done = False
        try:
            import richpyro as rp

            trows = [
                [rp.table_cell("Title", align="left"),
                 rp.table_cell(info["title"], align="left")],
                [rp.table_cell("Duration", align="left"),
                 rp.table_cell(dur_txt, align="left")],
                [rp.table_cell("Channel", align="left"),
                 rp.table_cell(info.get("author", "-"), align="left")],
                [rp.table_cell("Mode", align="left"),
                 rp.table_cell("Video" if is_video else "Audio", align="left")],
                [rp.table_cell("Requested", align="left"),
                 rp.table_cell(info.get("req_by", "Assistant"), align="left")],
            ]
            blocks = [
                rp.table([
                    [rp.table_cell("Now Playing", is_header=True,
                                   colspan=2, align="center")],
                ], bordered=False, compact=False),
                rp.divider(),
                rp.table(trows, bordered=True, striped=True, compact=False),
            ]
            from pyrogram.enums import ButtonStyle as _BS
            blocks.append(rp.buttons(
                rp.btn("Stop", callback_data=b"music:stop", style=_BS.DANGER),
                rp.btn("Skip", callback_data=b"music:skip", style=_BS.PRIMARY),
                rp.btn("Pause", callback_data=b"music:pause", style=_BS.DEFAULT),
                rp.btn("Tutup", callback_data=b"0", style=_BS.DANGER),
            ))
            if event is not None:
                await self.send_rich_blocks(event, blocks, query_prefix="music")
                with contextlib.suppress(Exception):
                    await event.delete()
            else:
                # auto-next: kirim kartu rich baru ke chat VC
                await self.send_rich_blocks(None, blocks, query_prefix="music", chat_id=self.current_chat)
        except Exception as e:
            with contextlib.suppress(Exception):
                self.logger.warning(f"music rich failed: {e!r}")
