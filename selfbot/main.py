import asyncio
import logging
import os

try:
    import uvloop
except ImportError:
    loop = asyncio.new_event_loop()
else:
    loop = uvloop.new_event_loop()
finally:
    asyncio.set_event_loop(loop)

from .core import Selfbot

logging.basicConfig(
    format="%(asctime)s,%(msecs)03d [ %(levelname).1s ] %(name)s: %(message)s",
    datefmt="%b %-d | %-I:%M %p | %-S",
    level=logging.INFO,
)
for lib in ("pyrogram", "httpx"):
    logging.getLogger(lib).setLevel(logging.ERROR)


def run() -> None:
    config = {
        "BOT_TOKEN": os.environ.get("BOT_TOKEN"),
        "DATABASE_URL": os.environ.get("DATABASE_URL"),
        "GEMINI_API_KEY": os.environ.get("GEMINI_API_KEY"),
        "GEMINI_MODEL": os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"),
        "STICKER_FILE_ID": os.environ.get(
            "STICKER_FILE_ID",
            "CAACAgIAAxkBAAIdeWi1SLWihwZEeyFOk9YM4-mBWJqxAAJOAgACVp29CjD-a22BMgNvHgQ",
        ),
    }
    try:
        loop.run_until_complete(Selfbot.launch(config, loop))
    except RuntimeError as e:
        logging.critical(f"{e.__class__.__name__}: {e}")
    finally:
        if loop and not loop.is_closed():
            loop.close()


if __name__ == "__main__":
    run()
