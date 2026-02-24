import logging
import typing

from selfbot.methods import Methods

if typing.TYPE_CHECKING:
    from selfbot.core import Selfbot


class Module(Methods):
    name = "Module"
    cmds = ""
    desc = None

    def __init__(self, client: Selfbot) -> None:
        self.client = client
        self.logger = logging.getLogger(self.__class__.__name__)

    @staticmethod
    def to_bytes(data: object) -> bytes:
        if data is None:
            return b""
        if isinstance(data, bytes):
            return data
        if isinstance(data, (bytearray, memoryview)):
            return bytes(data)
        if hasattr(data, "getbuffer"):
            return bytes(data.getbuffer())
        if hasattr(data, "read"):
            return data.read()
        return bytes(data)

    @staticmethod
    def message_text(message: object) -> str:
        if message is None:
            return ""

        for attr in ("text", "caption"):
            value = getattr(message, attr, None)
            if value:
                return str(value)

        content = getattr(message, "content", None)
        if not content:
            return ""
        if isinstance(content, str):
            return content
        markdown = getattr(content, "markdown", None)
        if markdown:
            return str(markdown)
        html = getattr(content, "html", None)
        if html:
            return str(html)
        return str(content)


class ModuleError(Exception): ...


class ModuleExists(ModuleError):
    def __init__(self, obj: type) -> None:
        super().__init__(f"Module '{obj.__name__}' Exists")
