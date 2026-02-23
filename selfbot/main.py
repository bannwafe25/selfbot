import asyncio
import logging
import os

from .core import Selfbot

logging.basicConfig(
    format="%(asctime)s,%(msecs)03d [ %(levelname).1s ] %(name)s: %(message)s",
    datefmt="%b %-d | %-I:%M %p | %-S",
    level=logging.INFO,
)
for lib in ("pyrogram", "httpx"):
    logging.getLogger(lib).setLevel(logging.ERROR)


def run() -> None:
    mongo_uri = os.environ.get("MONGODB_URI") or os.environ.get("DATABASE_URL")
    config = {
        "BOT_TOKEN": os.environ.get("BOT_TOKEN"),
        "MONGODB_URI": mongo_uri,
        "GEMINI_API_KEY": os.environ.get("GEMINI_API_KEY"),
        "FERDEV_API_KEY": os.environ.get("FERDEV_API_KEY"),
        "IMGUR_CLIENT_ID": os.environ.get("IMGUR_CLIENT_ID"),
        "IMGBB_API_KEY": os.environ.get("IMGBB_API_KEY"),
        "STICKER_FILE_ID": os.environ.get(
            "STICKER_FILE_ID",
            "CAACAgIAAxkBAAIdeWi1SLWihwZEeyFOk9YM4-mBWJqxAAJOAgACVp29CjD-a22BMgNvHgQ",
        ),
    }
    with asyncio.Runner() as runner:
        runner.run(Selfbot.launch(config, runner.get_loop()))


if __name__ == "__main__":
    run()
