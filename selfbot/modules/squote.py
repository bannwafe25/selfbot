import base64
import contextlib
import datetime
import html
import re
from io import BytesIO

from PIL import Image
from pyrogram import filters
from pyrogram.types import Message, ReplyParameters, User

from selfbot.listener import handler, reply
from selfbot.module import Module

QUOTE_PATTERN = re.compile(r"^(squote|sq)(?:\s+([\s\S]+))?$", re.IGNORECASE)
FAKE_PATTERN = re.compile(r"^(fakequote|fq)(?:\s+([\s\S]+))?$", re.IGNORECASE)
DISPATCH_PATTERN = re.compile(r"^(?:squote|sq|fakequote|fq)(?:\s+[\s\S]+)?$", re.IGNORECASE)
QUOTES_API = "https://quotes-o042.onrender.com/generate"


class Squote(Module):
    name = "Squote"
    cmds = "{squote|sq|fakequote|fq} ..."
    desc = {
        "squote|sq": "Generate quote from replied message(s).",
        "fakequote|fq": "Generate quote using custom text on replied sender.",
        "flags": "!png !me !noreply {count}",
        "e.g.": "sq 3 !png",
    }

    async def on_starting(self) -> None:
        self.files_cache = {}

    @handler(filters.regex(DISPATCH_PATTERN) & reply, 1)
    async def on_message_out(self, event: Message) -> None:
        text = str(event.content).strip()
        if FAKE_PATTERN.match(text):
            await self._handle_fake_quote(event, text)
            return

        await self._handle_quote(event, text)

    async def _handle_quote(self, event: Message, text: str) -> None:
        await self.respond(event, "<code>Collecting messages...</code>")
        now = datetime.datetime.now(datetime.UTC)

        _, raw_args = QUOTE_PATTERN.match(text).groups()
        count, as_png, send_for_me, no_reply = self._parse_quote_args(raw_args or "")
        messages = await self._collect_messages(event, count)
        if not messages:
            await self.respond(event, "<code>No valid messages found to quote.</code>")
            return

        progress = event
        if send_for_me:
            await event.delete()
            progress = await event._client.send_message("me", "<code>Generating...</code>")
        else:
            await self.respond(event, "<code>Generating...</code>")

        try:
            payload_messages = []
            for msg in messages:
                rendered = await self._render_message(event._client, msg, no_reply=no_reply)
                if rendered:
                    payload_messages.append(rendered)

            if not payload_messages:
                await self.respond(progress, "<code>No supported content to quote.</code>")
                return

            image = await self._generate_quote(payload_messages, as_png=as_png)
            await self.respond(progress, "<code>Sending...</code>")
            await self._send_result(
                event,
                progress,
                image=image,
                as_png=as_png,
                send_for_me=send_for_me,
                foot=self.fmtsec(now),
            )
        except Exception as e:
            await self.respond(
                progress,
                f"<b>Squote failed</b>\n\n<code>{html.escape(str(e)[:300])}</code>",
            )

    async def _handle_fake_quote(self, event: Message, text: str) -> None:
        await self.respond(event, "<code>Processing...</code>")
        now = datetime.datetime.now(datetime.UTC)

        _, raw_args = FAKE_PATTERN.match(text).groups()
        text, as_png, send_for_me, no_reply = self._parse_fake_args(raw_args or "")
        if not text:
            await self.respond(
                event,
                "<code>Fake quote text is empty. Example: fq hello world !png</code>",
            )
            return

        replied = event.reply_to_message
        if not replied:
            await self.respond(event, "<code>Reply to a message first.</code>")
            return

        progress = event
        if send_for_me:
            await event.delete()
            progress = await event._client.send_message("me", "<code>Generating...</code>")
        else:
            await self.respond(event, "<code>Generating...</code>")

        try:
            rendered = await self._render_message(
                event._client, replied, no_reply=no_reply, override_text=text
            )
            if not rendered:
                await self.respond(progress, "<code>No supported content to quote.</code>")
                return

            image = await self._generate_quote([rendered], as_png=as_png)
            await self.respond(progress, "<code>Sending...</code>")
            await self._send_result(
                event,
                progress,
                image=image,
                as_png=as_png,
                send_for_me=send_for_me,
                foot=self.fmtsec(now),
            )
        except Exception as e:
            await self.respond(
                progress,
                f"<b>Fakequote failed</b>\n\n<code>{html.escape(str(e)[:300])}</code>",
            )

    async def _send_result(
        self,
        event: Message,
        progress: Message,
        image: BytesIO,
        as_png: bool,
        send_for_me: bool,
        foot: str,
    ) -> None:
        chat_id = "me" if send_for_me else event.chat.id
        reply_params = None
        if not send_for_me:
            reply_params = ReplyParameters(message_id=event.reply_to_message_id or event.id)

        if as_png:
            await event._client.send_document(
                chat_id=chat_id,
                document=image,
                caption=f"<b><blockquote>{foot}</blockquote></b>",
                reply_parameters=reply_params,
            )
        else:
            try:
                await event._client.send_sticker(
                    chat_id=chat_id,
                    sticker=image,
                    reply_parameters=reply_params,
                )
            except Exception:
                image.seek(0)
                image.name = "squote.webp"
                await event._client.send_document(
                    chat_id=chat_id,
                    document=image,
                    caption=f"<b><blockquote>{foot}</blockquote></b>",
                    reply_parameters=reply_params,
                )

        with contextlib.suppress(Exception):
            await progress.delete()

    async def _generate_quote(self, messages: list[dict], as_png: bool) -> BytesIO:
        payload = {
            "messages": messages,
            "quote_color": "#162330",
            "text_color": "#fff",
        }
        resp = await self.client.http.post(QUOTES_API, json=payload, timeout=45)
        if resp.status_code != 200:
            raise RuntimeError(f"Quotes API error: HTTP {resp.status_code}")

        if as_png:
            img = Image.open(BytesIO(resp.content)).convert("RGBA")
            data = BytesIO()
            data.name = "squote.png"
            img.save(data, format="PNG")
            data.seek(0)
            return data

        data = BytesIO(resp.content)
        data.name = "squote.webp"
        data.seek(0)
        return data

    async def _collect_messages(self, event: Message, count: int) -> list[Message]:
        replied = event.reply_to_message
        if not replied:
            return []

        if count <= 1:
            return [replied]

        start_id = max(1, replied.id - count + 1)
        ids = list(range(start_id, replied.id + 1))
        items = await event._client.get_messages(event.chat.id, ids)
        return [msg for msg in items if msg and not msg.empty]

    async def _render_message(
        self,
        app,
        message: Message,
        *,
        no_reply: bool,
        override_text: str | None = None,
    ) -> dict | None:
        text = override_text if override_text is not None else self._get_text(message)
        entities = [] if override_text is not None else self._extract_entities(message, text)
        media = await self._extract_media_base64(app, message)
        author = await self._build_author(app, message)
        reply_data = {}
        if not no_reply and message.reply_to_message and not message.reply_to_message.empty:
            rep = message.reply_to_message
            if rep.from_user:
                reply_data["id"] = rep.from_user.id
                reply_data["name"] = self._full_name(rep.from_user)
            elif rep.sender_chat:
                reply_data["id"] = rep.sender_chat.id
                reply_data["name"] = rep.sender_chat.title
            else:
                reply_data["id"] = 0
                reply_data["name"] = "Unknown"
            reply_data["text"] = self._get_text(rep)

        return {
            "text": text,
            "media": media,
            "entities": entities,
            "author": author,
            "reply": reply_data,
        }

    def _extract_entities(self, message: Message, text: str) -> list[dict]:
        if not text:
            return []

        if message.photo:
            source = message.caption_entities or []
        else:
            source = message.entities or []

        entities = []
        for entity in source:
            entities.append(
                {
                    "offset": entity.offset,
                    "length": entity.length,
                    "type": str(entity.type).split(".")[-1].lower(),
                }
            )
        return entities

    async def _extract_media_base64(self, app, message: Message) -> str:
        file_id = None
        if message.photo:
            file_id = message.photo.file_id
        elif message.sticker and not (message.sticker.is_animated or message.sticker.is_video):
            file_id = message.sticker.file_id

        if not file_id:
            return ""

        if file_id in self.files_cache:
            return self.files_cache[file_id]

        data = await app.download_media(file_id, in_memory=True)
        if not data:
            return ""
        if hasattr(data, "getbuffer"):
            raw = bytes(data.getbuffer())
        elif hasattr(data, "read"):
            raw = data.read()
        else:
            raw = bytes(data)

        encoded = base64.b64encode(raw).decode()
        self.files_cache[file_id] = encoded
        return encoded

    async def _build_author(self, app, message: Message) -> dict:
        origin = getattr(message, "forward_origin", None)
        if origin:
            sender_user = getattr(origin, "sender_user", None)
            if sender_user:
                return await self._author_from_user(app, sender_user, via=message.via_bot)

            sender_chat = getattr(origin, "sender_chat", None)
            if sender_chat:
                return await self._author_from_chat(app, sender_chat, via=message.via_bot)

            name = (
                getattr(origin, "sender_name", None)
                or getattr(origin, "hidden_user_name", None)
                or "Hidden User"
            )
            return {
                "id": 0,
                "name": name,
                "rank": "",
                "avatar": "",
                "via_bot": message.via_bot.username if message.via_bot else "",
            }

        if message.from_user:
            return await self._author_from_user(app, message.from_user, via=message.via_bot)
        if message.sender_chat:
            return await self._author_from_chat(app, message.sender_chat, via=message.via_bot)
        return {
            "id": 0,
            "name": "Unknown",
            "rank": "",
            "avatar": "",
            "via_bot": message.via_bot.username if message.via_bot else "",
        }

    async def _author_from_user(self, app, user: User, via=None) -> dict:
        avatar = ""
        if getattr(user, "photo", None):
            big_file_id = getattr(user.photo, "big_file_id", None)
            if big_file_id:
                with contextlib.suppress(Exception):
                    avatar = await self._file_to_base64(app, big_file_id)

        return {
            "id": user.id,
            "name": self._full_name(user),
            "rank": "",
            "avatar": avatar,
            "via_bot": via.username if via else "",
        }

    async def _author_from_chat(self, app, chat, via=None) -> dict:
        avatar = ""
        photo = getattr(chat, "photo", None)
        if photo:
            big_file_id = getattr(photo, "big_file_id", None)
            if big_file_id:
                with contextlib.suppress(Exception):
                    avatar = await self._file_to_base64(app, big_file_id)

        chat_type = getattr(chat, "type", None)
        rank = "channel" if str(chat_type).split(".")[-1].lower() == "channel" else ""
        return {
            "id": chat.id,
            "name": getattr(chat, "title", "Channel"),
            "rank": rank,
            "avatar": avatar,
            "via_bot": via.username if via else "",
        }

    async def _file_to_base64(self, app, file_id: str) -> str:
        if file_id in self.files_cache:
            return self.files_cache[file_id]
        data = await app.download_media(file_id, in_memory=True)
        if hasattr(data, "getbuffer"):
            raw = bytes(data.getbuffer())
        elif hasattr(data, "read"):
            raw = data.read()
        else:
            raw = bytes(data)
        encoded = base64.b64encode(raw).decode()
        self.files_cache[file_id] = encoded
        return encoded

    def _get_text(self, message: Message) -> str:
        if message.photo:
            return message.caption or "📷 Photo"
        if message.poll:
            return self._poll_text(message.poll)
        if message.sticker:
            return "Sticker"
        if message.voice:
            return "🎵 Voice"
        if message.audio:
            return "🎧 Music"
        if message.video:
            return "📹 Video"
        if message.video_note:
            return "📹 Videomessage"
        if message.animation:
            return "🖼 GIF"
        if message.document:
            name = getattr(message.document, "file_name", None) or "File"
            return f"💾 File {name}"
        if message.contact:
            return "👤 Contact"
        if message.location or message.venue:
            return "📍 Location"
        if message.game:
            return "🎮 Game"
        if message.dice:
            return f"{message.dice.emoji} - {message.dice.value}"
        if message.new_chat_members:
            return "👤 joined the group"
        if message.left_chat_member:
            return "👤 left the group"
        if message.new_chat_title:
            return f"✏ changed group name to {message.new_chat_title}"
        if message.new_chat_photo:
            return "🖼 changed group photo"
        if message.delete_chat_photo:
            return "🖼 removed group photo"
        if message.pinned_message:
            return "📍 pinned message"
        if message.video_chat_started:
            return "🎤 started a new video chat"
        if message.video_chat_ended:
            return "🎤 ended the video chat"
        if message.video_chat_members_invited:
            return "🎤 invited participants to the video chat"
        if message.group_chat_created or message.supergroup_chat_created:
            return "👥 created the group"
        if message.channel_chat_created:
            return "👥 created the channel"
        return message.text or message.caption or "unsupported message"

    @staticmethod
    def _poll_text(poll) -> str:
        mode = "Poll" if poll.type == "regular" else "Quiz"
        anon = "Anonymous " if poll.is_anonymous else ""
        status = " (closed)" if poll.is_closed else ""
        lines = [f"📊 {anon}{mode}{status}", poll.question]
        for option in poll.options:
            voted = f" ({option.voter_count} voted)" if option.voter_count else ""
            lines.append(f"- {option.text}{voted}")
        lines.append(f"Total: {poll.total_voter_count} voted")
        return "\n".join(lines)

    @staticmethod
    def _full_name(user: User) -> str:
        if user.last_name:
            return f"{user.first_name} {user.last_name}"
        return user.first_name or "User"

    @staticmethod
    def _parse_quote_args(raw: str) -> tuple[int, bool, bool, bool]:
        count = 1
        as_png = False
        send_for_me = False
        no_reply = False
        for token in raw.split():
            low = token.lower()
            if low.isdigit():
                count = max(1, min(int(low), 15))
            elif low in {"!png", "!file"}:
                as_png = True
            elif low in {"!me", "!ls"}:
                send_for_me = True
            elif low in {"!noreply", "!nr"}:
                no_reply = True
        return count, as_png, send_for_me, no_reply

    @staticmethod
    def _parse_fake_args(raw: str) -> tuple[str, bool, bool, bool]:
        as_png = False
        send_for_me = False
        no_reply = False
        words = []
        for token in raw.split():
            low = token.lower()
            if low in {"!png", "!file"}:
                as_png = True
            elif low in {"!me", "!ls"}:
                send_for_me = True
            elif low in {"!noreply", "!nr"}:
                no_reply = True
            else:
                words.append(token)
        return " ".join(words).strip(), as_png, send_for_me, no_reply
