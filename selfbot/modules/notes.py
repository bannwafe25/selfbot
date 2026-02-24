import contextlib
import datetime
import html
import re

from pyrogram import filters
from pyrogram.errors import ChatForwardsRestricted
from pyrogram.types import Message, ReplyParameters

from selfbot.listener import handler
from selfbot.module import Module

DISPATCH_PATTERN = re.compile(
    r"^(?:save|note|notes|clear)(?:\s+[\s\S]+)?$",
    re.IGNORECASE,
)
SAVE_PATTERN = re.compile(r"^save(?:\s+(\S+))(?:\s+([\s\S]+))?$", re.IGNORECASE)
NOTE_PATTERN = re.compile(r"^note(?:\s+(\S+))?$", re.IGNORECASE)
NOTES_PATTERN = re.compile(r"^notes$", re.IGNORECASE)
CLEAR_PATTERN = re.compile(r"^clear(?:\s+(\S+))?$", re.IGNORECASE)


class Notes(Module):
    name = "Notes"
    cmds = "{save|note|notes|clear} ..."
    desc = {
        "save": "Save a note from replied message or inline text.",
        "note": "Send a saved note by name.",
        "notes": "List all saved notes.",
        "clear": "Delete a saved note.",
        "e.g.": "save greeting Hello World",
    }

    async def on_starting(self) -> None:
        try:
            await self.client.db.notes_items.create_index([("name", 1)], unique=True)
        except Exception:
            pass

    @handler(filters.regex(DISPATCH_PATTERN), 1)
    async def on_message_out(self, event: Message) -> None:
        text = str(event.content).strip()
        if SAVE_PATTERN.match(text):
            await self._cmd_save(event, text)
            return
        if NOTE_PATTERN.match(text):
            await self._cmd_note(event, text)
            return
        if NOTES_PATTERN.match(text):
            await self._cmd_notes(event)
            return
        if CLEAR_PATTERN.match(text):
            await self._cmd_clear(event, text)

    async def _cmd_save(self, event: Message, text: str) -> None:
        await self.respond(event, "<code>Saving note...</code>")
        now = datetime.datetime.now(datetime.UTC)

        match = SAVE_PATTERN.match(text)
        name_raw, inline_text = match.groups()
        if not name_raw:
            await self.respond(event, "<code>Usage: save {name} [text] or reply to a message.</code>")
            return

        name = self._normalize_name(name_raw)
        if not name:
            await self.respond(event, "<code>Invalid note name.</code>")
            return

        exists = await self.client.db.notes_items.find_one({"name": name})
        if exists:
            await self.respond(event, f"<code>Note '{html.escape(name)}' already exists.</code>")
            return

        storage_chat_id = await self._ensure_storage_chat(event._client)
        if not storage_chat_id:
            await self.respond(event, "<code>Unable to prepare notes storage chat.</code>")
            return

        try:
            if event.reply_to_message:
                msg_ids, media_group = await self._store_from_reply(
                    event._client,
                    storage_chat_id,
                    event.chat.id,
                    event.reply_to_message,
                )
                if not msg_ids:
                    await self.respond(event, "<code>Failed to store replied message.</code>")
                    return
            else:
                if not inline_text or not inline_text.strip():
                    await self.respond(
                        event, "<code>Usage: save {name} [text] or reply to a message.</code>"
                    )
                    return
                sent = await event._client.send_message(storage_chat_id, inline_text.strip())
                msg_ids = [sent.id]
                media_group = False

            await self.client.db.notes_items.insert_one(
                {
                    "name": name,
                    "display_name": name_raw.strip(),
                    "storage_chat_id": int(storage_chat_id),
                    "message_ids": msg_ids,
                    "media_group": bool(media_group),
                    "created_at": datetime.datetime.now(datetime.UTC),
                }
            )
        except Exception as e:
            await self.respond(
                event,
                f"<b>Save failed</b>\n\n<code>{html.escape(str(e)[:300])}</code>",
            )
            return

        await self.respond(
            event,
            self.fmtmsg(
                "Notes",
                {
                    "Name": name,
                    "Type": "Media Group" if media_group else "Message",
                },
                self.fmtsec(now),
            ),
        )

    async def _cmd_note(self, event: Message, text: str) -> None:
        await self.respond(event, "<code>Loading note...</code>")
        now = datetime.datetime.now(datetime.UTC)

        match = NOTE_PATTERN.match(text)
        name_raw = (match.group(1) or "").strip()
        if not name_raw:
            await self.respond(event, "<code>Usage: note {name}</code>")
            return

        name = self._normalize_name(name_raw)
        note = await self.client.db.notes_items.find_one({"name": name})
        if not note:
            await self.respond(event, f"<code>Note '{html.escape(name)}' not found.</code>")
            return

        storage_chat_id = int(note.get("storage_chat_id") or 0)
        msg_ids = [int(i) for i in note.get("message_ids") or [] if str(i).lstrip("-").isdigit()]
        if not storage_chat_id or not msg_ids:
            await self.respond(
                event, "<code>Note data is invalid. Re-save this note.</code>"
            )
            return

        reply_params = ReplyParameters(message_id=event.reply_to_message_id or event.id)
        try:
            if len(msg_ids) == 1:
                await event._client.copy_message(
                    chat_id=event.chat.id,
                    from_chat_id=storage_chat_id,
                    message_id=msg_ids[0],
                    reply_parameters=reply_params,
                )
            else:
                try:
                    await event._client.forward_messages(
                        chat_id=event.chat.id,
                        from_chat_id=storage_chat_id,
                        message_ids=msg_ids,
                    )
                except Exception:
                    for msg_id in msg_ids:
                        with contextlib.suppress(Exception):
                            await event._client.copy_message(
                                chat_id=event.chat.id,
                                from_chat_id=storage_chat_id,
                                message_id=msg_id,
                                reply_parameters=reply_params,
                            )
        except Exception as e:
            await self.respond(
                event,
                self.fmtmsg("Notes", f"Failed to send note: {e}", self.fmtsec(now)),
            )
            return

        await event.delete()

    async def _cmd_notes(self, event: Message) -> None:
        await self.respond(event, "<code>Loading notes...</code>")
        now = datetime.datetime.now(datetime.UTC)

        names_set = set()
        cursor = self.client.db.notes_items.find(
            {},
            {"_id": 0, "name": 1, "display_name": 1},
        )
        async for row in cursor:
            key = str(row.get("name") or "").strip()
            if not key:
                continue
            shown = str(row.get("display_name") or key).strip()
            if shown:
                names_set.add(shown)

        names = sorted(names_set, key=lambda x: x.casefold())
        if not names:
            await self.respond(event, "<code>No notes saved yet.</code>")
            return

        await self.respond(
            event,
            self.fmtmsg("Available Notes", names, self.fmtsec(now)),
        )

    async def _cmd_clear(self, event: Message, text: str) -> None:
        await self.respond(event, "<code>Deleting note...</code>")
        now = datetime.datetime.now(datetime.UTC)

        match = CLEAR_PATTERN.match(text)
        name_raw = (match.group(1) or "").strip()
        if not name_raw:
            await self.respond(event, "<code>Usage: clear {name}</code>")
            return

        name = self._normalize_name(name_raw)
        res = await self.client.db.notes_items.delete_one({"name": name})
        if not res.deleted_count:
            await self.respond(event, f"<code>Note '{html.escape(name)}' not found.</code>")
            return

        await self.respond(
            event,
            self.fmtmsg("Notes", {"Deleted": name}, self.fmtsec(now)),
        )

    async def _ensure_storage_chat(self, client) -> int | None:
        meta = await self.client.db.notes_meta.find_one({"_id": "meta"})
        if meta and meta.get("chat_id"):
            chat_id = int(meta["chat_id"])
            try:
                await client.get_chat(chat_id)
                return chat_id
            except Exception:
                pass

        try:
            chat = await client.create_supergroup(
                "Selfbot_Notes_Storage",
                "Internal storage for selfbot notes. Do not remove messages here.",
            )
            chat_id = int(chat.id)
        except Exception:
            # fallback to Saved Messages
            me = await client.get_me()
            chat_id = int(me.id)

        await self.client.db.notes_meta.update_one(
            {"_id": "meta"},
            {
                "$set": {
                    "chat_id": chat_id,
                    "updated_at": datetime.datetime.now(datetime.UTC),
                }
            },
            upsert=True,
        )
        return chat_id

    async def _store_from_reply(
        self,
        client,
        storage_chat_id: int,
        source_chat_id: int,
        replied: Message,
    ) -> tuple[list[int], bool]:
        if replied.media_group_id:
            group = await client.get_media_group(source_chat_id, replied.id)
            ids = [msg.id for msg in group if msg]
            if not ids:
                return [], True

            try:
                sent = await client.forward_messages(storage_chat_id, source_chat_id, ids)
                msg_ids = [msg.id for msg in sent if msg]
                return msg_ids, True
            except ChatForwardsRestricted:
                pass

            copied_ids = []
            for msg_id in ids:
                try:
                    copied = await client.copy_message(
                        chat_id=storage_chat_id,
                        from_chat_id=source_chat_id,
                        message_id=msg_id,
                    )
                    copied_ids.append(copied.id)
                except Exception:
                    continue
            return copied_ids, True

        try:
            sent = await replied.forward(storage_chat_id)
            return [sent.id], False
        except ChatForwardsRestricted:
            pass

        copied = await client.copy_message(
            chat_id=storage_chat_id,
            from_chat_id=source_chat_id,
            message_id=replied.id,
        )
        return [copied.id], False

    @staticmethod
    def _normalize_name(name: str) -> str:
        normalized = name.strip().lower()
        if not normalized:
            return ""
        normalized = re.sub(r"[^a-zA-Z0-9_\-\.]", "", normalized)
        return normalized[:64]
