import asyncio
import contextlib
import html
import json
import os
import re
import tempfile
import urllib.request

from pyrogram import filters
from pyrogram.types import Message

from selfbot.listener import handler
from selfbot.module import Module

pattern = re.compile(r"^(?:scrapr|dl)(?:\s+([\s\S]+))?$", re.IGNORECASE)

BRIDGE = os.path.expanduser("~/apps/selfbot/scrapr/bridge.js")

# Deteksi platform dari URL → action scrapr
ROUTES = [
    (r"tiktok\.com|vt\.tiktok", "tiktok.snaptik"),
    (r"instagram\.com", "instagram.snapsave"),
    (r"mediafire\.com", "resolver.mediafire"),
    (r"sfile\.mobi|sfile\.com", "resolver.sfile"),
    (r"safelinku|sfl\.gl", "resolver.safelinku"),
    (r"rekonise\.com", "resolver.rekonise"),
    (r"sub2unlock", "resolver.sub2unlock"),
    (r"terabox", "terabox.sechno"),
    (r"facebook\.com|fb\.watch", "facebook.fdown"),
    (r"twitter\.com|x\.com", "twitter.tvd"),
    (r"soundcloud\.com", "soundcloud.klickaud"),
    (r"spotify\.com", "spotify.spotidown"),
    (r"pin\.it|pinterest\.com", "pinterest.pindown"),
    (r"reddit\.com", "reddit.rapidsave"),
    (r"threads\.net", "threads.threadster"),
    (r"bilibili\.com", "bilibili.direct"),
    (r"douyin\.com", "douyin.direct"),
    (r"pixiv\.net", "pixiv.ajax"),
    (r"bandcamp\.com", "bandcamp.bandcampdownloader"),
    (r"music\.apple\.com", "applemusic.aplmate"),
    (r"xiaohongshu|rednote", "rednote.direct"),
]


def _detect(url: str) -> str | None:
    for rx, action in ROUTES:
        if re.search(rx, url, re.IGNORECASE):
            return action
    return None


async def _run_bridge(action: str, url: str) -> dict:
    proc = await asyncio.create_subprocess_exec(
        "node", BRIDGE, action, url,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
    )
    out, _ = await asyncio.wait_for(proc.communicate(), timeout=90)
    data = json.loads(out.decode().strip() or "{}")
    if not data.get("status"):
        raise RuntimeError(data.get("error") or data.get("message") or "scrapr gagal")
    return data["result"]


def _download(url: str, dest: str) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=180) as r, open(dest, "wb") as f:
        while True:
            chunk = r.read(262144)
            if not chunk:
                break
            f.write(chunk)
    if not os.path.exists(dest) or os.path.getsize(dest) < 5000:
        raise RuntimeError("file kecil/kosong")


def _pick_downloads(result: dict) -> list[dict]:
    """Pilih media terbaik dari hasil scrapr (maks 3 file)."""
    dls = result.get("downloads") or []
    if not dls and result.get("url"):
        dls = [{"url": result["url"], "type": result.get("type", "file"),
                "quality": result.get("quality", "")}]
    # urutkan: video > audio; quality tinggi dulu
    def rank(d):
        q = str(d.get("quality", ""))
        num = 0
        m = re.search(r"(\d{3,4})p", q)
        if m:
            num = int(m.group(1))
        return (d.get("type") == "video", num)
    return sorted(dls, key=rank, reverse=True)[:3]


