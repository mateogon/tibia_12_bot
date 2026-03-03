"""Bot construction helpers."""

from __future__ import annotations

from .bot_runtime import Bot


def create_bot() -> Bot:
    """Create a fully initialized bot instance."""
    return Bot()
