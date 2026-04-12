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


def test_write_config_creates_parent_dir(fake_home: Path, tmp_path: Path) -> None:
    wiki_root = tmp_path / "mywiki"
    wiki_root.mkdir()
    cfg.write_config(wiki_root)
    assert fake_home.exists()
    assert fake_home.parent.is_dir()


def test_write_config_writes_valid_toml(fake_home: Path, tmp_path: Path) -> None:
    wiki_root = tmp_path / "mywiki"
    wiki_root.mkdir()
    cfg.write_config(wiki_root)
    text = fake_home.read_text(encoding="utf-8")
    assert "schema_version = 1" in text
    assert f'wiki_root = "{wiki_root.as_posix()}"' in text


def test_write_config_overwrites_existing(fake_home: Path, tmp_path: Path) -> None:
    wiki_a = tmp_path / "wiki-a"
    wiki_b = tmp_path / "wiki-b"
    wiki_a.mkdir()
    wiki_b.mkdir()
    cfg.write_config(wiki_a)
    cfg.write_config(wiki_b)
    text = fake_home.read_text(encoding="utf-8")
    assert wiki_b.as_posix() in text
    assert wiki_a.as_posix() not in text


def test_write_config_no_temp_file_left_behind(fake_home: Path, tmp_path: Path) -> None:
    wiki_root = tmp_path / "mywiki"
    wiki_root.mkdir()
    cfg.write_config(wiki_root)
    leftovers = list(fake_home.parent.glob("*.tmp"))
    assert leftovers == []


def test_write_config_cleans_up_temp_on_failure(
    fake_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If write or replace fails, the temp file must not be left on disk."""
    import os as _os

    wiki_root = tmp_path / "mywiki"
    wiki_root.mkdir()

    real_replace = _os.replace

    def boom(src, dst):
        raise OSError("simulated replace failure")

    monkeypatch.setattr("pensieve.config.os.replace", boom)

    with pytest.raises(OSError, match="simulated replace failure"):
        cfg.write_config(wiki_root)

    leftovers = list(fake_home.parent.glob("*.tmp"))
    assert leftovers == []
