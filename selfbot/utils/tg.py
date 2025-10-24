import struct

from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram.utils import (
    MIN_MONOFORUM_CHANNEL_ID,
    get_channel_id,
    unpack_inline_message_id,
)


def ids(inline_message_id: str) -> tuple:
    data = unpack_inline_message_id(inline_message_id)
    try:
        cid, mid = data.owner_id, data.id
    except AttributeError:
        cid, mid = struct.unpack(">ii", data.id.to_bytes(8, signed=True))

    if cid < 0 or cid >= MIN_MONOFORUM_CHANNEL_ID:
        cid = get_channel_id(abs(cid))

    return cid, mid


def ikm(rows: list | tuple) -> InlineKeyboardMarkup:
    if isinstance(rows, tuple):
        rows = [[rows]]

    if isinstance(rows, list) and isinstance(rows[0], tuple):
        rows = [rows]

    ikb = []
    for row in rows:
        line = []
        for i in row:
            args, last = {"text": i[0]}, i[-1]
            if len(i) == 2:
                args["callback_data"] = last
            elif len(i) == 3:
                args[i[1]] = last
            else:
                raise ValueError

            line.append(InlineKeyboardButton(**args))

        ikb.append(line)

    return InlineKeyboardMarkup(ikb)
