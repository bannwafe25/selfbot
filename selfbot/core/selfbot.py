import asyncio
import logging
import pathlib

from httpx import AsyncClient

from .database import Database
from .dispatcher import Dispatcher
from .extender import Extender
from .telegram import Telegram


class Selfbot(Database, Dispatcher, Extender, Telegram):
    def __init__(self, config: dict) -> None:
        self.config = config
        self.logger = logging.getLogger("Selfbot")
        super().__init__()

    @classmethod
    async def launch(cls, config: dict) -> "Selfbot":
        selfbot = cls(config)
        try:
            selfbot.http = AsyncClient(timeout=900)
            await selfbot.run()
        finally:
            loop = asyncio.get_running_loop()
            if loop and not loop.is_closed():
                loop.call_soon(loop.stop)

        return selfbot

    async def stop(self) -> None:
        self.logger.info("Stopping Selfbot...")
        try:
            res = await asyncio.gather(
                *[
                    self.dispatch("stopping"),
                    self.app.stop(),
                    self.bot.stop(),
                    self.http.close(),
                ],
                return_exceptions=True,
            )
            for i in res:
                if isinstance(i, Exception):
                    self.logger.error(f"{i.__class__.__name__}: {i}")

            try:
                await self.db.close()
            except Exception:
                pass
        except Exception as e:
            self.logger.error(f"{e.__class__.__name__}: {e}")

    @property
    def _git(self) -> str:
        cur = pathlib.Path.cwd().resolve()
        while cur != cur.parent:
            if (cur / ".git").is_dir():
                return str(cur)

            cur = cur.parent

        return str(pathlib.Path.cwd())
