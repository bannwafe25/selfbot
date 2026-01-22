import logging
import typing

from selfbot.methods import Methods

if typing.TYPE_CHECKING:
    from selfbot.core import Selfbot


class Module(Methods):
    name = "Module"
    cmds = ""
    desc = None

    def __init__(self, client: "Selfbot") -> None:
        self.client = client
        self.logger = logging.getLogger(self.__class__.__name__)


class ModuleError(Exception):
    pass


class ModuleExists(ModuleError):
    def __init__(self, obj: type) -> None:
        super().__init__(f"Module '{obj.__name__}' Exists")
