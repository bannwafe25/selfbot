import abc

from pymongo import AsyncMongoClient


class Database(abc.ABC):
    def __init__(self, **kwargs) -> None:
        self.db = None
        self._mongo_client = None
        super().__init__(**kwargs)

    async def initdb(self) -> None:
        try:
            self._mongo_client = AsyncMongoClient(self.config["DATABASE_URL"])
            from pymongo.errors import ConfigurationError
            try:
                db_name = self._mongo_client.get_database().name
            except ConfigurationError:
                db_name = "selfbot"
            self.db = self._mongo_client[db_name]
            
            # optional: simple ping to verify connection
            await self._mongo_client.admin.command('ping')
        except Exception as e:
            self.logger.error(f"{e.__class__.__name__}: {e}")
            raise

        self.config.pop("DATABASE_URL", None)

    async def close(self) -> None:
        if self._mongo_client:
            self._mongo_client.close()
