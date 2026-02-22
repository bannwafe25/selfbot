import asyncio
import datetime
import random
import re
import shlex
import shutil
import time
from io import BytesIO
from pathlib import Path

from PIL import Image
from pyrogram import filters
from pyrogram.enums import MessageMediaType
from pyrogram.errors import StickersetInvalid
from pyrogram.raw import functions
from pyrogram.raw import types as raw_types
from pyrogram.types import LinkPreviewOptions, Message, User
from pyrogram.utils import FileId

from selfbot.listener import handler, reply
from selfbot.module import Module

EMOJIS = (
    "☕",
    "🤡",
    "🙂",
    "🤔",
    "🔪",
    "😂",
    "💀",
    "🔥",
    "❤️",
    "✨",
    "💯",
    "👍",
    "🎉",
    "😎",
    "😭",
    "🥺",
    "😱",
    "🤯",
    "😴",
    "🤪",
    "🥰",
    "😈",
    "👻",
    "🎭",
    "🎨",
    "🎮",
    "🎵",
    "⚡",
    "💎",
    "🌟",
    "🌙",
    "☀️",
    "🌈",
    "⭐",
    "💫",
    "🍕",
    "🍔",
    "🍿",
    "🎂",
    "🍰",
    "🍩",
    "🍪",
    "🐱",
    "🐶",
    "🐺",
    "🦊",
    "🐼",
    "🐯",
    "🦁",
    "💪",
    "🙏",
    "👏",
    "✌️",
    "🤝",
    "👊",
    "🤘",
)

pattern = re.compile(r"^kang(?:\s+.+)?$")


