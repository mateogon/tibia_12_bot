"""Compatibility entrypoint for the refactored bot runtime."""

from typing import TYPE_CHECKING

from src.core.app import run

if TYPE_CHECKING:
    from src.core.bot import Bot as Bot


def __getattr__(name):
    if name == "Bot":
        from src.core.bot import Bot as _Bot

        return _Bot
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


if __name__ == "__main__":
    run()
