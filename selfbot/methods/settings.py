import datetime
import os
import re


class Settings:
    secret_markers = (
        "KEY",
        "TOKEN",
        "SECRET",
        "PASS",
        "PASSWORD",
        "AUTH",
        "SESSION",
        "COOKIE",
    )

    @staticmethod
    def normalize_key(key: str) -> str:
        return key.strip().upper()

    @classmethod
    def is_secret_key(cls, key: str) -> bool:
        upper = cls.normalize_key(key)
        return any(marker in upper for marker in cls.secret_markers)

    @staticmethod
    def mask_value(value: object, keep: int = 4) -> str:
        text = str(value)
        if not text:
            return "-"
        if len(text) <= keep * 2:
            return "*" * len(text)
        return f"{text[:keep]}...{text[-keep:]}"

    async def getvar(self, key: str, default: object = None) -> object:
        norm = self.normalize_key(key)
        row = await self.client.db.settings_vars.find_one({"key": norm})
        if row and row.get("value") not in (None, ""):
            return row["value"]

        value = self.client.config.get(norm)
        if value not in (None, ""):
            return value

        env_value = os.environ.get(norm)
        if env_value:
            return env_value

        return default

    async def setvar(self, key: str, value: object) -> str:
        norm = self.normalize_key(key)
        await self.client.db.settings_vars.update_one(
            {"key": norm},
            {
                "$set": {
                    "key": norm,
                    "value": str(value),
                    "updated_at": datetime.datetime.now(datetime.UTC),
                }
            },
            upsert=True,
        )
        return norm

    async def delvar(self, key: str) -> int:
        norm = self.normalize_key(key)
        result = await self.client.db.settings_vars.delete_one({"key": norm})
        return result.deleted_count

    async def listvars(self, key_filter: str = "") -> list[dict]:
        query = {}
        if key_filter:
            query["key"] = {"$regex": re.escape(key_filter), "$options": "i"}

        rows = []
        cursor = self.client.db.settings_vars.find(query).sort("key", 1)
        async for row in cursor:
            rows.append(row)
        return rows
