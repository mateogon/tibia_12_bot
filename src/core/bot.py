"""Bot class compatibility module.

This keeps imports stable while we incrementally split the legacy runtime.
"""

from .bot_runtime import Bot

__all__ = ["Bot"]
