"""Pensieve user-level configuration.

A single TOML file at ~/.pensieve/config.toml is the contract between the
pensieve CLI and any external tool (e.g. the slack-scrape skill) that needs
to know where the wiki lives.
"""

from __future__ import annotations

import os
from pathlib import Path

SCHEMA_VERSION = 1
CONFIG_PATH = Path.home() / ".pensieve" / "config.toml"


class ConfigError(Exception):
    """Raised when the user-level Pensieve config is missing or invalid."""


def write_config(wiki_root: Path) -> None:
    """Write the user-level config pointing at *wiki_root*.

    Performs an atomic replace via os.replace() so concurrent readers either
    see the old file or the new file, never a partial write. Cross-platform
    safe — plain os.rename is not atomic on Windows when the destination
    already exists.
    """
    wiki_root = wiki_root.resolve()
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = CONFIG_PATH.with_suffix(CONFIG_PATH.suffix + ".tmp")
    contents = (
        f"schema_version = {SCHEMA_VERSION}\n"
        f'wiki_root = "{wiki_root.as_posix()}"\n'
    )
    tmp_path.write_text(contents, encoding="utf-8")
    os.replace(tmp_path, CONFIG_PATH)
