from .debug import Debug
from .fmt import Format
from .tg import Telegram

__all__ = ["Utils"]


class Utils(Debug, Format, Telegram):
    pass
