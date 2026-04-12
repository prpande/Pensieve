"""Tests for pensieve.config — global user config I/O."""

from __future__ import annotations

from pathlib import Path

import pytest

from pensieve import config as cfg
from pensieve.config import ConfigError


@pytest.fixture
def fake_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect CONFIG_PATH under tmp_path so tests never touch real ~/.pensieve."""
    fake_config = tmp_path / "home" / ".pensieve" / "config.toml"
    monkeypatch.setattr(cfg, "CONFIG_PATH", fake_config)
    return fake_config


def test_config_error_is_exception() -> None:
    err = ConfigError("boom")
    assert isinstance(err, Exception)
    assert str(err) == "boom"


def test_schema_version_constant() -> None:
    assert cfg.SCHEMA_VERSION == 1
