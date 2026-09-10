import asyncio
import logging

from httpx import AsyncClient, Timeout

from .database import Database
from .dispatcher import Dispatcher
from .extender import Extender
from .telegram import Telegram


class Selfbot(Database, Dispatcher, Extender, Telegram):
    def __init__(self, config: dict) -> None:
        self.config = config
        self.logger = logging.getLogger(self.__class__.__name__)
        super().__init__()

    @classmethod
    async def launch(
        cls,
        config: dict,
        loop: asyncio.AbstractEventLoop,
    ) -> Selfbot:

        selfbot = cls(config)

        try:
            selfbot.http = AsyncClient(
                http2=True,
                timeout=Timeout(timeout=None),
                follow_redirects=True,
            )

            selfbot.loop = loop

            await selfbot.run()

        finally:
            await selfbot.stop()

        return selfbot

    async def stop(self) -> None:
        try:
            tasks = [
                self.dispatch("stopping"),
                self.http.aclose(),
            ]

            if getattr(self, "app", None):
                tasks.append(self.app.stop())

            if getattr(self, "assistant", None):
                tasks.append(self.assistant.stop())

            if getattr(self, "bot", None):
                tasks.append(self.bot.stop())

            await asyncio.gather(
                *tasks,
                return_exceptions=True,
            )

            await self.close()

        except Exception as e:
            self.logger.error(
                f"{e.__class__.__name__}: {e}"
            )
            raise

        self.logger.info(
            f"{self.__class__.__name__} Stopped"
        )
