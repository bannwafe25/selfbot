import abc
import inspect
from urllib.parse import urlparse

from pymongo import AsyncMongoClient
from pymongo.errors import ConfigurationError


class Database(abc.ABC):
    def __init__(self, **kwargs) -> None:
        self.db = None
        self._mongo_client = None
        super().__init__(**kwargs)

    @staticmethod
    def _is_valid_mongo_uri(uri: str) -> bool:
        return urlparse(uri).scheme in {"mongodb", "mongodb+srv"}

    async def initdb(self) -> None:
        uri = self.config.get("MONGODB_URI")
        if not uri:
            raise ValueError("MONGODB_URI is required")

        if not self._is_valid_mongo_uri(uri):
            raise ValueError(
                "Invalid MONGODB_URI scheme. Use mongodb:// or mongodb+srv://"
            )

        try:
            self._mongo_client = AsyncMongoClient(uri)
            try:
                db_name = self._mongo_client.get_database().name
            except ConfigurationError:
                db_name = "selfbot"
            self.db = self._mongo_client[db_name]

            # optional: simple ping to verify connection
            await self._mongo_client.admin.command("ping")
        except Exception as e:
            self.logger.error(f"{e.__class__.__name__}: {e}")
            raise

        self.config.pop("MONGODB_URI", None)
        self.config.pop("DATABASE_URL", None)

    async def close(self) -> None:
        if self._mongo_client:
            close_result = self._mongo_client.close()
            if inspect.isawaitable(close_result):
                await close_result
