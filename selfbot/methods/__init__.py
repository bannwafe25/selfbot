from .debug import Debug
from .format import Format
from .settings import Settings
from .telegram import Telegram

__all__ = ["Methods"]


class Methods(Debug, Format, Settings, Telegram): ...
