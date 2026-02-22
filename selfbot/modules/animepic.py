import asyncio
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


class AnimePic(Module):
    name = "AnimePic"

    nekos_best_tags = ["husbando", "kitsune", "neko", "pat"]

    waifu_pics_tags = [
        "waifu",
        "neko",
        "shinobu",
        "megumin",
        "bully",
        "cry",
        "awoo",
        "lick",
        "smug",
        "blush",
        "smile",
        "wave",
        "highfive",
        "handhold",
        "nom",
        "bite",
        "slap",
        "happy",
        "wink",
        "poke",
        "cringe",
    ]

    nekosia_tags = [
        "animal_ears",
        "blue-archive",
        "blue_eyes",
        "cat_ears",
        "catgirl",
        "cute",
        "fox_ears",
        "foxgirl",
        "girl",
        "pink_hair",
        "ribbon",
        "sailor_uniform",
        "skirt",
        "smile",
        "tail",
        "tail_with_ribbon",
        "thigh_high_socks",
        "thighs",
        "uniform",
        "vtuber",
        "white_hair",
        "white_thigh_high_socks",
        "young_girl",
        "kemonomimi",
    ]

    waifu_im_tags = [
        "kamisato-ayaka",
        "marin-kitagawa",
        "mori-calliope",
        "raiden-shogun",
        "maid",
        "oppai",
        "selfies",
        "uniform",
        "waifu",
    ]

    animepixels_tags = [
        "animepixels",
        "nature",
        "one_piece",
        "one-piece",
        "naruto",
        "pokemon",
        "my_hero_academia",
        "my-hero-academia",
        "jujutsu_kaisen",
        "jujutsu-kaisen",
        "attack_on_titan",
        "attack-on-titan",
        "spy_x_family",
        "spy-x-family",
        "solo_leveling",
        "solo-leveling",
        "dragon_ball",
        "dragon-ball",
        "demon_slayer",
        "demon-slayer",
    ]

    animepixels_category_map = {
        "animepixels": None,
        "nature": "nature",
        "one_piece": "one_piece",
        "one-piece": "one_piece",
        "naruto": "naruto",
        "pokemon": "pokemon",
        "my_hero_academia": "my_hero_academia",
        "my-hero-academia": "my_hero_academia",
        "jujutsu_kaisen": "jujutsu_kaisen",
        "jujutsu-kaisen": "jujutsu_kaisen",
        "attack_on_titan": "attack_on_titan",
        "attack-on-titan": "attack_on_titan",
        "spy_x_family": "spy_x_family",
        "spy-x-family": "spy_x_family",
        "solo_leveling": "solo_leveling",
        "solo-leveling": "solo_leveling",
        "dragon_ball": "dragon_ball",
        "dragon-ball": "dragon_ball",
        "demon_slayer": "demon_slayer",
        "demon-slayer": "demon_slayer",
    }

    yandere_tags = [
        "yande",
        "yandere",
        "kowloon",
        "rag76",
        "ogre_illust",
        "b-baby",
        "cream_pan",
        "rering",
        "fiona_cassandra",
        "hotvenus",
        "stars_voice",
        "sparxie",
    ]

    mwm_moe_tags = [
        "ai",
        "aimp",
        "bd",
        "fj",
        "lai",
        "moe",
        "moemp",
        "mp",
        "pc",
        "tx",
        "xhl",
        "ys",
        "ysmp",
    ]

    picre_tags = ["picre"]
    nekos_moe_tags = ["moe"]
    nekobot_tags = ["coffee", "food", "holo", "kanna", "kemonomimi", "neko"]

    nekosapi_tags = [
        "bikini",
        "black_hair",
        "blonde_hair",
        "blue_hair",
        "brown_hair",
        "catgirl",
        "dress",
        "flower",
        "girl",
        "horsegirl",
        "kemonomimi",
        "large_breasts",
        "medium_breasts",
        "mountain",
        "night",
        "pink_hair",
        "purple_hair",
        "rain",
        "red_hair",
        "school_uniform",
        "shorts",
        "skirt",
        "small_breasts",
        "sportswear",
        "tree",
        "usagimimi",
        "wet",
        "white_hair",
    ]

    tags = sorted(
        list(
            set(
                mwm_moe_tags
                + picre_tags
                + waifu_im_tags
                + animepixels_tags
                + yandere_tags
                + nekos_moe_tags
                + nekobot_tags
                + nekosapi_tags
                + nekosia_tags
                + waifu_pics_tags
                + nekos_best_tags
                + [
                    "gecg",
                    "meow",
                    "gasm",
                    "goose",
                    "lewd",
                    "v3",
                    "wallpaper",
                    "lizard",
                    "woof",
                    "fox_girl",
                    "avatar",
                    "cuddle",
                    "hug",
                    "kiss",
                    "spank",
                    "feed",
                ]
            )
        )
    )

    msg_pattern = re.compile(
        rf"^({'|'.join(re.escape(tag) for tag in tags)})$", re.IGNORECASE
    )
    cb_pattern = re.compile(r"^animepic/next/(.+)$")

    cmds = f"{{{', '.join(tags)}}}"
    desc = {
        "Info": "Sends anime pictures from multi API sources.",
        "e.g.": "waifu",
    }

    @handler(filters.regex(msg_pattern) & ~reply, 1)
    async def on_message_out(self, event: Message) -> None:
        await self.respond(event, "<code>...</code>")
        try:
            res = await event._client.get_inline_bot_results(
                self.client.bot.me.id, event.content, chat_id=event.chat.id
            )
            if not res.results:
                await self.respond(event, "<code>The bot returned no results.</code>")
                return

            await asyncio.gather(
                event.reply_inline_bot_result(
                    res.query_id,
                    res.results[0].id,
                    reply_parameters=ReplyParameters(
                        message_id=event.reply_to_message_id or event.id
                    ),
                ),
                event.delete(),
            )
        except Exception as e:
            await self.respond(event, f"<code>{html.escape(str(e))}</code>")

    @handler(filters.regex(msg_pattern), 2)
    async def on_inline_query(self, event: InlineQuery) -> None:
        tag = event.matches[0].group(1).lower()
        try:
            now = datetime.datetime.now(datetime.UTC)
            result = await self.get_image_url(tag)
            if not result:
                await event.answer([], cache_time=0)
                return

            await event.answer(
                [
                    InlineQueryResultPhoto(
                        photo_url=result[0],
                        caption=self.build_caption(self.fmtsec(now), *result[1:]),
                        reply_markup=self.build_keyboard(tag),
                    )
                ],
                cache_time=0,
            )
        except Exception:
            await event.answer([], cache_time=0)

    @handler(filters.regex(cb_pattern), 4)
    async def on_inline_callback(self, event: CallbackQuery) -> None:
        (tag,) = event.matches[0].groups()
        try:
            await event.answer("Refreshing...")
            now = datetime.datetime.now(datetime.UTC)
            result = await self.get_image_url(tag)
            if not result:
                await event.answer("Failed to get a new image.", show_alert=True)
                return

            await event.edit_message_media(
                media=InputMediaPhoto(
                    media=result[0],
                    caption=self.build_caption(self.fmtsec(now), *result[1:]),
                ),
                reply_markup=self.build_keyboard(tag),
            )
        except Exception as e:
            await event.answer(f"Error: {html.escape(str(e))}", show_alert=True)

    async def get_image_url(self, tag: str) -> tuple | None:
        apis_to_try = [
            (self.mwm_moe_tags, self._get_from_mwm_moe),
            (self.picre_tags, self._get_from_picre),
            (self.waifu_im_tags, self._get_from_waifu_im),
            (self.animepixels_tags, self._get_from_animepixels),
            (self.yandere_tags, self._get_from_yandere),
            (self.nekos_moe_tags, self._get_from_nekos_moe),
            (self.nekobot_tags, self._get_from_nekobot),
            (self.nekosapi_tags, self._get_from_nekosapi),
            (self.nekosia_tags, self._get_from_nekosia),
            (self.waifu_pics_tags, self._get_from_waifu_pics),
            (self.nekos_best_tags, self._get_from_nekos_best),
        ]

        for tags_list, api_func in apis_to_try:
            if tag in tags_list:
                try:
                    result = await api_func(tag)
                    if result:
                        return result
                except Exception:
                    continue

        try:
            for _ in range(3):
                resp = await self.client.http.get(
                    f"https://nekos.life/api/v2/img/{tag}", timeout=10
                )
                if resp.status_code == 200:
                    data = resp.json()
                    url = data.get("url")
                    if self._is_valid_non_gif(url):
                        return url, None, {}, None
                await asyncio.sleep(0.2)
        except Exception:
            return None

        return None

    @staticmethod
    def _is_valid_non_gif(url: str | None) -> bool:
        return bool(url and not url.lower().endswith(".gif"))

    async def _get_from_mwm_moe(self, tag: str) -> tuple | None:
        resp = await self.client.http.get(
            f"https://t.mwm.moe/{tag}", follow_redirects=True, timeout=10
        )
        url = str(resp.url) if resp.status_code == 200 else None
        if self._is_valid_non_gif(url):
            return url, None, {}, None
        return None

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
                return (
                    file_url,
                    data.get("author"),
                    {},
                    data.get("source"),
                )

        resp = await self.client.http.get(
            "https://pic.re/images", follow_redirects=True, timeout=10
        )
        url = str(resp.url) if resp.status_code == 200 else None
        if self._is_valid_non_gif(url):
            return url, None, {}, None
        return None

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
            key: val
            for key, val in {
                "Pixiv": artist.get("pixiv"),
                "Twitter": artist.get("twitter"),
                "Patreon": artist.get("patreon"),
                "DeviantArt": artist.get("deviantArt"),
            }.items()
            if val
        }
        return (
            url,
            artist.get("name"),
            links,
            image_data.get("source") or image_data.get("source_url"),
        )

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

            data = resp.json() or {}
            results = data.get("results") or []
            if not isinstance(results, list) or not results:
                return None
            data = results[0]
        else:
            resp = await self.client.http.get(
                "https://animepixels-api.vercel.app/api/media/random/image",
                timeout=10,
            )
            if resp.status_code != 200:
                return None
            data = resp.json() or {}

        url = data.get("url")
        if not self._is_valid_non_gif(url):
            return None

        return (url, None, {}, None)

    async def _get_from_yandere(self, tag: str) -> tuple | None:
        tag_filter = None if tag in {"yande", "yandere"} else tag
        query_tags = "rating:safe order:random"
        if tag_filter:
            query_tags = f"{query_tags} {tag_filter}"

        resp = await self.client.http.get(
            "https://yande.re/post.json",
            params={"limit": 1, "tags": query_tags},
            timeout=10,
        )
        if resp.status_code != 200:
            return None

        posts = resp.json() or []
        # Fall back to plain safe random if the specific tag has no safe post.
        if tag_filter and (not isinstance(posts, list) or not posts):
            resp = await self.client.http.get(
                "https://yande.re/post.json",
                params={"limit": 1, "tags": "rating:safe order:random"},
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
        source_url = post.get("source") or (
            f"https://yande.re/post/show/{post_id}" if post_id else None
        )
        return (url, post.get("author"), {}, source_url)

    async def _get_from_nekos_moe(self, _: str) -> tuple | None:
        resp = await self.client.http.get(
            "https://nekos.moe/api/v1/random/image",
            params={"nsfw": "false"},
            timeout=10,
        )
        if resp.status_code != 200:
            return None

        images = resp.json().get("images") or []
        if not images:
            return None

        image_id = images[0].get("id")
        if not image_id:
            return None

        return (
            f"https://nekos.moe/image/{image_id}",
            images[0].get("artist"),
            {},
            f"https://nekos.moe/post/{image_id}",
        )

    async def _get_from_nekobot(self, tag: str) -> tuple | None:
        api_category = "hololewd" if tag == "holo" else tag
        resp = await self.client.http.get(
            "https://nekobot.xyz/api/image",
            params={"type": api_category},
            timeout=10,
        )
        if resp.status_code != 200:
            return None

        data = resp.json()
        url = data.get("message") if data.get("success") else None
        if self._is_valid_non_gif(url):
            return url, None, {}, None
        return None

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

        image_data = images[0]
        url = image_data.get("url")
        if not self._is_valid_non_gif(url):
            return None

        return (
            url,
            image_data.get("artist_name"),
            {},
            image_data.get("source_url"),
        )

    async def _get_from_nekosia(self, tag: str) -> tuple | None:
        resp = await self.client.http.get(
            f"https://api.nekosia.cat/api/v1/images/{tag}", timeout=10
        )
        if resp.status_code != 200:
            resp = await self.client.http.get(
                "https://api.nekosia.cat/api/v1/images/random",
                params={"tag": tag},
                timeout=10,
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
        links = {}
        if artist.get("profile"):
            links["Profile"] = artist["profile"]

        return (url, artist.get("username"), links, source.get("url"))

    async def _get_from_waifu_pics(self, tag: str) -> tuple | None:
        resp = await self.client.http.get(
            f"https://api.waifu.pics/sfw/{tag}", timeout=10
        )
        if resp.status_code != 200:
            return None

        url = resp.json().get("url")
        if self._is_valid_non_gif(url):
            return url, None, {}, None
        return None

    async def _get_from_nekos_best(self, tag: str) -> tuple | None:
        resp = await self.client.http.get(f"https://nekos.best/api/v2/{tag}", timeout=10)
        if resp.status_code != 200:
            return None

        result = (resp.json().get("results") or [{}])[0]
        url = result.get("url")
        if not self._is_valid_non_gif(url):
            return None

        links = {}
        if result.get("artist_href"):
            links["Profile"] = result["artist_href"]

        return (url, result.get("artist_name"), links, result.get("source_url"))

    def build_keyboard(self, tag: str):
        return self.ikm(
            [
                [
                    ("Refresh", "data", f"animepic/next/{tag}", "G"),
                    ("Close", "data", b"0", "R"),
                ]
            ]
        )

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
                links = []
                for name, url in artist_links.items():
                    if url:
                        links.append(f'<a href="{url}">{html.escape(name)}</a>')
                if links:
                    artist = f"{artist} ({' | '.join(links)})"
            parts.append(artist)

        if source_url:
            parts.append(f'<a href="{source_url}">Source</a>')

        info = " | ".join(parts)
        if info:
            return f"{info}\n<b><blockquote>{rtt}</blockquote></b>"
        return f"<b><blockquote>{rtt}</blockquote></b>"