class Scrapr(Module):
    name = "Scrapr"
    cmds = "scrapr|dl {url}"
    desc = {
        "{url}": "Link sosmed/file — auto detect platform (TikTok, IG, MediaFire, dll).",
        "e.g.": "dl https://vt.tiktok.com/xxx",
    }

    @handler(filters.regex(pattern), 1)
    async def on_message_out(self, event: Message) -> None:
        query = (pattern.match(str(event.content).strip()).group(1) or "").strip()
        if not query and event.reply_to_message:
            query = (event.reply_to_message.text or event.reply_to_message.caption or "").strip()
        m = re.search(r"https?://\S+", query)
        if not m:
            await self.respond(event, "<code>Usage: dl {url}</code>")
            return
        url = m.group(0)

        action = _detect(url)
        if not action:
            await self.respond(event, "<code>Platform gak dikenali.</code>")
            return

        status = await self.respond(event, f"<code>Resolving {html.escape(action)}...</code>")

        try:
            result = await _run_bridge(action, url)
        except Exception as e:
            with contextlib.suppress(Exception):
                await status.edit(f"<code>Resolve gagal: {e}</code>")
            return

        title = result.get("title") or result.get("filename") or "media"
        dls = _pick_downloads(result)
        if not dls:
            with contextlib.suppress(Exception):
                await status.edit("<code>Gak ada media yang bisa diunduh.</code>")
            return

        # === Kartu rich "Scrapr — Siap Diunduh" (via bot inline, pola sgb) ===
        try:
            import datetime as _dt
            import richpyro as rp
            from pyrogram.raw import functions as rawfn
            from pyrogram.raw.types import (
                InputBotInlineMessageRichMessage,
                InputBotInlineResult,
            )

            now = _dt.datetime.now(_dt.UTC)
            plat = action.split(".")[0].capitalize()
            blocks = [
                rp.para(rp.bold("Scrapr — Siap Diunduh")),
                rp.para(title.strip()[:200]),
                rp.para(
                    f"Platform: {plat}\n"
                    + "\n".join(f"{i}. {d.get('quality') or d.get('type','file')}" for i, d in enumerate(dls, 1))
                ),
            ]
            bot = self.client.bot
            rich_raw = await rp.blocks_message(*blocks).write(client=bot)
            ping_mod = self.client.modules.get("Ping")
            route = getattr(ping_mod, "_rich_route", None)
            if route is None and ping_mod is not None:
                self._ensure_rich_handler(
                    ping_mod, rawfn, InputBotInlineMessageRichMessage, InputBotInlineResult
                )
                route = getattr(ping_mod, "_rich_route", None)
            if route is not None:
                route["scrapr"] = (rich_raw, None)
                res = await event._client.get_inline_bot_results(
                    bot.me.id, f"scrapr{now.timestamp()}"
                )
                if res.results:
                    await event.reply_inline_bot_result(res.query_id, res.results[0].id)
                    with contextlib.suppress(Exception):
                        await event.delete()
                    # lanjut download di background, status text gak dibutuhkan lagi
                    with contextlib.suppress(Exception):
                        await status.delete()
        except Exception:
            pass  # rich gagal → lanjut jalur biasa (status text)

        with contextlib.suppress(Exception):
            await status.edit(f"<code>Downloading: {html.escape(title[:100])}</code>")

        tmp_dir = tempfile.mkdtemp(prefix="scrapr_")
        sent = 0
        for d in dls:
            durl = d.get("url")
            if not durl:
                continue
            dtype = str(d.get("type", "file")).lower()
            # normalisasi: "mp4"->video, "mp3/m4a"->audio, "jpg/png"->image
            dtype = {"mp4": "video", "mkv": "video", "webm": "video",
                     "mp3": "audio", "m4a": "audio",
                     "jpg": "image", "jpeg": "image", "png": "image"}.get(dtype, dtype)
            # Deteksi ext dari URL kalau type gak jelas
            ext = {"video": ".mp4", "audio": ".mp3", "image": ".jpg"}.get(dtype, "")
            if not ext:
                um = re.search(r"\.(mp4|mkv|webm|m4a|mp3|jpg|jpeg|png|gif)(\?|$)", durl, re.IGNORECASE)
                ext = f".{um.group(1).lower()}" if um else ".bin"
                if ext in (".mp4", ".mkv", ".webm"):
                    dtype = "video"
                elif ext in (".m4a", ".mp3"):
                    dtype = "audio"
                elif ext in (".jpg", ".jpeg", ".png", ".gif"):
                    dtype = "image"
            dest = os.path.join(tmp_dir, f"media{ext}")
            try:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, _download, durl, dest)
                cap = f"<b>{html.escape(title[:200])}</b>"
                if d.get("quality"):
                    cap += f"\n{d['quality']}"
                if dtype in ("video", "image"):
                    if dtype == "video":
                        await self.client.app.send_video(event.chat.id, dest, caption=cap)
                    else:
                        await self.client.app.send_photo(event.chat.id, dest, caption=cap)
                else:
                    await self.client.app.send_document(event.chat.id, dest, caption=cap)
                sent += 1
            except Exception:
                continue
            if sent >= 3:
                break

        with contextlib.suppress(Exception):
            import shutil
            shutil.rmtree(tmp_dir, True)
        if sent:
            with contextlib.suppress(Exception):
                await status.delete()
            with contextlib.suppress(Exception):
                await event.delete()
        else:
            with contextlib.suppress(Exception):
                await status.edit("<code>Semua download gagal.</code>")