class Sticker(Module):
    name = "Sticker"
    cmds = "<Reply to Media> kang (-f)? (-e emoji)?"
    desc = {
        "Info": "Saves a sticker/image/gif/video to your sticker pack.",
        "-f": "Fast-forwards the video to fit 3 seconds.",
        "-e": "Specify custom emoji for the sticker.",
        "e.g.": "<Reply to Video> kang -f -e 🔥",
    }

    @handler(filters.regex(pattern) & reply, 1)
    async def on_message_out(self, event: Message) -> None:
        await self.respond(event, "<code>Processing...</code>")
        replied = event.reply_to_message
        if not replied:
            await self.respond(event, "<code>Reply to media first.</code>", revoke=2.5)
            return

        ff = "-f" in event.content.split()
        custom_emoji = None
        emoji_match = re.search(r"(?:^|\s)-e\s+(.+?)(?:\s+-f\s*|$)", event.content)
        if emoji_match:
            custom_emoji = emoji_match.group(1).strip()

        if replied.media_group_id:
            messages = await self.client.app.get_media_group(event.chat.id, replied.id)
        else:
            messages = [replied]

        success = 0
        set_short_name = None
        total = len(messages)
        for idx, msg in enumerate(messages, start=1):
            media_func = self.MEDIA_TYPE_MAP.get(msg.media)
            if not media_func:
                await self.respond(
                    event,
                    f"<code>Skipping unsupported media ({idx}/{total}).</code>",
                )
                await asyncio.sleep(1)
                continue

            await self.respond(event, f"<code>Processing {idx}/{total}...</code>")
            try:
                file_id, emoji, temp_msg = await media_func(self, message=msg, ff=ff)
                final_emoji = custom_emoji or emoji
                stickers = await self._kang_sticker(
                    event._client,
                    media_file_id=file_id,
                    emoji=final_emoji,
                    user=event.from_user or event._client.me,
                )
                if temp_msg:
                    await temp_msg.delete()

                short_name = self._extract_short_name(stickers)
                if short_name:
                    set_short_name = short_name

                success += 1
            except Exception as e:
                await self.respond(
                    event,
                    (
                        f"<b>Error on item {idx}/{total}</b>\n\n"
                        f"<code>{self._escape(str(e))}</code>"
                    ),
                )
                await asyncio.sleep(2)

        if success and set_short_name:
            url = f"https://t.me/addstickers/{set_short_name}"
            await self.respond(
                event,
                f"<b>Successfully added {success}/{total} sticker(s).</b>",
                link_preview_options=LinkPreviewOptions(url=url, show_above_text=True),
            )
        elif success:
            await self.respond(
                event,
                f"<b>Successfully added {success}/{total} sticker(s).</b>",
            )
        else:
            await self.respond(event, "<code>No valid media found to process.</code>")

    @staticmethod
    def _escape(value: str) -> str:
        return (
            value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")[:500]
        )

    @staticmethod
    def _extract_short_name(stickers) -> str | None:
        if hasattr(stickers, "set") and hasattr(stickers.set, "short_name"):
            return stickers.set.short_name
        if hasattr(stickers, "short_name"):
            return stickers.short_name
        return None

    async def _save_sticker(self, file: Path | BytesIO) -> Message:
        sent = await self.client.app.send_document("me", document=file)
        if isinstance(file, Path) and file.is_file():
            shutil.rmtree(file.parent, ignore_errors=True)
        return sent

    @staticmethod
    def _resize_photo(input_file: BytesIO) -> BytesIO:
        image = Image.open(input_file).convert("RGBA")
        maxsize = 512
        scale = maxsize / max(image.width, image.height)
        new_size = (int(image.width * scale), int(image.height * scale))
        resized = image.resize(new_size, Image.Resampling.LANCZOS)
        out = BytesIO()
        out.name = "sticker.png"
        resized.save(out, format="PNG")
        out.seek(0)
        return out

    async def _photo_kang(self, message: Message, **_) -> tuple[str, str | None, Message]:
        file = await message.download(in_memory=True)
        file.seek(0)
        resized = await asyncio.to_thread(self._resize_photo, file)
        temp = await self._save_sticker(resized)
        return temp.document.file_id, None, temp

    async def _video_kang(
        self, message: Message, ff: bool = False
    ) -> tuple[str, str | None, Message]:
        media = message.video or message.animation or message.document or message.sticker
        if not media:
            raise TypeError("Unsupported media.")

        if getattr(media, "file_size", 0) > 5 * 1024 * 1024:
            raise MemoryError("File size exceeds 5MB.")

        download_dir = Path("downloads") / str(int(time.time() * 1000))
        input_file = download_dir / "input.mp4"
        output_file = download_dir / "sticker.webm"
        download_dir.mkdir(parents=True, exist_ok=True)

        await message.download(str(input_file))
        duration = int(getattr(media, "duration", 3) or 3)
        await self._resize_video(input_file, output_file, duration=duration, ff=ff)
        temp = await self._save_sticker(output_file)
        return temp.document.file_id, None, temp

    async def _resize_video(
        self,
        input_file: Path,
        output_file: Path,
        duration: int,
        ff: bool = False,
    ) -> None:
        inq = shlex.quote(str(input_file))
        outq = shlex.quote(str(output_file))
        cmd = f"ffmpeg -hide_banner -loglevel error -i {inq} "
        if ff:
            cmd += (
                '-vf "scale=512:512:force_original_aspect_ratio=decrease:flags=lanczos,'
                'fps=30,setpts=0.3*PTS" -ss 0 -t 3 '
            )
        else:
            cmd += (
                '-vf "scale=512:512:force_original_aspect_ratio=decrease:flags=lanczos,'
                f'fps=30" -ss 0 -t {min(duration, 3)} '
            )
        cmd += (
            "-c:v libvpx-vp9 -pix_fmt yuva420p -b:v 400k -maxrate 500k -bufsize 1000k "
            f"-auto-alt-ref 0 -an -loop 0 {outq}"
        )
        output = await self.shell(cmd)
        if not output_file.exists() or output_file.stat().st_size == 0:
            raise RuntimeError(f"FFmpeg conversion failed.\n{output}")

    async def _document_kang(
        self, message: Message, ff: bool = False
    ) -> tuple[str, str | None, Message]:
        file_name = (getattr(message.document, "file_name", "") or "").lower()
        if file_name.endswith((".png", ".jpg", ".jpeg", ".webp", ".bmp")):
            return await self._photo_kang(message)
        if file_name.endswith(
            (".mp4", ".mov", ".webm", ".gif", ".avi", ".mkv", ".flv", ".m4v", ".mpeg")
        ):
            return await self._video_kang(message=message, ff=ff)
        raise TypeError("Unsupported document type.")

    async def _sticker_kang(
        self, message: Message, **_
    ) -> tuple[str, str | None, Message | None]:
        sticker = message.sticker
        if not sticker:
            raise TypeError("Invalid sticker.")
        if sticker.is_video:
            return await self._video_kang(message)
        if sticker.is_animated:
            raise TypeError("Lottie animated stickers (.tgs) are not supported.")
        return sticker.file_id, sticker.emoji, None

    async def _get_sticker_set(
        self, client, user: User
    ) -> tuple[str, str, bool, object | None]:
        count = 0
        me = self.client.app.me
        owner = me.username or f"user_{me.id}"
        suffix = f"_by_{owner}"
        create_new = False
        sticker_set = None

        while True:
            short_name = f"kang_{user.id}_{count}{suffix}"
            try:
                raw_set = await client.invoke(
                    functions.messages.GetStickerSet(
                        stickerset=raw_types.InputStickerSetShortName(
                            short_name=short_name
                        ),
                        hash=0,
                    )
                )
                sticker_set = raw_set.set
                if sticker_set.count < 120:
                    break
                count += 1
            except StickersetInvalid:
                create_new = True
                sticker_set = None
                break

        title = f"{user.first_name}'s Kang Pack Vol. {count + 1}"
        return short_name, title, create_new, sticker_set

    async def _kang_sticker(
        self, client, media_file_id: str, emoji: str | None, user: User
    ):
        short_name, title, create_new, sticker_set = await self._get_sticker_set(
            client, user
        )
        file_id = FileId.decode(media_file_id)
        document = raw_types.InputDocument(
            id=file_id.media_id,
            access_hash=file_id.access_hash,
            file_reference=file_id.file_reference,
        )
        item = raw_types.InputStickerSetItem(
            document=document, emoji=emoji or random.choice(EMOJIS)
        )

        if create_new:
            query = functions.stickers.CreateStickerSet(
                user_id=await client.resolve_peer(peer_id=user.id),
                short_name=short_name,
                title=title,
                stickers=[item],
            )
        else:
            query = functions.stickers.AddStickerToSet(
                stickerset=raw_types.InputStickerSetID(
                    id=sticker_set.id, access_hash=sticker_set.access_hash
                ),
                sticker=item,
            )

        return await client.invoke(query)

    MEDIA_TYPE_MAP = {
        MessageMediaType.PHOTO: _photo_kang,
        MessageMediaType.VIDEO: _video_kang,
        MessageMediaType.ANIMATION: _video_kang,
        MessageMediaType.DOCUMENT: _document_kang,
        MessageMediaType.STICKER: _sticker_kang,
    }
