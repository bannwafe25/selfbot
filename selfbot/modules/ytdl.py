import asyncio
import contextlib
import datetime
import html
import os
import re
import shutil
from pathlib import Path

from pyrogram import filters
from pyrogram.types import Message, ReplyParameters
from py_yt import VideosSearch

from selfbot.listener import handler
from selfbot.module import Module
from selfbot.apis import DELINE_YTMP3, FERDEV_YTMP3, FERDEV_APIKEY

try:
    import yt_dlp
except ImportError:
    yt_dlp = None

pattern = re.compile(r"^(song|vsong)(?:\s+(-d|--doc|-v|--voice))?\s+(.+)$", re.IGNORECASE)
yt_id_pattern = re.compile(r'"videoId":"([A-Za-z0-9_-]{11})"')


class YtDL(Module):
    name = "YtDL"
    cmds = "song|vsong (-d|--doc|-v|--voice)? {query}"
    desc = {
        "query": "A YouTube link, video ID, or title search query.",
        "song": "Send as audio (MP3).",
        "vsong": "Send as video (MP4).",
        "-d, --doc": "Send as a document file.",
        "-v, --voice": "Send as a voice message.",
        "e.g.": "song NaFF Kau Masih Kekasihku",
    }

    @staticmethod
    async def get_waveform(audio_path: str) -> bytes | None:
        try:
            proc = await asyncio.create_subprocess_exec(
                "ffmpeg",
                "-i",
                audio_path,
                "-f",
                "u8",
                "-ac",
                "1",
                "-ar",
                "8000",
                "-",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError:
            return None

        try:
            stdout, _ = await proc.communicate()
            if proc.returncode != 0 or not stdout or len(stdout) < 100:
                return None

            num_samples = 100
            step = max(1, len(stdout) // num_samples)
            sampled = []
            for i in range(num_samples):
                idx = min(i * step, len(stdout) - 1)
                sample = int((stdout[idx] / 255) * 31)
                sampled.append(max(0, min(31, sample)))
            return bytes(sampled)
        except Exception:
            with contextlib.suppress(Exception):
                proc.kill()
            return None

    @handler(filters.regex(pattern), 1)
    async def on_message_out(self, event: Message) -> None:
        await self.respond(event, "<code>Processing...</code>")
        now = datetime.datetime.now(datetime.UTC)

        text = str(event.content or "").strip()
        match = pattern.match(text)
        if not match:
            await self.respond(
                event,
                "<b>Usage:</b> <code>song|vsong &lt;youtube_link | search_query&gt;</code>",
            )
            return

        cmd, flag, query = match.groups()
        is_video = (cmd or "").lower().startswith("vsong")
        query = query.strip()

        yt_link = self._extract_youtube_url(query)
        if not yt_link:
            await self.respond(
                event,
                f"<code>Searching for '{html.escape(query[:100])}'...</code>",
            )
            yt_link = await self._search_youtube_url(query)
            if not yt_link:
                await self.respond(
                    event,
                    f"<code>No YouTube results found for '{html.escape(query[:100])}'.</code>",
                )
                return

        if is_video:
            await self._vsong(event, yt_link, now)
            return

        await self.respond(event, "<code>Fetching song from API...</code>")

        audio_file = None
        thumb_file = None
        try:
            song_data = await self._fetch_song_data(yt_link)
            title = song_data["title"]
            thumb_url = song_data["thumbnail"]
            quality = song_data["quality"]
            size_label = song_data["size_label"]
            ext = song_data["ext"]
            dlink = song_data["dlink"]
            duration = song_data["duration"]
            if not dlink:
                raise RuntimeError("API did not provide a download link.")

            download_dir = Path("downloads")
            download_dir.mkdir(parents=True, exist_ok=True)

            safe_title = self._safe_name(title)
            suffix = f"{event.chat.id}_{event.id}"
            audio_file = download_dir / f"{safe_title}_{suffix}.{ext}"
            thumb_file = download_dir / f"thumb_{suffix}.jpg"

            await self.respond(
                event, f"<code>Downloading: {html.escape(title[:100])}</code>"
            )
            if song_data.get("local_file"):
                # Sudah di-download yt-dlp langsung — tinggal rename ke tujuan
                local = Path(dlink)
                if local.exists():
                    local.rename(audio_file)
            try:
                if not audio_file.exists():
                    await self._download_file(str(dlink), audio_file, timeout=300)
            except Exception as first_err:
                # Tunnel bisa expired/kosong — minta link baru lalu coba sekali lagi
                self.logger.warning(f"Download failed ({first_err}), refreshing link...")
                song_data = await self._fetch_song_data(yt_link)
                dlink = song_data["dlink"]
                if not dlink:
                    raise RuntimeError("API did not provide a download link.")
                await self._download_file(str(dlink), audio_file, timeout=300)
            if not audio_file.exists() or audio_file.stat().st_size == 0:
                raise RuntimeError("Audio file download failed or is empty.")

            if thumb_url:
                try:
                    await self._download_file(str(thumb_url), thumb_file, timeout=30)
                    if not thumb_file.exists() or thumb_file.stat().st_size == 0:
                        thumb_file = None
                except Exception:
                    self.logger.warning("Failed to download thumbnail.")
                    thumb_file = None
            else:
                thumb_file = None

            if duration <= 0:
                duration = await self._probe_duration(audio_file)
            duration_str = self._duration_text(duration)
            size_text = size_label or self.fmtbyte(audio_file.stat().st_size)
            caption_parts = [
                f"<b>Title:</b> {html.escape(title)}",
                f"<b>Duration:</b> {duration_str}",
                f"<b>Size:</b> {html.escape(size_text)}",
            ]
            if quality:
                caption_parts.append(f"<b>Quality:</b> {html.escape(quality)}")
            caption = (
                "\n".join(caption_parts)
                + f"\n\n<b><blockquote>{self.fmtsec(now)}</blockquote></b>"
            )

            reply_parameters = ReplyParameters(
                message_id=event.reply_to_message_id or event.id
            )
            thumb = str(thumb_file) if thumb_file and thumb_file.exists() else None
            normalized_flag = (flag or "").lower()

            if normalized_flag in ("-d", "--doc"):
                await event._client.send_document(
                    chat_id=event.chat.id,
                    document=str(audio_file),
                    caption=caption,
                    thumb=thumb,
                    reply_parameters=reply_parameters,
                )
            elif normalized_flag in ("-v", "--voice"):
                waveform = await self.get_waveform(str(audio_file))
                kwargs = {
                    "chat_id": event.chat.id,
                    "voice": str(audio_file),
                    "caption": caption,
                    "duration": duration,
                    "reply_parameters": reply_parameters,
                }
                if waveform:
                    kwargs["waveform"] = waveform
                await event._client.send_voice(**kwargs)
            else:
                await event._client.send_audio(
                    chat_id=event.chat.id,
                    audio=str(audio_file),
                    caption=caption,
                    title=title,
                    duration=duration,
                    thumb=thumb,
                    reply_parameters=reply_parameters,
                )

            # Kartu rich teks (audio terkirim polos di atas kartu)
            rich_rows = [
                ("Judul", title[:50] or "-"),
                ("Durasi", duration_str),
                ("Ukuran", size_text),
            ]
            if quality:
                rich_rows.append(("Quality", quality))
            flag_name = {"-d": "Document", "-v": "Voice"}.get(
                (flag or "").lower(), "Audio"
            )
            rich_rows.append(("Mode", flag_name))
            await self.send_rich(
                event,
                "🎵 Song Selesai",
                rich_rows,
                query_prefix=f"song{int(now.timestamp()*1000)}",
            )
            await event.delete()
        except Exception as e:
            self.logger.error(f"Song download error: {e}")
            await self.respond(
                event,
                f"<b>Song failed</b>\n\n<code>{html.escape(str(e)[:300])}</code>",
            )
        finally:
            for file_path in (audio_file, thumb_file):
                if not file_path:
                    continue
                with contextlib.suppress(OSError):
                    if file_path.exists():
                        file_path.unlink()

    async def _vsong(self, event: Message, yt_link: str, now) -> None:
        video_file = None
        try:
            await self.respond(event, "<code>Downloading video (bisa agak lama)...</code>")
            loop = asyncio.get_running_loop()
            title = await loop.run_in_executor(
                None, lambda: self._ytdlp_video_title(yt_link)
            )
            download_dir = Path("downloads")
            download_dir.mkdir(parents=True, exist_ok=True)
            safe_title = self._safe_name(title)
            suffix = f"{event.chat.id}_{event.id}"
            video_file = download_dir / f"{safe_title}_{suffix}.mp4"

            info = await loop.run_in_executor(
                None, lambda: self._ytdlp_download_video(yt_link, str(video_file))
            )
            title = info.get("title") or title
            duration = int(info.get("duration") or 0)
            if not video_file.exists() or video_file.stat().st_size == 0:
                raise RuntimeError("Video download failed or is empty.")
            if duration <= 0:
                duration = await self._probe_duration(video_file)

            reply_parameters = ReplyParameters(
                message_id=event.reply_to_message_id or event.id
            )
            await event._client.send_video(
                chat_id=event.chat.id,
                video=str(video_file),
                caption=(
                    f"<b>Title:</b> {html.escape(title)}\n"
                    f"<b>Duration:</b> {self._duration_text(duration)}\n"
                    f"<b>Size:</b> {video_file.stat().st_size / 1048576:.1f} MB\n\n"
                    f"<b><blockquote>{self.fmtsec(now)}</blockquote></b>"
                ),
                supports_streaming=True,
                reply_parameters=reply_parameters,
            )

            # Kartu rich teks (video terkirim polos di atas kartu)
            await self.send_rich(
                event,
                "🎬 VSong Selesai",
                [
                    ("Judul", title[:50] or "-"),
                    ("Durasi", self._duration_text(duration)),
                    ("Ukuran", f"{video_file.stat().st_size / 1048576:.1f} MB"),
                    ("Format", "MP4"),
                ],
                query_prefix=f"vsong{int(now.timestamp()*1000)}",
            )
            await event.delete()
        except Exception as e:
            self.logger.error(f"VSong download error: {e}")
            await self.respond(
                event,
                f"<b>VSong failed</b>\n\n<code>{html.escape(str(e)[:300])}</code>",
            )
        finally:
            if video_file:
                with contextlib.suppress(OSError):
                    if video_file.exists():
                        video_file.unlink()

    def _ytdlp_video_opts(self, outtmpl: str | None = None) -> dict:
        opts = self._ytdlp_base_opts()
        if outtmpl:
            opts["format"] = "best[ext=mp4]/bestvideo[ext=mp4]+bestaudio[ext=m4a]/best"
            opts["outtmpl"] = outtmpl
            opts["merge_output_format"] = "mp4"
        return opts

    def _ytdlp_video_title(self, yt_link: str) -> str:
        with yt_dlp.YoutubeDL(self._ytdlp_video_opts()) as ydl:
            info = ydl.extract_info(yt_link, download=False)
        return info.get("title") or "vsong"

    def _ytdlp_download_video(self, yt_link: str, outtmpl: str) -> dict:
        with yt_dlp.YoutubeDL(self._ytdlp_video_opts(outtmpl)) as ydl:
            return ydl.extract_info(yt_link, download=True)

    async def _fetch_song_data(self, yt_link: str) -> dict:
        # Local yt-dlp engine first (no API limits). Raises RuntimeError
        # if yt-dlp is unavailable so callers fall back to remote APIs.
        if yt_dlp is not None:
            try:
                info = await asyncio.get_running_loop().run_in_executor(
                    None,
                    lambda: self._ytdlp_extract(yt_link),
                )
                # yt-dlp langsung download audio (URL googlevideo sering
                # 403 kalau diakses httpx tanpa headers yt-dlp).
                out = Path("downloads") / f"ytaudio_{int(asyncio.get_running_loop().time() * 1000)}"
                out.parent.mkdir(parents=True, exist_ok=True)
                dl = await asyncio.get_running_loop().run_in_executor(
                    None,
                    lambda: self._ytdlp_download_audio(yt_link, out),
                )
                if dl and dl.exists() and dl.stat().st_size > 0:
                    info["dlink"] = str(dl)
                    info["local_file"] = True
                    info["ext"] = dl.suffix.lstrip(".") or "mp3"
                return info
            except Exception as e:
                self.logger.warning(f"yt-dlp engine failed, fallback to API: {e}")
        else:
            self.logger.warning("yt_dlp not installed, using APIs")

        try:
            return await self._fetch_song_data_deline(yt_link)
        except Exception as e:
            self.logger.warning(f"Primary API failed, fallback to ferdev: {e}")

        try:
            return await self._fetch_song_data_cobalt(yt_link)
        except Exception as e:
            self.logger.warning(f"Cobalt failed, fallback to ferdev: {e}")
            return await self._fetch_song_data_ferdev(yt_link)

    async def _fetch_song_data_cobalt(self, yt_link: str) -> dict:
        import json as _json

        resp = await self.client.http.post(
            "https://co.otomir23.me/",
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            json={"url": yt_link, "downloadMode": "audio", "audioFormat": "mp3"},
            timeout=60,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"Cobalt API error: HTTP {resp.status_code}")

        data = _json.loads(resp.text)
        if data.get("status") != "tunnel" or not data.get("url"):
            raise RuntimeError(
                f"Cobalt returned status={data.get('status')}"
            )

        return {
            "title": data.get("filename", "").rsplit(".", 1)[0] or "Untitled",
            "thumbnail": "",
            "quality": "",
            "size_label": "",
            "ext": "mp3",
            "dlink": data["url"],
            "duration": 0,
        }

    def _ytdlp_base_opts(self, skip_download: bool = True) -> dict:
        opts = {
            "format": "bestaudio/best",
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "skip_download": skip_download,
            "js_runtimes": {"deno": {"path": "/usr/local/bin/deno"}},
            "remote_components": ["ejs:github"],
        }
        # YouTube bot-check workaround: pakai cookies bila tersedia.
        cookie_file = os.environ.get("YTDLP_COOKIES") or "/home/agentuser/cookies.txt"
        if os.path.isfile(cookie_file):
            opts["cookiefile"] = cookie_file
        # yt-dlp default hanya pakai deno; daftarkan node (tersedia di server)
        # sebagai JS runtime buat n-challenge solver (EJS).
        node_path = os.environ.get("NODE_PATH") or shutil.which("node") or "/usr/local/bin/node"
        deno_path = os.environ.get("DENO_PATH") or shutil.which("deno") or "/usr/local/bin/deno"
        opts["js_runtimes"] = {"node": {"path": node_path}, "deno": {"path": deno_path}}
        opts["remote_components"] = ["ejs:github"]
        return opts

    def _ytdlp_download_audio(self, yt_link: str, out_base: Path) -> Path | None:
        opts = self._ytdlp_base_opts(skip_download=False)
        opts["format"] = "bestaudio/best"
        opts["outtmpl"] = str(out_base) + ".%(ext)s"
        # Auto-convert ke MP3 biar format konsisten
        opts["postprocessors"] = [
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}
        ]
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.extract_info(yt_link, download=True)
        mp3 = out_base.with_suffix(".mp3")
        if mp3.exists():
            return mp3
        for p in out_base.parent.glob(out_base.name + ".*"):
            if p.is_file():
                return p
        return None

    def _ytdlp_extract(self, yt_link: str) -> dict:
        opts = self._ytdlp_base_opts()
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(yt_link, download=False)

        audio = [f for f in (info.get("formats") or []) if f.get("acodec") not in (None, "none")]
        if not audio:
            raise RuntimeError("No audio stream found by yt-dlp.")
        best = max(audio, key=lambda f: f.get("abr") or f.get("tbr") or 0)
        url = best.get("url")
        if not url:
            raise RuntimeError("yt-dlp returned no direct URL.")

        size = best.get("filesize") or best.get("filesize_approx") or 0
        return {
            "title": info.get("title") or "Untitled",
            "thumbnail": info.get("thumbnail") or "",
            "quality": f"{best.get('abr', 0) or ''}kbps".strip("kbps ") or "audio",
            "size_label": self.fmtbyte(size) if size else "",
            "ext": best.get("ext") or "m4a",
            "dlink": url,
            "duration": int(info.get("duration") or 0),
        }

    async def _fetch_song_data_deline(self, yt_link: str) -> dict:
        resp = await self.client.http.get(
            DELINE_YTMP3,
            params={"url": yt_link},
            timeout=60,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"API error: HTTP {resp.status_code}")

        try:
            data = resp.json()
        except Exception as e:
            raise RuntimeError(f"Invalid API response: {e}") from e

        if not isinstance(data, dict):
            raise RuntimeError("API response is not JSON object.")

        if not data.get("status"):
            err = (
                data.get("error")
                or data.get("message")
                or data.get("msg")
                or "API returned an error."
            )
            raise RuntimeError(str(err))

        result = data.get("result") or {}
        if not isinstance(result, dict):
            raise RuntimeError("API returned empty song data.")

        youtube_data = result.get("youtube") or {}
        pick_data = result.get("pick") or {}
        title = str(youtube_data.get("title") or "Untitled").strip()
        dlink = str(result.get("dlink") or "").strip()
        ext = str(pick_data.get("ext") or "mp3").strip().lower()
        if not re.fullmatch(r"[a-z0-9]{1,6}", ext):
            ext = "mp3"

        return {
            "title": title or "Untitled",
            "thumbnail": str(youtube_data.get("thumbnail") or "").strip(),
            "quality": str(pick_data.get("quality") or "").strip(),
            "size_label": str(pick_data.get("size") or "").strip(),
            "ext": ext,
            "dlink": dlink,
            "duration": 0,
        }

    async def _fetch_song_data_ferdev(self, yt_link: str) -> dict:
        api_key = await self.getvar("FERDEV_API_KEY", FERDEV_APIKEY)
        resp = await self.client.http.get(
            FERDEV_YTMP3,
            params={"link": yt_link, "apikey": api_key},
            timeout=60,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"Fallback API error: HTTP {resp.status_code}")

        try:
            data = resp.json()
        except Exception as e:
            raise RuntimeError(f"Invalid fallback API response: {e}") from e

        if not isinstance(data, dict):
            raise RuntimeError("Fallback API response is not JSON object.")
        if not data.get("success"):
            raise RuntimeError(
                str(
                    data.get("message")
                    or data.get("error")
                    or "Fallback API returned an error."
                )
            )

        payload = data.get("data") or {}
        if not isinstance(payload, dict):
            raise RuntimeError("Fallback API returned empty song data.")

        dlink = str(payload.get("dlink") or "").strip()
        title = str(payload.get("title") or "Untitled").strip()
        thumb = str(payload.get("thumbnail") or "").strip()

        size_value = payload.get("size")
        if isinstance(size_value, (int, float)) and size_value > 0:
            size_label = self.fmtbyte(int(size_value))
        else:
            size_label = str(size_value or "").strip()

        duration = self._parse_int(payload.get("duration"))
        ext = "mp3"
        if "." in dlink.rsplit("/", 1)[-1]:
            maybe_ext = dlink.rsplit("/", 1)[-1].rsplit(".", 1)[-1].lower()
            if re.fullmatch(r"[a-z0-9]{1,6}", maybe_ext):
                ext = maybe_ext

        return {
            "title": title or "Untitled",
            "thumbnail": thumb,
            "quality": "",
            "size_label": size_label,
            "ext": ext,
            "dlink": dlink,
            "duration": duration,
        }

    async def _download_file(self, url: str, out_file: Path, timeout: int) -> None:
        for attempt in range(3):
            try:
                async with self.client.http.stream("GET", url, timeout=timeout) as resp:
                    if resp.status_code != 200:
                        raise RuntimeError(f"Download failed: HTTP {resp.status_code}")
                    with out_file.open("wb") as handle:
                        async for chunk in resp.aiter_bytes(chunk_size=65536):
                            if chunk:
                                handle.write(chunk)
                if out_file.exists() and out_file.stat().st_size > 0:
                    return
                self.logger.warning(f"Download attempt {attempt + 1} empty, retrying...")
            except Exception as e:
                self.logger.warning(f"Download attempt {attempt + 1} failed: {e}")
            await asyncio.sleep(2)

        # Final fallback: plain GET download
        resp = await self.client.http.get(url, timeout=timeout)
        if resp.status_code != 200 or not resp.content:
            raise RuntimeError(f"Download failed: HTTP {resp.status_code}")
        with out_file.open("wb") as handle:
            handle.write(resp.content)

    async def _search_youtube_url(self, query: str) -> str | None:
        # Primary search via py-yt-search.
        try:
            data = await VideosSearch(query, limit=1).next()
            result = (data or {}).get("result") or []
            if result:
                item = result[0] or {}
                vid = str(item.get("id") or "").strip()
                link = str(item.get("link") or "").strip()
                if vid and re.fullmatch(r"[A-Za-z0-9_-]{11}", vid):
                    return f"https://youtu.be/{vid}"
                if link:
                    ext = self._extract_youtube_url(link)
                    if ext:
                        return ext
        except Exception:
            pass

        # Fallback search by scraping YouTube results page.
        resp = await self.client.http.get(
            "https://www.youtube.com/results",
            params={"search_query": query},
            timeout=30,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        if resp.status_code != 200:
            return None

        seen = set()
        for vid in yt_id_pattern.findall(resp.text):
            if vid in seen:
                continue
            seen.add(vid)
            return f"https://youtu.be/{vid}"
        return None

    @staticmethod
    def _extract_youtube_url(query: str) -> str | None:
        query = query.strip()
        if re.fullmatch(r"[A-Za-z0-9_-]{11}", query):
            return f"https://youtu.be/{query}"

        patterns = (
            r"(?:https?://)?(?:www\.)?youtu\.be/([A-Za-z0-9_-]{11})",
            r"(?:https?://)?(?:www\.)?youtube\.com/watch\?(?:.*&)?v=([A-Za-z0-9_-]{11})",
            r"(?:https?://)?(?:www\.)?youtube\.com/shorts/([A-Za-z0-9_-]{11})",
            r"(?:https?://)?(?:www\.)?youtube\.com/embed/([A-Za-z0-9_-]{11})",
        )
        for pattern in patterns:
            match = re.search(pattern, query)
            if match:
                return f"https://youtu.be/{match.group(1)}"
        return None

    @staticmethod
    def _safe_name(name: str) -> str:
        clean = re.sub(r"[<>:\"/\\|?*\x00-\x1f]", "", name).strip()
        clean = re.sub(r"\s+", " ", clean)
        return clean[:60] or "song"

    @staticmethod
    def _parse_int(value: object) -> int:
        try:
            return max(0, int(float(value)))
        except (TypeError, ValueError):
            return 0

    async def _probe_duration(self, audio_path: Path) -> int:
        try:
            proc = await asyncio.create_subprocess_exec(
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(audio_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError:
            return 0

        try:
            stdout, _ = await proc.communicate()
            if proc.returncode != 0:
                return 0

            value = (stdout or b"").decode("utf-8", errors="ignore").strip()
            if not value:
                return 0
            return max(0, int(round(float(value))))
        except Exception:
            with contextlib.suppress(Exception):
                proc.kill()
            return 0

    @staticmethod
    def _duration_text(seconds: int) -> str:
        total = max(0, int(seconds))
        hours, rem = divmod(total, 3600)
        mins, secs = divmod(rem, 60)
        if hours:
            return f"{hours:02d}:{mins:02d}:{secs:02d}"
        return f"{mins:02d}:{secs:02d}"
