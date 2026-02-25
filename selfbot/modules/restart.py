import asyncio
import datetime
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
    cmds = "update | r(estart)?"
    desc = {
        "Info": "Pull latest changes from GitHub and restart the selfbot.",
        "e.g.": "restart",
    }

    @handler(filters.regex(dispatch_pattern) & ~reply, 1)
    async def on_message_out(self, event: Message) -> None:
        await self._do_update(event)

    async def _do_update(self, event: Message) -> None:
        await self.respond(event, "<code>Checking for updates...</code>")
        started_at = datetime.datetime.now(datetime.UTC)

        try:
            branch = await self._run_git("rev-parse", "--abbrev-ref", "HEAD")
            worktree_state = "Dirty" if await self._run_git("status", "--porcelain") else "Clean"

            # Get current commit hash before pull
            old_hash = await self._run_git("rev-parse", "--short", "HEAD")

            # Git pull (autostash handles unstaged changes)
            pull_output = await self._run_git("pull", "--rebase", "--autostash")
            pull_lower = pull_output.lower()

            # Get new commit hash
            new_hash = await self._run_git("rev-parse", "--short", "HEAD")

            if (
                "already up to date" in pull_lower
                or "already up-to-date" in pull_lower
                or old_hash == new_hash
            ):
                msg = self._build_uptodate_message(
                    branch=branch,
                    commit_hash=new_hash,
                    worktree_state=worktree_state,
                    pull_output=pull_output,
                    elapsed=self.fmtsec(started_at),
                )
                await self.respond(
                    event,
                    msg,
                )
                return

            # Get commit log between old and new
            log_output = await self._run_git(
                "log", f"{old_hash}..{new_hash}",
                "--pretty=format:%h%x09%s", "--no-decorate",
            )
            commits = self._parse_commit_log(log_output)
            diff_output = await self._run_git("diff", "--name-status", f"{old_hash}..{new_hash}")

            msg = self._build_updated_message(
                branch=branch,
                old_hash=old_hash,
                new_hash=new_hash,
                worktree_state=worktree_state,
                pull_output=pull_output,
                commits=commits,
                diff_output=diff_output,
                elapsed=self.fmtsec(started_at),
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
    def _parse_commit_log(log_output: str) -> list[tuple[str, str]]:
        commits = []
        for line in log_output.splitlines():
            line = line.strip()
            if not line:
                continue
            if "\t" in line:
                commit_hash, subject = line.split("\t", 1)
            else:
                parts = line.split(maxsplit=1)
                commit_hash = parts[0]
                subject = parts[1] if len(parts) > 1 else "-"
            commits.append((commit_hash.strip(), subject.strip()))
        return commits

    @staticmethod
    def _summarize_diff(diff_output: str) -> str:
        stats = {"A": 0, "M": 0, "D": 0, "R": 0}
        other = 0
        for line in diff_output.splitlines():
            token = line.strip().split("\t", 1)[0].upper()
            if not token:
                continue
            kind = token[0]
            if kind in stats:
                stats[kind] += 1
            else:
                other += 1

        parts = []
        if stats["A"]:
            parts.append(f"Added {stats['A']}")
        if stats["M"]:
            parts.append(f"Modified {stats['M']}")
        if stats["D"]:
            parts.append(f"Deleted {stats['D']}")
        if stats["R"]:
            parts.append(f"Renamed {stats['R']}")
        if other:
            parts.append(f"Other {other}")
        return ", ".join(parts) if parts else "-"

    @staticmethod
    def _shrink_lines(text: str, limit: int = 4) -> str:
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        if not lines:
            return "-"
        if len(lines) <= limit:
            return "\n".join(lines)
        hidden = len(lines) - limit
        return "\n".join(lines[:limit]) + f"\n... ({hidden} more lines)"

    def _build_uptodate_message(
        self,
        branch: str,
        commit_hash: str,
        worktree_state: str,
        pull_output: str,
        elapsed: str,
    ) -> str:
        pull_preview = self._shrink_lines(pull_output, limit=3)
        body = (
            f"<b>Update Summary</b>\n\n"
            f"Status: Already up to date ✅\n"
            f"Branch: {html.escape(branch)}\n"
            f"Commit: {html.escape(commit_hash)}\n"
            f"Worktree: {html.escape(worktree_state)}\n\n"
            f"<b>Pull Output</b>\n"
            f"<blockquote expandable>{html.escape(pull_preview)}</blockquote>\n\n"
            f"<b><blockquote>{html.escape(elapsed)}</blockquote></b>"
        )
        return body

    def _build_updated_message(
        self,
        branch: str,
        old_hash: str,
        new_hash: str,
        worktree_state: str,
        pull_output: str,
        commits: list[tuple[str, str]],
        diff_output: str,
        elapsed: str,
    ) -> str:
        commit_lines = []
        for commit_hash, subject in commits[:12]:
            commit_lines.append(f"• {commit_hash} {subject}")
        if len(commits) > 12:
            commit_lines.append(f"... and {len(commits) - 12} more")

        commit_block = "\n".join(commit_lines) if commit_lines else "No commit details."
        diff_summary = self._summarize_diff(diff_output)
        pull_preview = self._shrink_lines(pull_output, limit=4)

        body = (
            f"<b>Update Summary</b>\n\n"
            f"Status: Updated ✅\n"
            f"Branch: {html.escape(branch)}\n"
            f"From: {html.escape(old_hash)}\n"
            f"To: {html.escape(new_hash)}\n"
            f"Commits: {len(commits)}\n"
            f"Changes: {html.escape(diff_summary)}\n"
            f"Worktree: {html.escape(worktree_state)}\n\n"
            f"<b>Pull Output</b>\n"
            f"<blockquote expandable>{html.escape(pull_preview)}</blockquote>\n\n"
            f"<b>New Commits</b>\n"
            f"<blockquote expandable>{html.escape(commit_block)}</blockquote>\n\n"
            f"Restarting...\n\n"
            f"<b><blockquote>{html.escape(elapsed)}</blockquote></b>"
        )
        return body

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
