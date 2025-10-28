from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from selfbot import Selfbot


class Module:
    name = ""

    cmds = ""
    desc = None

    def __init__(self, client: "Selfbot") -> None:
        self.client = client


class ModuleError(Exception):
    pass


class ModuleExists(ModuleError):
    def __init__(self, mod: "Module") -> None:
        super().__init__(f"'{mod.name}' Exists")
