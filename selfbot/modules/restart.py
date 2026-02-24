import asyncio
import html
import os
import re
import sys

from pyrogram import filters
from pyrogram.types import Message

from selfbot.listener import handler, reply
from selfbot.module import Module

restart_pattern = re.compile(r"^r(?:estart)?$")
update_pattern = re.compile(r"^update$", re.IGNORECASE)
dispatch_pattern = re.compile(r"^(?:r(?:estart)?|update)$", re.IGNORECASE)


class Restart(Module):
    name = "Restart System"
    cmds = "r(estart)? | update"
    desc = {
        "restart": "Restart the selfbot.",
        "update": "Pull latest changes from GitHub and restart.",
        "e.g.": "update",
    }

    @handler(filters.regex(dispatch_pattern) & ~reply, 1)
    async def on_message_out(self, event: Message) -> None:
        text = str(event.content or "").strip().lower()

        if update_pattern.match(text):
            await self._do_update(event)
        else:
            await self._do_restart(event)

    async def _do_restart(self, event: Message) -> None:
        await asyncio.gather(
            self.respond(event, "<code>Restarting...</code>"),
            self.client.db.restart_msgs.update_one(
                {"name": "app"},
                {"$set": {"chat_id": event.chat.id, "message_id": event.id}},
                upsert=True,
            ),
        )
        os.execv(sys.argv[0], sys.argv)

    async def _do_update(self, event: Message) -> None:
        await self.respond(event, "<code>Checking for updates...</code>")

        try:
            # Get current commit hash before pull
            old_hash = await self._run_git("rev-parse", "--short", "HEAD")

            # Git pull
            pull_output = await self._run_git("pull", "--rebase")

            if "Already up to date" in pull_output:
                await self.respond(
                    event,
                    "<b>Update</b>\n\n<code>Already up to date.</code>",
                )
                return

            # Get new commit hash
            new_hash = await self._run_git("rev-parse", "--short", "HEAD")

            # Get commit log between old and new
            log_output = await self._run_git(
                "log", f"{old_hash}..{new_hash}",
                "--oneline", "--no-decorate",
            )

            lines = log_output.strip().splitlines()
            commits = "\n".join(
                f"  • <code>{html.escape(line)}</code>" for line in lines[:15]
            )
            if len(lines) > 15:
                commits += f"\n  ... and {len(lines) - 15} more"

            msg = (
                f"<b>Update</b>\n\n"
                f"<blockquote>{commits}</blockquote>\n\n"
                f"<code>Restarting...</code>"
            )

            await asyncio.gather(
                self.respond(event, msg),
                self.client.db.restart_msgs.update_one(
                    {"name": "app"},
                    {"$set": {"chat_id": event.chat.id, "message_id": event.id}},
                    upsert=True,
                ),
            )
            os.execv(sys.argv[0], sys.argv)

        except Exception as e:
            await self.respond(
                event,
                f"<b>Update failed</b>\n\n<code>{html.escape(str(e)[:300])}</code>",
            )

    @staticmethod
    async def _run_git(*args: str) -> str:
        proc = await asyncio.create_subprocess_exec(
            "git", *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            err = (stderr or stdout or b"").decode("utf-8", errors="ignore").strip()
            raise RuntimeError(f"git {args[0]} failed: {err}")
        return (stdout or b"").decode("utf-8", errors="ignore").strip()
