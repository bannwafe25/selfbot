import asyncio
import contextlib
import datetime
import html
import re

from pyrogram import filters
from pyrogram.errors import RPCError, UserIsBlocked
from pyrogram.types import Message

from selfbot.listener import handler
from selfbot.module import Module
from selfbot.apis import SANGMATA_USERNAME

pattern = re.compile(r"^sgb(?:\s+(.+))?$", re.IGNORECASE)



class SGB(Module):
    name = "SangMata"
    cmds = "sgb {user_id|username}?"
    desc = {
        "Info": "Get user history info from @SangMata_beta_bot.",
        "?": "Optional (reply to user message or provide target).",
        "e.g.": "sgb @username",
    }

    @handler(filters.regex(pattern), 1)
    async def on_message_out(self, event: Message) -> None:
        await self.respond(event, "<code>Processing...</code>")
        now = datetime.datetime.now(datetime.UTC)
        target = self._extract_target(event)
        if target is None:
            await self.respond(
                event,
                "<code>Usage: sgb {user_id|username} or reply to a user's message.</code>",
            )
            return

        try:
            result = await self._ask_sangmata(event._client, target, timeout=15)
            if not result:
                await self.respond(
                    event, "<code>No response from @SangMata_beta_bot (timeout).</code>"
                )
                return

            if "you have used up your quota" in result.lower():
                result = result.splitlines()[0]

            safe = html.escape(result.strip())
            if len(safe) > 3600:
                safe = safe[:3600] + "..."

            await self.respond(
                event,
                (
                    "<b>SangMata Result</b>\n\n"
                    f"<blockquote expandable>{safe}</blockquote>\n\n"
                    f"<b><blockquote>{self.fmtsec(now)}</blockquote></b>"
                ),
            )
        except UserIsBlocked:
            await self.respond(
                event,
                "<code>Please unblock @SangMata_beta_bot first.</code>",
            )
        except RPCError as e:
            await self.respond(event, f"<code>{html.escape(str(e)[:300])}</code>")
        except Exception as e:
            await self.respond(
                event,
                f"<b>SGB failed</b>\n\n<code>{html.escape(str(e)[:300])}</code>",
            )

    def _extract_target(self, event: Message) -> int | str | None:
        args = (pattern.match(str(event.content).strip()).group(1) or "").strip()
        if args:
            token = args.split()[0].strip()
            if token.lstrip("-").isdigit():
                return int(token)
            return token

        replied = event.reply_to_message
        if replied and replied.from_user:
            return replied.from_user.id
        return None

    async def _ask_sangmata(
        self,
        client,
        target: int | str,
        timeout: int = 15,
    ) -> str | None:
        bot = await client.get_users(SANGMATA_USERNAME)
        bot_id = bot.id
        started_at = datetime.datetime.now(datetime.UTC)

        sent = await client.send_message(bot_id, str(target))
        with contextlib.suppress(Exception):
            await sent.delete()

        deadline = started_at + datetime.timedelta(seconds=timeout)
        seen_ids = set()
        while datetime.datetime.now(datetime.UTC) < deadline:
            async for msg in client.get_chat_history(bot_id, limit=10):
                if not msg or msg.id in seen_ids:
                    continue
                seen_ids.add(msg.id)

                if not msg.from_user or msg.from_user.id != bot_id:
                    continue

                msg_dt = msg.date
                if msg_dt and msg_dt.tzinfo is None:
                    msg_dt = msg_dt.replace(tzinfo=datetime.UTC)
                if msg_dt and msg_dt < started_at:
                    continue

                text = self.message_text(msg)
                if text:
                    return text

            await asyncio.sleep(0.8)

        return None
