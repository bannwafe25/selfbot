import os
import tomllib


def version():
    path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "pyproject.toml"
    )
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)

        return data.get("project", {}).get("version", "0.0.0")
    except Exception:
        return "0.0.0"


__version__ = version()

__all__ = ["__version__"]
