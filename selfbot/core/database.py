import abc

from asyncpg import create_pool

schema = """
CREATE SCHEMA IF NOT EXISTS restart;
CREATE TABLE IF NOT EXISTS restart.msgs(
    chat_id     BIGINT,
    message_id  INT
);
"""


class Database(abc.ABC):
    def __init__(self, **kwargs: any) -> None:
        self.db = None
        super().__init__(**kwargs)

    async def initdb(self) -> None:
        self.db = await create_pool(self.config["database_url"])
        await self.db.execute(schema)
