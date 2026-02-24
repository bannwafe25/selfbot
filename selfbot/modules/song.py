import asyncio
import contextlib
import datetime
import html
import re
from pathlib import Path

from pyrogram import filters
from pyrogram.types import Message, ReplyParameters
from py_yt import VideosSearch

from selfbot.listener import handler
from selfbot.module import Module
from selfbot.apis import DELINE_YTMP3, FERDEV_YTMP3, FERDEV_APIKEY

pattern = re.compile(r"^song(?:\s+(-d|--doc|-v|--voice))?\s+(.+)$", re.IGNORECASE)
yt_id_pattern = re.compile(r'"videoId":"([A-Za-z0-9_-]{11})"')


class Song(Module):
    name = "Song"
    cmds = "song (-d|--doc|-v|--voice)? {query}"
    desc = {
        "query": "A YouTube link, video ID, or title search query.",
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
                "<b>Usage:</b> <code>song (-d|--doc|-v|--voice)? &lt;youtube_link | search_query&gt;</code>",
            )
            return

        flag, query = match.groups()
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
                await event.reply_document(
                    document=str(audio_file),
                    caption=caption,
                    thumb=thumb,
                    reply_parameters=reply_parameters,
                )
            elif normalized_flag in ("-v", "--voice"):
                waveform = await self.get_waveform(str(audio_file))
                kwargs = {
                    "voice": str(audio_file),
                    "caption": caption,
                    "duration": duration,
                    "reply_parameters": reply_parameters,
                }
                if waveform:
                    kwargs["waveform"] = waveform
                await event.reply_voice(**kwargs)
            else:
                await event.reply_audio(
                    audio=str(audio_file),
                    caption=caption,
                    title=title,
                    duration=duration,
                    thumb=thumb,
                    reply_parameters=reply_parameters,
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

    async def _fetch_song_data(self, yt_link: str) -> dict:
        try:
            return await self._fetch_song_data_deline(yt_link)
        except Exception as e:
            self.logger.warning(f"Primary API failed, fallback to ferdev: {e}")
            return await self._fetch_song_data_ferdev(yt_link)

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
        async with self.client.http.stream("GET", url, timeout=timeout) as resp:
            if resp.status_code != 200:
                raise RuntimeError(f"Download failed: HTTP {resp.status_code}")
            with out_file.open("wb") as handle:
                async for chunk in resp.aiter_bytes(chunk_size=65536):
                    if chunk:
                        handle.write(chunk)

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
