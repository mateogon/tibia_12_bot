"""Application entrypoints for bot runtime."""

from __future__ import annotations

from .runner import BotRunner


class BotApp:
    """High-level app object wiring construction and runtime loop."""

    def __init__(self, bot_factory=None) -> None:
        self.bot_factory = bot_factory

    def run(self):
        if self.bot_factory is None:
            from .factory import create_bot

            self.bot_factory = create_bot
        bot = self.bot_factory()
        return BotRunner(bot).run()


def run():
    """Default CLI/runtime entrypoint."""
    return BotApp().run()
