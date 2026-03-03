"""Compatibility wrapper. Prefer importing from src.bot.vision.detect_monsters."""
from src.bot.vision.detect_monsters import *  # noqa: F401,F403

if __name__ == "__main__":
    # Delegate CLI behavior to the new module.
    import runpy
    runpy.run_module("src.bot.vision.detect_monsters", run_name="__main__")
