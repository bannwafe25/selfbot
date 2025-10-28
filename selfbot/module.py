import logging
import typing

if typing.TYPE_CHECKING:
    from selfbot.core import Selfbot


class Module:
    name = ""

    cmds = ""
    desc = None

    def __init__(self, client: "Selfbot") -> None:
        self.client = client
        self.logger = logging.getLogger(self.__class__.__name__)


class ModuleError(Exception):
    pass


class ModuleExists(ModuleError):
    def __init__(self, mod: "Module") -> None:
        super().__init__(f"'{mod.name}' Exists")
