"""Pensieve user-level configuration.

A single TOML file at ~/.pensieve/config.toml is the contract between the
pensieve CLI and any external tool (e.g. the slack-scrape skill) that needs
to know where the wiki lives.
"""

from __future__ import annotations

import os
from pathlib import Path

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]

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
    try:
        tmp_path.write_text(contents, encoding="utf-8")
        os.replace(tmp_path, CONFIG_PATH)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


def load_config() -> dict:
    """Load and validate the user-level Pensieve config.

    Raises ConfigError with a human-friendly message on any problem.
    Validation here is purely about the config file itself — it does NOT
    check that wiki_root exists on disk. Use get_wiki_root() for that.
    """
    if not CONFIG_PATH.exists():
        raise ConfigError(
            "Pensieve is not initialised. Run 'pensieve init <path>' first."
        )
    try:
        with CONFIG_PATH.open("rb") as fh:
            data = tomllib.load(fh)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"Invalid config at {CONFIG_PATH}: {exc}") from exc

    schema_version = data.get("schema_version", 0)
    if isinstance(schema_version, int) and schema_version > SCHEMA_VERSION:
        raise ConfigError(
            f"Config schema version {schema_version} is newer than this "
            f"Pensieve ({SCHEMA_VERSION}). Upgrade pensieve."
        )

    wiki_root = data.get("wiki_root")
    if not wiki_root:
        raise ConfigError(
            "Config is missing 'wiki_root'. Re-run 'pensieve init <path>'."
        )

    return data
