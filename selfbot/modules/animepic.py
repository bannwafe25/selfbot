import asyncio
import contextlib
import datetime
import html
import re
from urllib.parse import quote, unquote

from pyrogram import filters
from pyrogram.types import (
    CallbackQuery,
    InlineQuery,
    InlineQueryResultAnimation,
    InlineQueryResultPhoto,
    InputMediaAnimation,
    InputMediaPhoto,
    Message,
    ReplyParameters,
)

from selfbot.listener import handler, reply
from selfbot.module import Module
from selfbot.apis import DELINE_RANDOM_BA, DELINE_RANDOM_LOLI


class AnimePic(Module):
    name = "AnimePic"

    # ── Tag lists (priority: safebooru → konachan → mwm_moe → picre → waifu_im
    #   → animepixels → yandere → nekos_moe → nekobot → nekosapi → nekosia
    #   → waifu_pics → nekos_best) ──────────────────────────────────────────

    safebooru_tags = [
        "safebooru", "1girl", "1boy", "2boys", "2girls", "genshin_impact",
        "blue_archive", "azur_lane", "honkai_star_rail", "vocaloid",
        "touhou", "miku", "maid", "school_uniform", "swimsuit",
    ]
    konachan_tags  = ["konachan", "landscape", "scenery", "sky", "water", "city", "tree", "clouds", "stars"]
    nekos_best_tags = [
        "husbando", "kitsune", "pat", "baka", "bored", "laugh", "nod", "nope",
        "pout", "shrug", "sleep", "smile", "stare", "think", "thumbsup", "tickle",
    ]

    waifu_pics_tags = [
        "waifu", "happy", "neko", "shinobu", "megumin", "bully", "cuddle", "cry", "hug", "awoo", "kiss",
        "lick", "smug", "bonk", "yeet", "wave", "highfive", "handhold", "nom", "bite",
        "glomp", "slap", "kill", "kick", "wink", "poke", "dance", "cringe",
    ]

    nekosia_tags = [
        "animal_ears", "blue-archive", "blue_eyes", "cat_ears", "fox_ears", "foxgirl",
        "girl", "pink_hair", "sailor_uniform", "tail_with_ribbon", "thigh_high_socks",
        "thighs", "vtuber", "white_hair", "white_thigh_high_socks", "young_girl",
        "kemonomimi", "loli", "maid", "short_hair", "long_hair", "twintails",
    ]

    waifu_im_tags = [
        "maid", "waifu", "uniform", "kamisato-ayaka", "marin-kitagawa", "mori-calliope",
        "raiden-shogun", "oppai", "selfies",
    ]

    animepixels_tags = [
        "animepixels", "nature", "one_piece", "one-piece", "naruto", "pokemon",
        "my_hero_academia", "my-hero-academia", "jujutsu_kaisen", "jujutsu-kaisen",
        "attack_on_titan", "attack-on-titan", "spy_x_family", "spy-x-family",
        "solo_leveling", "solo-leveling", "dragon_ball", "dragon-ball",
        "demon_slayer", "demon-slayer", "bleach", "hunter_x_hunter", "hunter-x-hunter",
        "tokyo_ghoul", "tokyo-ghoul", "death_note", "death-note",
    ]

    animepixels_category_map = {
        "animepixels": None, "nature": "nature",
        "one_piece": "one_piece", "one-piece": "one_piece",
        "naruto": "naruto", "pokemon": "pokemon",
        "my_hero_academia": "my_hero_academia", "my-hero-academia": "my_hero_academia",
        "jujutsu_kaisen": "jujutsu_kaisen", "jujutsu-kaisen": "jujutsu_kaisen",
        "attack_on_titan": "attack_on_titan", "attack-on-titan": "attack_on_titan",
        "spy_x_family": "spy_x_family", "spy-x-family": "spy_x_family",
        "solo_leveling": "solo_leveling", "solo-leveling": "solo_leveling",
        "dragon_ball": "dragon_ball", "dragon-ball": "dragon_ball",
        "demon_slayer": "demon_slayer", "demon-slayer": "demon_slayer",
        "bleach": "bleach", "hunter_x_hunter": "hunter_x_hunter", "hunter-x-hunter": "hunter_x_hunter",
        "tokyo_ghoul": "tokyo_ghoul", "tokyo-ghoul": "tokyo_ghoul",
        "death_note": "death_note", "death-note": "death_note",
    }

    yandere_tags = [
        "yande", "yandere", "kowloon", "rag76", "ogre_illust", "b-baby", "cream_pan",
        "rering", "fiona_cassandra", "hotvenus", "stars_voice", "sparxie", "blue_archive",
        "genshin_impact", "honkai_star_rail", "idolmaster", "fate", "kancolle",
    ]

    mwm_moe_tags = [
        "ai", "aimp", "bd", "fj", "lai", "moe", "moemp", "mp", "pc", "tx", "xhl",
        "ys", "ysmp",
    ]

    picre_tags = ["picre"]

    nekos_moe_tags = [
        "ahoge", "apron", "armor", "armpits", "bangs", "barefoot", "beach", "bed",
        "blush", "bow", "bra", "bunny", "catgirl", "chibi", "collar", "crying",
        "cute", "dress", "embarrassed", "eyes", "fangs", "feet", "flower", "glasses",
        "gloves", "grin", "happy", "hat", "heart", "hoodie", "kawaii", "kimono",
        "leotard", "maid", "midriff", "military", "monochrome", "navel", "nude",
        "original", "panties", "ribbon", "running", "sad", "shy", "skirt", "sleeping",
        "smile", "solo", "swimsuit", "sword", "tail", "tears", "thighhighs", "tongue",
        "twintails", "umbrella", "underwear", "uniform", "waifu", "wings", "yukata",
    ]

    nekobot_tags = ["coffee", "food", "holo", "kanna", "kemonomimi", "gasm", "meow", "fox_girl", "avatar"]

    deline_tags = ["ba", "loli", "waifu", "husbu", "cosplay"]
    _deline_map = {
        "ba": DELINE_RANDOM_BA,
        "loli": DELINE_RANDOM_LOLI,
        "waifu": "https://api.deline.web.id/random/waifu",
        "husbu": "https://api.deline.web.id/random/husbu",
        "cosplay": "https://api.deline.web.id/random/cosplay",
    }

    nekosapi_tags = [
        "black_hair", "blonde_hair", "blue_hair", "brown_hair", "horsegirl",
        "large_breasts", "medium_breasts", "mountain", "night", "purple_hair", "rain",
        "red_hair", "school_uniform", "shorts", "small_breasts", "sportswear", "tree",
        "usagimimi", "wet", "maid", "foxgirl", "catgirl",
    ]

    tags = sorted(
        set(
            safebooru_tags + konachan_tags + mwm_moe_tags + picre_tags
            + waifu_im_tags + animepixels_tags + yandere_tags + nekos_moe_tags
            + nekobot_tags + nekosapi_tags + nekosia_tags + waifu_pics_tags
            + nekos_best_tags + deline_tags
            + ["gecg", "meow", "gasm", "goose", "lewd", "v3", "wallpaper",
               "lizard", "woof", "fox_girl", "avatar", "cuddle", "hug", "kiss",
               "spank", "feed"]
        )
    )

    msg_pattern = re.compile(
        rf"^(?:({'|'.join(re.escape(t) for t in tags)})|moe\s+(.+))$",
        re.IGNORECASE,
    )
    moe_tags_pattern = re.compile(r"^moetags(?:\s+(.+))?$", re.IGNORECASE)
    cb_pattern = re.compile(r"^animepic/next/(.+)$")

    cmds = f"{{{', '.join(tags)}}} | moe {{tag}} | moetags {{keyword?}}"
    desc = {
        "Info": "Sends anime pictures from multi API sources.",
        "moe {tag}": "Search image by Nekos.moe tag.",
        "moetags {keyword?}": "List Nekos.moe tags (or filter by keyword).",
        "e.g.": "waifu | moe cat ears | moetags cat",
    }

    # ── Nekos.moe tag cache ───────────────────────────────────────────────────
    _moe_tags_cache: list[str] = []
    _moe_tags_cache_time: datetime.datetime | None = None
    _moe_tags_cache_ttl = datetime.timedelta(hours=12)
    _moe_tags_hint = [
        "1girl", "2girls", "cat ears", "animal ears", "ahoge", "smile", "blush",
        "blue eyes", "brown hair", "white hair", "black hair", "long hair",
        "short hair", "thighhighs", "skirt", "uniform", "school uniform", "maid",
    ]

    # ── API routing registry (list_attr, method_name, pass_moe_tag) ───────────
    _API_REGISTRY = (
        ("deline_tags",    "_get_from_deline",     False),
        ("safebooru_tags", "_get_from_safebooru", False),
        ("konachan_tags",  "_get_from_konachan",  False),
        ("mwm_moe_tags",   "_get_from_mwm_moe",   False),
        ("picre_tags",     "_get_from_picre",      False),
        ("waifu_im_tags",  "_get_from_waifu_im",   False),
        ("animepixels_tags", "_get_from_animepixels", False),
        ("yandere_tags",   "_get_from_yandere",    False),
        ("nekos_moe_tags", "_get_from_nekos_moe",  True),
        ("nekobot_tags",   "_get_from_nekobot",    False),
        ("nekosapi_tags",  "_get_from_nekosapi",   False),
        ("nekosia_tags",   "_get_from_nekosia",    False),
        ("waifu_pics_tags","_get_from_waifu_pics", False),
        ("nekos_best_tags","_get_from_nekos_best", False),
    )

    # ── Handlers ─────────────────────────────────────────────────────────────

    @handler(filters.regex(moe_tags_pattern) & ~reply, 1)
    async def on_moe_tags(self, event: Message) -> None:
        await self._safe_respond(event, "<code>Fetching Nekos.moe tags...</code>")
        try:
            m = self.moe_tags_pattern.match(str(event.content or ""))
            raw_query = m.group(1) if m else None
            query = (raw_query or "").strip()
            force_refresh = query.lower() in {"-r", "--refresh", "refresh"}
            if force_refresh:
                query = ""

            all_tags = await self._fetch_moe_tags(force_refresh=force_refresh)
            if not all_tags:
                await self._safe_respond(event, "<code>Failed to fetch Nekos.moe tags right now.</code>")
                return

            if query:
                matched = [t for t in all_tags if query.lower() in t.lower()]
                if not matched:
                    await self._safe_respond(
                        event,
                        f"<code>No Nekos.moe tag matched: {html.escape(query)}</code>",
                    )
                    return
                joined_tags, shown_count = self._format_tag_list(matched, max_chars=2500)
                text = (
                    "<b>Nekos.moe Tags</b>\n"
                    f"<b>Query:</b> <code>{html.escape(query)}</code>\n"
                    f"<b>Matched:</b> <code>{len(matched)}</code>\n"
                    f"<b>Shown:</b> <code>{shown_count}</code>\n\n"
                    f"<code>{html.escape(joined_tags)}</code>\n\n"
                    "<b>Use:</b> <code>moe &lt;tag&gt;</code>"
                )
                await self._safe_respond(event, text)
                return

            hints = [t for t in self._moe_tags_hint if t in all_tags]
            hint_text, _ = self._format_tag_list(hints, max_chars=500)
            text = (
                "<b>Nekos.moe Tags</b>\n"
                f"<b>Total:</b> <code>{len(all_tags)}</code>\n"
                f"<b>Hints:</b> <code>{html.escape(hint_text)}</code>\n\n"
                "<b>Use:</b> <code>moe &lt;tag&gt;</code>\n"
                "<b>Search:</b> <code>moetags &lt;keyword&gt;</code>\n"
                "<b>Refresh cache:</b> <code>moetags --refresh</code>"
            )
            await self._safe_respond(event, text)
        except Exception as e:
            await self._safe_respond(event, f"<code>{html.escape(str(e))}</code>")

    @handler(filters.regex(msg_pattern) & ~reply, 1)
    async def on_message_out(self, event: Message) -> None:
        await self._safe_respond(event, "<code>...</code>")
        now = datetime.datetime.now(datetime.UTC)
        try:
            query = str(event.content or "").strip()
            tag, moe_tag = self.parse_query(query)
            reply_params = ReplyParameters(message_id=event.reply_to_message_id or event.id)
            res = await event._client.get_inline_bot_results(
                self.client.bot.me.id, query, chat_id=event.chat.id
            )
            if not res.results:
                await self._safe_respond(event, "<code>The bot returned no results.</code>")
                return

            try:
                await event.reply_inline_bot_result(
                    res.query_id, res.results[0].id,
                    reply_parameters=reply_params,
                )
            except Exception as inline_err:
                err_str = str(inline_err).upper()
                if "WEBPAGE_MEDIA_EMPTY" not in err_str and "WEBPAGE_CURL_FAILED" not in err_str:
                    raise

                result = await self.get_image_url(tag, moe_tag)
                if not result:
                    raise inline_err

                caption = self.build_caption(self.fmtsec(now), *result[1:])
                if self._is_gif_url(result[0]):
                    await event.reply_animation(
                        animation=result[0], caption=caption,
                        reply_parameters=reply_params,
                    )
                else:
                    await event.reply_photo(
                        photo=result[0], caption=caption,
                        reply_parameters=reply_params,
                    )

            with contextlib.suppress(Exception):
                await event.delete()
        except Exception as e:
            await self._safe_respond(event, f"<code>{html.escape(str(e))}</code>")

    @handler(filters.regex(msg_pattern), 2)
    async def on_inline_query(self, event: InlineQuery) -> None:
        query = str(event.query or "").strip()
        tag, moe_tag = self.parse_query(query)
        try:
            now = datetime.datetime.now(datetime.UTC)
            result = await self.get_image_url(tag, moe_tag)
            if not result:
                await event.answer([], cache_time=0)
                return

            caption = self.build_caption(self.fmtsec(now), *result[1:])
            kb = self.build_keyboard(tag, moe_tag)
            if self._is_gif_url(result[0]):
                inline_result = InlineQueryResultAnimation(
                    animation_url=result[0], caption=caption, reply_markup=kb,
                )
            else:
                inline_result = InlineQueryResultPhoto(
                    photo_url=result[0], caption=caption, reply_markup=kb,
                )

            await event.answer([inline_result], cache_time=0)
        except Exception:
            await event.answer([], cache_time=0)

    @handler(filters.regex(cb_pattern), 4)
    async def on_inline_callback(self, event: CallbackQuery) -> None:
        (payload,) = event.matches[0].groups()
        try:
            await event.answer("Refreshing...")
            now = datetime.datetime.now(datetime.UTC)
            tag, moe_tag = self.parse_callback_payload(payload)
            result = await self.get_image_url(tag, moe_tag)
            if not result:
                await event.answer("Failed to get a new image.", show_alert=True)
                return

            caption = self.build_caption(self.fmtsec(now), *result[1:])
            if self._is_gif_url(result[0]):
                media = InputMediaAnimation(media=result[0], caption=caption)
            else:
                media = InputMediaPhoto(media=result[0], caption=caption)

            await event.edit_message_media(
                media=media, reply_markup=self.build_keyboard(tag, moe_tag),
            )
        except Exception as e:
            await event.answer(f"Error: {html.escape(str(e))}", show_alert=True)

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def _safe_respond(self, event: Message, text: str) -> None:
        try:
            await self.respond(event, text)
        except Exception:
            with contextlib.suppress(Exception):
                await event._client.send_message(event.chat.id, text)

    async def _fetch_moe_tags(self, force_refresh: bool = False) -> list[str]:
        now = datetime.datetime.now(datetime.UTC)
        if (
            not force_refresh
            and self._moe_tags_cache
            and self._moe_tags_cache_time
            and now - self._moe_tags_cache_time < self._moe_tags_cache_ttl
        ):
            return self._moe_tags_cache

        resp = await self.client.http.get("https://nekos.moe/api/v1/tags", timeout=15)
        if resp.status_code != 200:
            return self._moe_tags_cache

        raw_tags = (resp.json() or {}).get("tags") or []
        fetched = sorted({t.strip() for t in raw_tags if isinstance(t, str) and t.strip()})
        if fetched:
            self._moe_tags_cache = fetched
            self._moe_tags_cache_time = now
        return self._moe_tags_cache

    @staticmethod
    def _format_tag_list(tags: list[str], max_chars: int = 2500) -> tuple[str, int]:
        picked, used = [], 0
        for tag in tags:
            token = tag if not picked else f", {tag}"
            if used + len(token) > max_chars:
                break
            picked.append(tag)
            used += len(token)
        return ", ".join(picked), len(picked)

    # ── Query / payload parsing ───────────────────────────────────────────────

    @staticmethod
    def parse_query(query: str) -> tuple[str, str | None]:
        normalized = (query or "").strip()
        if not normalized:
            return "", None
        m = re.match(r"^moe\s+(.+)$", normalized, flags=re.IGNORECASE)
        if m:
            wanted = m.group(1).strip()
            return "moe", wanted or None
        return normalized.lower(), None

    @staticmethod
    def parse_callback_payload(payload: str) -> tuple[str, str | None]:
        if payload.startswith("moe::"):
            wanted = unquote(payload[5:]).strip()
            return "moe", wanted or None
        return payload.lower(), None

    @staticmethod
    def build_callback_payload(tag: str, moe_tag: str | None) -> str:
        if tag == "moe" and moe_tag:
            compact = " ".join(moe_tag.strip().split())[:24]
            return f"moe::{quote(compact, safe='')[:40]}"
        return tag

    # ── Image routing ─────────────────────────────────────────────────────────

    async def get_image_url(self, tag: str, moe_tag: str | None = None) -> tuple | None:
        for list_attr, func_name, use_moe in self._API_REGISTRY:
            if tag in getattr(self, list_attr):
                try:
                    fn = getattr(self, func_name)
                    result = await fn(moe_tag if use_moe else tag)
                    if result:
                        return result
                except Exception:
                    continue
        return await self._fallback_nekos_life(tag)

    async def _fallback_nekos_life(self, tag: str) -> tuple | None:
        try:
            for _ in range(3):
                resp = await self.client.http.get(
                    f"https://nekos.life/api/v2/img/{tag}", timeout=10
                )
                if resp.status_code == 200:
                    url = resp.json().get("url")
                    if self._is_valid_non_gif(url):
                        return url, None, {}, None
                await asyncio.sleep(0.2)
        except Exception:
            pass
        return None

    # ── URL utilities ─────────────────────────────────────────────────────────

    @staticmethod
    def _is_valid_url(url: str | None) -> bool:
        return bool(isinstance(url, str) and url.startswith(("http://", "https://")))

    @staticmethod
    def _is_gif_url(url: str | None) -> bool:
        if not isinstance(url, str):
            return False
        return url.split("?", 1)[0].split("#", 1)[0].lower().endswith(".gif")

    @staticmethod
    def _is_valid_non_gif(url: str | None) -> bool:
        return AnimePic._is_valid_url(url) and not AnimePic._is_gif_url(url)

    @staticmethod
    def _pick_preferred_url(urls: list[str]) -> str | None:
        for url in urls:
            if AnimePic._is_valid_non_gif(url):
                return url
        for url in urls:
            if AnimePic._is_valid_url(url):
                return url
        return None

    # ── API fetchers ──────────────────────────────────────────────────────────

    async def _get_from_deline(self, tag: str) -> tuple | None:
        api_url = self._deline_map.get(tag)
        if not api_url:
            return None
            
        import time
        buster = f"{time.time()}"
        sep = "&" if "?" in api_url else "?"
        query_url = f"{api_url}{sep}t={buster}"
        
        resp = await self.client.http.head(query_url, timeout=10)
        if resp.status_code == 200:
            return api_url, None, {}, None
        return None


    async def _get_from_mwm_moe(self, tag: str) -> tuple | None:
        resp = await self.client.http.get(
            f"https://t.mwm.moe/{tag}", follow_redirects=True, timeout=10
        )
        url = str(resp.url) if resp.status_code == 200 else None
        return (url, None, {}, None) if self._is_valid_non_gif(url) else None

    async def _get_from_picre(self, _: str) -> tuple | None:
        resp = await self.client.http.post("https://pic.re/image", timeout=10)
        if resp.status_code == 200:
            data = resp.json() or {}
            file_url = data.get("file_url")
            if isinstance(file_url, str):
                if file_url.startswith("//"):
                    file_url = f"https:{file_url}"
                elif file_url.startswith("/"):
                    file_url = f"https://pic.re{file_url}"
                elif not file_url.startswith(("http://", "https://")):
                    file_url = f"https://{file_url.lstrip('/')}"
            if self._is_valid_non_gif(file_url):
                return file_url, data.get("author"), {}, data.get("source")

        resp = await self.client.http.get(
            "https://pic.re/images", follow_redirects=True, timeout=10
        )
        url = str(resp.url) if resp.status_code == 200 else None
        return (url, None, {}, None) if self._is_valid_non_gif(url) else None

    async def _get_from_waifu_im(self, tag: str) -> tuple | None:
        resp = await self.client.http.get(
            "https://api.waifu.im/images",
            params={"IncludedTags": tag, "IsNsfw": "false", "PageSize": 1},
            timeout=10,
        )
        if resp.status_code != 200:
            return None

        data = resp.json() or {}
        images = data.get("items") or data.get("images") or []
        if not isinstance(images, list) or not images:
            return None

        image_data = images[0]
        url = image_data.get("url")
        if not self._is_valid_non_gif(url):
            return None

        artists = image_data.get("artists") or []
        artist = (
            artists[0]
            if isinstance(artists, list) and artists and isinstance(artists[0], dict)
            else image_data.get("artist") or {}
        )
        links = {
            k: v for k, v in {
                "Pixiv": artist.get("pixiv"),
                "Twitter": artist.get("twitter"),
                "Patreon": artist.get("patreon"),
                "DeviantArt": artist.get("deviantArt"),
            }.items() if v
        }
        return url, artist.get("name"), links, image_data.get("source") or image_data.get("source_url")

    async def _get_from_animepixels(self, tag: str) -> tuple | None:
        category = self.animepixels_category_map.get(tag)
        if category:
            resp = await self.client.http.get(
                f"https://animepixels-api.vercel.app/api/media/image/{category}",
                params={"limit": 1, "offset": 0},
                timeout=10,
            )
            if resp.status_code != 200:
                return None
            results = (resp.json() or {}).get("results") or []
            if not isinstance(results, list) or not results:
                return None
            data = results[0]
        else:
            resp = await self.client.http.get(
                "https://animepixels-api.vercel.app/api/media/random/image", timeout=10
            )
            if resp.status_code != 200:
                return None
            data = resp.json() or {}

        url = data.get("url")
        return (url, None, {}, None) if self._is_valid_non_gif(url) else None

    async def _get_from_yandere(self, tag: str) -> tuple | None:
        tag_filter = None if tag in {"yande", "yandere"} else tag
        base_query = "rating:safe order:random"
        query = f"{base_query} {tag_filter}" if tag_filter else base_query

        resp = await self.client.http.get(
            "https://yande.re/post.json", params={"limit": 1, "tags": query}, timeout=10
        )
        if resp.status_code != 200:
            return None

        posts = resp.json() or []
        if tag_filter and (not isinstance(posts, list) or not posts):
            resp = await self.client.http.get(
                "https://yande.re/post.json",
                params={"limit": 1, "tags": base_query},
                timeout=10,
            )
            if resp.status_code != 200:
                return None
            posts = resp.json() or []

        if not isinstance(posts, list) or not posts:
            return None

        post = posts[0]
        url = post.get("sample_url") or post.get("jpeg_url") or post.get("file_url")
        if not self._is_valid_non_gif(url):
            return None

        post_id = post.get("id")
        source = post.get("source") or (f"https://yande.re/post/show/{post_id}" if post_id else None)
        return url, post.get("author"), {}, source

    async def _get_from_nekos_moe(self, wanted_tag: str | None = None) -> tuple | None:
        image_data: dict = {}

        if wanted_tag:
            raw_tags = [t.strip() for t in re.split(r"[|,]", wanted_tag) if t.strip()]
            search_resp = await self.client.http.post(
                "https://nekos.moe/api/v1/images/search",
                json={"nsfw": False, "tags": (raw_tags or [wanted_tag.strip()])[:8],
                      "sort": "relevance", "limit": 1},
                timeout=10,
            )
            if search_resp.status_code == 200:
                images = (search_resp.json() or {}).get("images") or []
                if images and isinstance(images[0], dict):
                    image_data = images[0]

        if not image_data:
            resp = await self.client.http.get(
                "https://nekos.moe/api/v1/random/image",
                params={"nsfw": "false", "count": 1},
                timeout=10,
            )
            if resp.status_code != 200:
                return None
            images = (resp.json() or {}).get("images") or []
            if not images or not isinstance(images[0], dict):
                return None
            image_data = images[0]

        image_id = image_data.get("id")
        if not image_id:
            return None

        detail_resp = await self.client.http.get(
            f"https://nekos.moe/api/v1/images/{image_id}", timeout=10
        )
        if detail_resp.status_code == 200:
            detail = (detail_resp.json() or {}).get("image")
            if isinstance(detail, dict):
                image_data = detail

        raw_artist = image_data.get("artist")
        if isinstance(raw_artist, dict):
            artist_name = raw_artist.get("username")
        elif isinstance(raw_artist, str):
            artist_name = raw_artist or None
        else:
            artist_name = None

        source = image_data.get("source")
        if not isinstance(source, str) or not source.startswith(("http://", "https://")):
            source = f"https://nekos.moe/post/{image_id}"

        return f"https://nekos.moe/image/{image_id}", artist_name, {}, source

    async def _get_from_safebooru(self, tag: str) -> tuple | None:
        query_tag = "1boy" if tag == "husbando" else ("1girl" if tag == "safebooru" else tag)
        resp = await self.client.http.get(
            "https://safebooru.org/index.php",
            params={"page": "dapi", "s": "post", "q": "index",
                    "json": 1, "limit": 1, "tags": f"{query_tag} sort:random"},
            timeout=10,
        )
        if resp.status_code != 200 or not resp.json():
            return None
        item = resp.json()[0]
        url = item.get("file_url")
        if not self._is_valid_url(url):
            return None
        source = item.get("source") or f"https://safebooru.org/index.php?page=post&s=view&id={item.get('id')}"
        return url, None, {}, source

    async def _get_from_konachan(self, tag: str) -> tuple | None:
        query_tag = "" if tag == "konachan" else tag
        resp = await self.client.http.get(
            "https://konachan.net/post.json",
            params={"limit": 1, "tags": f"{query_tag} order:random".strip()},
            timeout=10,
        )
        if resp.status_code != 200 or not resp.json():
            return None
        item = resp.json()[0]
        url = item.get("file_url") or item.get("jpeg_url")
        if not self._is_valid_url(url):
            return None
        source = item.get("source") or f"https://konachan.net/post/show/{item.get('id')}"
        return url, item.get("author"), {}, source

    async def _get_from_nekobot(self, tag: str) -> tuple | None:
        api_category = "hololewd" if tag == "holo" else tag
        resp = await self.client.http.get(
            "https://nekobot.xyz/api/image", params={"type": api_category}, timeout=10
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        url = data.get("message") if data.get("success") else None
        return (url, None, {}, None) if self._is_valid_non_gif(url) else None

    async def _get_from_nekosapi(self, tag: str) -> tuple | None:
        resp = await self.client.http.get(
            "https://api.nekosapi.com/v4/images/random",
            params={"rating": "safe,suggestive", "count": 1, "tags": tag},
            timeout=10,
        )
        if resp.status_code != 200:
            return None
        images = resp.json() or []
        if not images:
            return None
        data = images[0]
        url = data.get("url")
        return (url, data.get("artist_name"), {}, data.get("source_url")) if self._is_valid_non_gif(url) else None

    async def _get_from_nekosia(self, tag: str) -> tuple | None:
        resp = await self.client.http.get(
            f"https://api.nekosia.cat/api/v1/images/{tag}", timeout=10
        )
        if resp.status_code != 200:
            resp = await self.client.http.get(
                "https://api.nekosia.cat/api/v1/images/random",
                params={"tag": tag}, timeout=10,
            )
        if resp.status_code != 200:
            return None

        data = resp.json()
        if isinstance(data, list):
            if not data:
                return None
            data = data[0]

        url = data.get("image", {}).get("original", {}).get("url")
        if not self._is_valid_non_gif(url):
            return None

        artist = data.get("attribution", {}).get("artist", {})
        source = data.get("source", {})
        links = {"Profile": artist["profile"]} if artist.get("profile") else {}
        return url, artist.get("username"), links, source.get("url")

    async def _get_from_waifu_pics(self, tag: str) -> tuple | None:
        many = await self.client.http.post(
            f"https://api.waifu.pics/many/sfw/{tag}", json={}, timeout=10
        )
        if many.status_code == 200:
            files = (many.json() or {}).get("files") or []
            if isinstance(files, list):
                url = self._pick_preferred_url(files)
                if url:
                    return url, None, {}, None

        resp = await self.client.http.get(f"https://api.waifu.pics/sfw/{tag}", timeout=10)
        if resp.status_code != 200:
            return None
        url = (resp.json() or {}).get("url")
        return (url, None, {}, None) if self._is_valid_url(url) else None

    async def _get_from_nekos_best(self, tag: str) -> tuple | None:
        resp = await self.client.http.get(f"https://nekos.best/api/v2/{tag}", timeout=10)
        if resp.status_code != 200:
            return None
        result = (resp.json().get("results") or [{}])[0]
        url = result.get("url")
        if not self._is_valid_non_gif(url):
            return None
        links = {"Profile": result["artist_href"]} if result.get("artist_href") else {}
        return url, result.get("artist_name"), links, result.get("source_url")

    # ── Caption / keyboard builders ───────────────────────────────────────────

    def build_keyboard(self, tag: str, moe_tag: str | None = None):
        payload = self.build_callback_payload(tag, moe_tag)
        return self.ikm([[
            ("Refresh", "data", f"animepic/next/{payload}", "G"),
            ("Close",   "data", b"0", "R"),
        ]])

    def build_caption(
        self,
        rtt: str,
        artist_name: str | None,
        artist_links: dict | None,
        source_url: str | None,
    ) -> str:
        parts = []
        if artist_name:
            artist = f"Artist: {html.escape(artist_name)}"
            if artist_links:
                link_strs = [
                    f'<a href="{u}">{html.escape(n)}</a>'
                    for n, u in artist_links.items() if u
                ]
                if link_strs:
                    artist = f"{artist} ({' | '.join(link_strs)})"
            parts.append(artist)
        if source_url:
            parts.append(f'<a href="{source_url}">Source</a>')

        info = " | ".join(parts)
        body = f"<b><blockquote>{rtt}</blockquote></b>"
        return f"{info}\n{body}" if info else body
