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

            # Deteksi pesan error dari SangMata bot sendiri
            low = result.lower()
            if "tidak valid" in low or "not valid" in low or "invalid" in low:
                await self.respond(
                    event,
                    "<b>SangMata</b>\n<code>Target tidak valid. Reply pesan user atau ketik: sgb @username</code>",
                )
                return

            safe = html.escape(result.strip())
            if len(safe) > 3600:
                safe = safe[:3600] + "..."

            # Format ala SangMata: kartu teks terstruktur (list), bukan tabel k/v
            import asyncio as _aio
            import contextlib as _cl
            import richpyro as rp
            from pyrogram.raw import functions as rawfn
            from pyrogram.raw.types import (
                InputBotInlineMessageRichMessage,
                InputBotInlineResult,
            )

            lines = [ln.strip() for ln in result.strip().splitlines() if ln.strip()]
            blocks = [
                rp.heading(rp.bold("🔍 History"), size=2),
                rp.divider(),
            ]
            for ln in lines[:40]:
                blocks.append(rp.para(rp.italic(ln)))
            blocks.append(rp.divider())
            blocks.append(rp.para(rp.bold(f"🕒 {self.fmtsec(now)}")))
            blocks.append(rp.buttons(rp.btn(rp.bold("🗑 Close"), callback_data=b"0", style=rp.Style.DANGER)))

            try:
                bot = self.client.bot
                rich_raw = await rp.blocks_message(*blocks).write(client=bot)
                ping_mod = self.client.modules.get("Ping")
                route = getattr(ping_mod, "_rich_route", None)
                if route is None and ping_mod is not None:
                    self._ensure_rich_handler(ping_mod, rawfn, InputBotInlineMessageRichMessage, InputBotInlineResult)
                    route = getattr(ping_mod, "_rich_route", None)
                if route is not None:
                    route["sgb"] = (rich_raw, None)
                    res = await event._client.get_inline_bot_results(
                        bot.me.id, f"sgb{now.timestamp()}"
                    )
                    if res.results:
                        await _aio.gather(
                            event.reply_inline_bot_result(res.query_id, res.results[0].id),
                            event.delete(),
                        )
                        return
            except Exception as e:
                with _cl.suppress(Exception):
                    self.logger.warning(f"sgb rich failed, fallback html: {e!r}")

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
