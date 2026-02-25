import contextlib
import datetime
import html
import re

from pyrogram import filters
from pyrogram.types import (
    CallbackQuery,
    InlineQuery,
    InlineQueryResultPhoto,
    InputMediaPhoto,
    Message,
    ReplyParameters,
)

from selfbot.listener import handler, reply
from selfbot.module import Module
from selfbot.apis import DELINE_PPCOUPLE

pattern = re.compile(r"^ppcouple$", re.IGNORECASE)
cb_pattern = re.compile(r"^ppcouple/next$")


class PPCouple(Module):
    name = "PP Couple"
    cmds = "ppcouple"
    desc = {
        "Info": "Get random couple profile pictures (cowo & cewe).",
        "e.g.": "ppcouple",
    }

    async def _fetch_couple(self) -> tuple[str, str] | None:
        try:
            resp = await self.client.http.get(DELINE_PPCOUPLE, timeout=15)
            if resp.status_code != 200:
                return None
            data = resp.json()
            if not data.get("status"):
                return None
            result = data.get("result") or {}
            cowo = result.get("cowo", "")
            cewe = result.get("cewe", "")
            if cowo and cewe:
                return cowo, cewe
        except Exception:
            pass
        return None

    @handler(filters.regex(pattern) & ~reply, 1)
    async def on_message_out(self, event: Message) -> None:
        await self.respond(event, "<code>...</code>")
        now = datetime.datetime.now(datetime.UTC)

        couple = await self._fetch_couple()
        if not couple:
            await self.respond(event, "<code>Failed to fetch PP Couple.</code>")
            return

        caption = (
            f"<b>PP Couple</b>\n\n"
            f"<b><blockquote>{self.fmtsec(now)}</blockquote></b>"
        )
        await event._client.send_media_group(
            chat_id=event.chat.id,
            media=[
                InputMediaPhoto(media=couple[0], caption="👦 Cowo"),
                InputMediaPhoto(media=couple[1], caption=f"👧 Cewe\n\n{caption}"),
            ],
            reply_to_message_id=event.reply_to_message_id or event.id,
        )
        with contextlib.suppress(Exception):
            await event.delete()

    @handler(filters.regex(pattern), 2)
    async def on_inline_query(self, event: InlineQuery) -> None:
        try:
            now = datetime.datetime.now(datetime.UTC)
            couple = await self._fetch_couple()
            if not couple:
                await event.answer([], cache_time=0)
                return

            caption = (
                f"<b>PP Couple</b>\n\n"
                f"<b><blockquote>{self.fmtsec(now)}</blockquote></b>"
            )
            kb = self.ikm([
                [("🔄 Refresh", "data", b"ppcouple/next"),
                 ("Close", "data", b"0")],
            ])

            results = [
                InlineQueryResultPhoto(
                    photo_url=couple[0],
                    caption=f"👦 <b>Cowo</b>\n\n{caption}",
                    reply_markup=kb,
                ),
                InlineQueryResultPhoto(
                    photo_url=couple[1],
                    caption=f"👧 <b>Cewe</b>\n\n{caption}",
                    reply_markup=kb,
                ),
            ]
            await event.answer(results, cache_time=0)
        except Exception:
            await event.answer([], cache_time=0)

    @handler(filters.regex(cb_pattern), 4)
    async def on_inline_callback(self, event: CallbackQuery) -> None:
        try:
            await event.answer("Refreshing...")
            now = datetime.datetime.now(datetime.UTC)
            couple = await self._fetch_couple()
            if not couple:
                await event.answer("Failed to get new images.", show_alert=True)
                return

            caption = (
                f"<b>PP Couple</b>\n\n"
                f"<b><blockquote>{self.fmtsec(now)}</blockquote></b>"
            )
            kb = self.ikm([
                [("🔄 Refresh", "data", b"ppcouple/next"),
                 ("Close", "data", b"0")],
            ])

            # Determine if this is cowo or cewe based on current caption
            current = str(getattr(event.message, "caption", "") or "")
            if "Cewe" in current:
                new_url = couple[1]
                label = "👧 <b>Cewe</b>"
            else:
                new_url = couple[0]
                label = "👦 <b>Cowo</b>"

            await event.edit_message_media(
                media=InputMediaPhoto(
                    media=new_url,
                    caption=f"{label}\n\n{caption}",
                ),
                reply_markup=kb,
            )
        except Exception as e:
            await event.answer(f"Error: {html.escape(str(e)[:100])}", show_alert=True)
