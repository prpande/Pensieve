"""Pensieve user-level configuration.

A single TOML file at ~/.pensieve/config.toml is the contract between the
pensieve CLI and any external tool (e.g. the slack-scrape skill) that needs
to know where the wiki lives.
"""

from __future__ import annotations

from pathlib import Path

SCHEMA_VERSION = 1
CONFIG_PATH = Path.home() / ".pensieve" / "config.toml"


class ConfigError(Exception):
    """Raised when the user-level Pensieve config is missing or invalid."""
