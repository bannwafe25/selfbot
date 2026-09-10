import asyncio
import datetime
import html
import re
import shutil
import tempfile
from pathlib import Path

import yt_dlp
from pyrogram import filters
from pyrogram.types import InputMediaPhoto, InputMediaVideo, Message

from selfbot import listener
from selfbot.module import Module


pattern = re.compile(
    r"^(?:igdl|instadl)\s+(https?://[^\s]+)$",
    re.IGNORECASE,
)


class InstaDL(Module):
    name = "InstaDL"

    cmds = "igdl|instadl {url}"

    desc = {
        "Info": "Download Instagram video, reel, photo, or carousel using yt-dlp.",
        "url": "The Instagram post URL.",
        "e.g.": "igdl https://www.instagram.com/p/C1234567890/",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.downloads_dir = Path("downloads")
        self.cookies_file = None

    async def on_loading(self) -> None:
        """
        Initialize downloader directories and optional Instagram cookies.
        """

        self.downloads_dir = (
            Path(__file__).resolve().parents[2] / "downloads"
        )

        await asyncio.to_thread(
            self.downloads_dir.mkdir,
            parents=True,
            exist_ok=True,
        )

        ig_cfg = self.client.config.get("instagram", {})

        if not isinstance(ig_cfg, dict):
            ig_cfg = {}

        cookies = (
            ig_cfg.get("cookies")
            or ig_cfg.get("cookiefile")
            or ig_cfg.get("cookies_file")
        )

        if cookies:
            cookies_path = Path(str(cookies))

            if not cookies_path.is_absolute():
                cookies_path = (
                    Path(__file__).resolve().parents[2] / cookies_path
                )

            if cookies_path.exists():
                self.cookies_file = cookies_path
                self.logger.info(
                    f"Instagram: Using cookies file {cookies_path}"
                )
            else:
                self.logger.warning(
                    f"Instagram cookies file not found: {cookies_path}"
                )

        self.logger.info("Instagram yt-dlp downloader loaded.")

    def _ydl_options(self, output_dir: Path) -> dict:
        """
        yt-dlp configuration.
        """

        options = {
            "outtmpl": str(output_dir / "%(id)s.%(ext)s"),

            "format": (
                "bv*+ba/"
                "b"
            ),

            "merge_output_format": "mp4",

            "noplaylist": False,

            "quiet": True,
            "no_warnings": True,

            "ignoreerrors": False,

            "retries": 3,
            "fragment_retries": 3,

            "socket_timeout": 30,

            "concurrent_fragment_downloads": 2,

            "restrictfilenames": True,

            "windowsfilenames": True,

            "overwrites": True,

            "continuedl": True,

            "nocheckcertificate": False,
        }

        if self.cookies_file:
            options["cookiefile"] = str(self.cookies_file)

        return options

    async def _download(self, url: str):
        """
        Download Instagram media using yt-dlp.
        """

        temp_dir = Path(
            tempfile.mkdtemp(
                prefix="instagram_",
                dir=str(self.downloads_dir),
            )
        )

        options = self._ydl_options(temp_dir)

        def download_sync():
            with yt_dlp.YoutubeDL(options) as ydl:
                info = ydl.extract_info(
                    url,
                    download=True,
                )

                if not info:
                    raise RuntimeError(
                        "yt-dlp returned no information."
                    )

                return info

        try:
            info = await asyncio.to_thread(
                download_sync
            )

            media_files = await asyncio.to_thread(
                self._collect_media,
                temp_dir,
            )

            if not media_files:
                raise RuntimeError(
                    "yt-dlp completed but no media files were found."
                )

            caption = self._get_caption(info)

            return (
                media_files,
                caption,
                temp_dir,
            )

        except Exception:
            await asyncio.to_thread(
                shutil.rmtree,
                temp_dir,
                ignore_errors=True,
            )
            raise

    @staticmethod
    def _collect_media(directory: Path):
        """
        Collect downloaded media files.
        """

        allowed = {
            ".mp4",
            ".mkv",
            ".webm",
            ".mov",
            ".jpg",
            ".jpeg",
            ".png",
            ".webp",
        }

        files = [
            file
            for file in directory.rglob("*")
            if file.is_file()
            and file.suffix.lower() in allowed
        ]

        files.sort(
            key=lambda x: (
                x.stat().st_mtime,
                x.name,
            )
        )

        return files

    @staticmethod
    def _get_caption(info) -> str:
        """
        Extract Instagram caption from yt-dlp metadata.
        """

        if not isinstance(info, dict):
            return ""

        caption = (
            info.get("description")
            or info.get("title")
            or ""
        )

        caption = str(caption).strip()

        if not caption:
            return ""

        return (
            "<blockquote>"
            + html.escape(caption)
            + "</blockquote>"
        )

    @staticmethod
    def _is_video(file_path: Path) -> bool:
        return file_path.suffix.lower() in {
            ".mp4",
            ".mkv",
            ".webm",
            ".mov",
        }

    async def _send_single(
        self,
        event: Message,
        file_path: Path,
        caption: str,
        reply_to: int,
    ):
        """
        Send one media file.
        """

        if self._is_video(file_path):
            await self.client.app.send_video(
                chat_id=event.chat.id,
                video=str(file_path),
                caption=caption,
                reply_to_message_id=reply_to,
            )
        else:
            await self.client.app.send_photo(
                chat_id=event.chat.id,
                photo=str(file_path),
                caption=caption,
                reply_to_message_id=reply_to,
            )

    async def _send_album_chunks(
        self,
        event: Message,
        media_files,
        caption: str,
        reply_to: int,
    ):
        """
        Telegram allows a maximum of 10 media items per album.
        """

        for start in range(0, len(media_files), 10):
            chunk = media_files[start : start + 10]

            album = []

            for index, file_path in enumerate(chunk):
                if self._is_video(file_path):
                    media_class = InputMediaVideo
                else:
                    media_class = InputMediaPhoto

                album.append(
                    media_class(
                        str(file_path),
                        caption=(
                            caption
                            if start == 0 and index == 0
                            else None
                        ),
                    )
                )

            await self.client.app.send_media_group(
                chat_id=event.chat.id,
                media=album,
                reply_to_message_id=reply_to,
            )

    @listener.handler(
        filters.regex(pattern),
        priority=1,
    )
    async def on_message_out(
        self,
        event: Message,
    ):
        match = pattern.match(
            event.text or ""
        )

        if not match:
            await event.edit(
                "Please provide an Instagram URL."
            )
            return

        url = match.group(1).strip()

        await event.edit(
            "<code>Instagram yt-dlp: Downloading...</code>"
        )

        started_at = datetime.datetime.now(
            datetime.UTC
        )

        temp_dir = None

        try:
            (
                media_files,
                caption,
                temp_dir,
            ) = await self._download(url)

            if not media_files:
                raise RuntimeError(
                    "No media found."
                )

            elapsed = self.fmtsec(
                started_at
            )

            caption_parts = []

            if caption:
                caption_parts.append(
                    caption
                )

            caption_parts.append(
                f"<a href='{html.escape(url)}'>Source</a>"
            )

            caption_parts.append(
                f"<b><blockquote>{html.escape(elapsed)}</blockquote></b>"
            )

            final_caption = "\n".join(
                caption_parts
            )

            reply_to = (
                event.reply_to_message.id
                if event.reply_to_message
                else event.id
            )

            if len(media_files) == 1:
                await self._send_single(
                    event=event,
                    file_path=media_files[0],
                    caption=final_caption,
                    reply_to=reply_to,
                )

            else:
                await self._send_album_chunks(
                    event=event,
                    media_files=media_files,
                    caption=final_caption,
                    reply_to=reply_to,
                )

            await event.delete()

        except Exception as e:
            self.logger.exception(
                "Instagram yt-dlp download failed"
            )

            error = html.escape(
                str(e)[:500]
            )

            await event.edit(
                "<b>Instagram Download Failed</b>\n\n"
                f"<code>{error}</code>"
            )

        finally:
            if temp_dir:
                await asyncio.to_thread(
                    shutil.rmtree,
                    temp_dir,
                    ignore_errors=True,
                )
