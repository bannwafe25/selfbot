class Module:
    name = ""

    cmds = ""
    desc = None

    def __init__(self, client: type) -> None:
        self.client = client


class ModuleError(Exception):
    pass


class ModuleExists(ModuleError):
    def __init__(self, mod: "Module") -> None:
        super().__init__(f"'{mod.name}' Exists")
