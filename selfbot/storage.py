import asyncio
import time

from pymongo import DeleteOne, UpdateOne
from pyrogram.raw.base import InputPeer
from pyrogram.raw.types import InputPeerChannel, InputPeerChat, InputPeerUser
from pyrogram.storage import Storage
from pyrogram.utils import get_channel_id

Object = object()


def get_input_peer(peer_id: int, access_hash: int, peer_type: str) -> InputPeer:
    if peer_type in ("user", "bot"):
        return InputPeerUser(user_id=peer_id, access_hash=access_hash)

    if peer_type == "group":
        return InputPeerChat(chat_id=-peer_id)

    if peer_type in ("channel", "supergroup"):
        return InputPeerChannel(
            channel_id=get_channel_id(peer_id), access_hash=access_hash
        )

    raise ValueError(f"Invalid peer type: {peer_type}")


class MongoStorage(Storage):
    def __init__(self, name: str, db) -> None:
        super().__init__()
        self.name = name
        self.db = db

    async def open(self) -> None:
        await self.db.sessions.update_one(
            {"name": self.name},
            {"$setOnInsert": {"dc_id": 2, "date": 0}},
            upsert=True,
        )

        try:
            await self.db.peers.create_index([("name", 1), ("id", 1)], unique=True)
            await self.db.peers.create_index([("name", 1), ("phone_number", 1)])
            await self.db.usernames.create_index(
                [("name", 1), ("id", 1)], unique=True
            )
            await self.db.update_state.create_index(
                [("name", 1), ("id", 1)], unique=True
            )
        except Exception:
            pass

    async def save(self) -> None:
        await self.date(int(time.time()))

    async def close(self) -> None: ...

    async def delete(self) -> None:
        await asyncio.gather(
            self.db.sessions.delete_many({"name": self.name}),
            self.db.peers.delete_many({"name": self.name}),
            self.db.update_state.delete_many({"name": self.name}),
        )

    async def update_peers(self, peers: list | None = None) -> None:
        if not peers:
            return

        peer_records = []
        username_records = []
        delete_username_requests = []
        for p_id, p_access_hash, p_type, p_phone_number in peers:
            delete_username_requests.append(DeleteOne({"name": self.name, "id": p_id}))
            peer_records.append(
                UpdateOne(
                    {"name": self.name, "id": p_id},
                    {
                        "$set": {
                            "access_hash": p_access_hash,
                            "type": p_type,
                            "phone_number": p_phone_number,
                        }
                    },
                    upsert=True,
                )
            )
            if p_phone_number:
                username_records.append(
                    UpdateOne(
                        {"name": self.name, "id": p_id},
                        {"$set": {"phone_number": p_phone_number}},
                        upsert=True,
                    )
                )

        if delete_username_requests:
            await self.db.usernames.bulk_write(delete_username_requests, ordered=False)

        if peer_records:
            await self.db.peers.bulk_write(peer_records, ordered=False)

        if username_records:
            await self.db.usernames.bulk_write(username_records, ordered=False)

    async def update_usernames(self, usernames: list | None = None) -> None: ...

    async def update_state(self, value: object = Object) -> list | None:
        if value is Object:
            cursor = self.db.update_state.find({"name": self.name})
            res = []
            async for doc in cursor:
                res.append(
                    (
                        doc.get("id"),
                        doc.get("pts"),
                        doc.get("qts"),
                        doc.get("date"),
                        doc.get("seq"),
                    )
                )
            return res

        if value is None:
            await self.db.update_state.delete_many({"name": self.name})
        else:
            await self.db.update_state.update_one(
                {"name": self.name, "id": value[0]},
                {
                    "$set": {
                        "pts": value[1],
                        "qts": value[2],
                        "date": value[3],
                        "seq": value[4],
                    }
                },
                upsert=True,
            )

        return None

    async def get_peer_by_id(self, peer_id: int | str) -> InputPeer:
        if isinstance(peer_id, str):
            try:
                peer_id = int(peer_id)
            except (ValueError, TypeError) as e:
                raise KeyError(f"Invalid peer ID: {peer_id}") from e

        doc = await self.db.peers.find_one({"name": self.name, "id": peer_id})
        if not doc:
            raise KeyError(f"Peer ID not found: {peer_id}")

        return get_input_peer(doc["id"], doc["access_hash"], doc["type"])

    async def get_peer_by_username(self, username: str) -> InputPeer:
        u_doc = await self.db.usernames.find_one(
            {"name": self.name, "username": username}
        )
        if not u_doc:
            raise KeyError(f"Username not found: {username}")

        p_doc = await self.db.peers.find_one({"name": self.name, "id": u_doc["id"]})
        if not p_doc:
            raise KeyError(f"Username not found: {username}")

        return get_input_peer(p_doc["id"], p_doc["access_hash"], p_doc["type"])

    async def get_peer_by_phone_number(self, phone_number: str) -> InputPeer:
        doc = await self.db.peers.find_one(
            {"name": self.name, "phone_number": phone_number}
        )
        if not doc:
            raise KeyError(f"Phone number not found: {phone_number}")

        return get_input_peer(doc["id"], doc["access_hash"], doc["type"])

    async def dc_id(self, value: object = Object) -> int | None:
        res = await self._value("dc_id", value)
        return res if value is Object else None

    async def api_id(self, value: object = Object) -> int | None:
        res = await self._value("api_id", value)
        return res if value is Object else None

    async def test_mode(self, value: object = Object) -> bool | None:
        res = await self._value("test_mode", value)
        return res if value is Object else None

    async def auth_key(self, value: object = Object) -> bytes | None:
        res = await self._value("auth_key", value)
        return res if value is Object else None

    async def date(self, value: object = Object) -> int | None:
        res = await self._value("date", value)
        return res if value is Object else None

    async def user_id(self, value: object = Object) -> int | None:
        res = await self._value("user_id", value)
        return res if value is Object else None

    async def is_bot(self, value: object = Object) -> bool | None:
        res = await self._value("is_bot", value)
        return res if value is Object else None

    async def set_update_state(self, update_state) -> None:
        from pyrogram.storage.storage import UpdateState

        states = (
            update_state
            if isinstance(update_state, (list, tuple))
            else [update_state]
        )
        for st in states:
            await self.db.update_state.update_one(
                {"name": self.name, "id": st.id},
                {"$set": {"pts": st.pts, "qts": st.qts,
                          "date": st.date, "seq": st.seq}},
                upsert=True,
            )

    async def get_update_states(self, ids=None) -> list:
        query = {"name": self.name}
        if ids is not None:
            if isinstance(ids, int):
                ids = [ids]
            query["id"] = {"$in": list(ids)}

        from pyrogram.storage.storage import UpdateState

        res = []
        cursor = self.db.update_state.find(query)
        async for doc in cursor:
            res.append(
                UpdateState(
                    id=doc.get("id"),
                    pts=doc.get("pts"),
                    qts=doc.get("qts"),
                    date=doc.get("date"),
                    seq=doc.get("seq"),
                )
            )
        return res

    async def delete_update_state(self, state_id) -> None:
        if isinstance(state_id, int):
            state_id = [state_id]
        await self.db.update_state.delete_many(
            {"name": self.name, "id": {"$in": list(state_id)}}
        )

    async def port(self, value: object = Object) -> int | None:
        res = await self._value("port", value)
        return res if value is Object else None

    async def server_address(self, value: object = Object) -> str | None:
        res = await self._value("server_address", value)
        return res if value is Object else None

    async def _value(self, attr: str, value: object = Object) -> object:
        if value is Object:
            doc = await self.db.sessions.find_one({"name": self.name})
            return doc.get(attr) if doc else None

        if attr in ("is_bot", "test_mode") and not isinstance(value, bool):
            value = bool(value)

        await self.db.sessions.update_one(
            {"name": self.name}, {"$set": {attr: value}}, upsert=True
        )
        return None
