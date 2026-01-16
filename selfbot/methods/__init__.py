from .debug import Debug
from .format import Format
from .telegram import Telegram

__all__ = ["Methods"]


class Methods(Debug, Format, Telegram): ...
