"""Compatibility wrapper for previous core module path.

Prefer importing from src.bot.core.bot_runtime.
"""

from .bot_runtime import *  # noqa: F401,F403


if __name__ == "__main__":
    main()
