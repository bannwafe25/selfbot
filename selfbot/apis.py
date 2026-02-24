# Centralized API URL registry.
# Modules should import URLs from here instead of hardcoding them.
# This makes it easy to update endpoints in one place.

# ── Deline APIs ──────────────────────────────────────────────────────
DELINE_BASE = "https://api.deline.web.id"
DELINE_BRAT = f"{DELINE_BASE}/maker/brat"
DELINE_BRATVID = f"{DELINE_BASE}/maker/bratvid"
DELINE_CEWEKBRAT = f"{DELINE_BASE}/maker/cewekbrat"
DELINE_ASUPAN = f"{DELINE_BASE}/random/asupan"
DELINE_REMOVEBG = f"{DELINE_BASE}/tools/removebg"
DELINE_YTMP3 = f"{DELINE_BASE}/downloader/ytmp3"
DELINE_RANDOM_BA = f"{DELINE_BASE}/random/ba"
DELINE_RANDOM_LOLI = f"{DELINE_BASE}/random/loli"
DELINE_SCREENSHOT = f"{DELINE_BASE}/tools/screenshot"
DELINE_PPCOUPLE = f"{DELINE_BASE}/random/ppcouple"

# ── Ferdev APIs ──────────────────────────────────────────────────────
FERDEV_ANIMEQUOTE = "https://api.ferdev.my.id/random/animequote"
FERDEV_APIKEY = "key_iOPE5w"
FERDEV_YTMP3 = "https://api.ferdev.my.id/downloader/ytmp3"

# ── Sanka Vollerei APIs ──────────────────────────────────────────────
SANKA_ANIMEQUOTE = "https://www.sankavollerei.com/anime/quote"
SANKA_APIKEY = "planaai"

# ── Chocomilk APIs ───────────────────────────────────────────────────
CHOCOMILK_AIO = "https://chocomilk.amira.us.kg/v1/download/aio"

# ── Quotes API ───────────────────────────────────────────────────────
QUOTES_API = "https://quotes-o042.onrender.com/generate"

# ── ImgBB ────────────────────────────────────────────────────────────
IMGBB_UPLOAD = "https://api.imgbb.com/1/upload"

# ── File Upload Services (for risearch, etc.) ────────────────────────
UPLOAD_0X0 = "https://0x0.st"
UPLOAD_TMPFILES = "https://tmpfiles.org/api/v1/upload"
UPLOAD_CATBOX = "https://catbox.moe/user/api.php"

# ── Reverse Image Search Engines ─────────────────────────────────────
SEARCH_ENGINES = {
    "lens": "https://lens.google.com/uploadbyurl?url={image}",
    "reverse": "https://www.google.com/searchbyimage?sbisrc=4chanx&image_url={image}&safe=off",
    "tineye": "https://www.tineye.com/search?url={image}",
    "bing": "https://www.bing.com/images/search?view=detailv2&iss=sbi&form=SBIVSP&sbisrc=UrlPaste&q=imgurl:{image}",
    "yandex": "https://yandex.com/images/search?source=collections&url={image}&rpt=imageview",
    "saucenao": "https://saucenao.com/search.php?db=999&url={image}",
}

# ── Misc ─────────────────────────────────────────────────────────────
SANGMATA_USERNAME = "@SangMata_beta_bot"
YASIR_REGDATE = "https://yasirapi.eu.org/register_date"
