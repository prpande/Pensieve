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


def test_load_config_missing_file_raises(fake_home: Path) -> None:
    with pytest.raises(ConfigError) as exc:
        cfg.load_config()
    assert "not initialised" in str(exc.value)
    assert "pensieve init" in str(exc.value)


def test_load_config_round_trip(fake_home: Path, tmp_path: Path) -> None:
    wiki_root = tmp_path / "mywiki"
    wiki_root.mkdir()
    cfg.write_config(wiki_root)
    data = cfg.load_config()
    assert data["schema_version"] == 1
    assert data["wiki_root"] == wiki_root.as_posix()


def test_load_config_malformed_toml_raises(fake_home: Path) -> None:
    fake_home.parent.mkdir(parents=True, exist_ok=True)
    fake_home.write_text("this is = = not toml", encoding="utf-8")
    with pytest.raises(ConfigError) as exc:
        cfg.load_config()
    assert "Invalid config" in str(exc.value)


def test_load_config_missing_wiki_root_raises(fake_home: Path) -> None:
    fake_home.parent.mkdir(parents=True, exist_ok=True)
    fake_home.write_text("schema_version = 1\n", encoding="utf-8")
    with pytest.raises(ConfigError) as exc:
        cfg.load_config()
    assert "missing 'wiki_root'" in str(exc.value)


def test_load_config_empty_wiki_root_raises(fake_home: Path) -> None:
    fake_home.parent.mkdir(parents=True, exist_ok=True)
    fake_home.write_text('schema_version = 1\nwiki_root = ""\n', encoding="utf-8")
    with pytest.raises(ConfigError) as exc:
        cfg.load_config()
    assert "missing 'wiki_root'" in str(exc.value)


def test_load_config_future_schema_version_raises(fake_home: Path, tmp_path: Path) -> None:
    fake_home.parent.mkdir(parents=True, exist_ok=True)
    fake_home.write_text(
        f'schema_version = 99\nwiki_root = "{tmp_path.as_posix()}"\n',
        encoding="utf-8",
    )
    with pytest.raises(ConfigError) as exc:
        cfg.load_config()
    assert "newer than this Pensieve" in str(exc.value)


def test_get_wiki_root_returns_path(fake_home: Path, tmp_path: Path) -> None:
    wiki_root = tmp_path / "mywiki"
    (wiki_root / "wiki").mkdir(parents=True)
    cfg.write_config(wiki_root)
    result = cfg.get_wiki_root()
    assert isinstance(result, Path)
    assert result == wiki_root.resolve()


def test_get_wiki_root_path_does_not_exist_raises(fake_home: Path, tmp_path: Path) -> None:
    fake_home.parent.mkdir(parents=True, exist_ok=True)
    fake_home.write_text(
        f'schema_version = 1\nwiki_root = "{(tmp_path / "ghost").as_posix()}"\n',
        encoding="utf-8",
    )
    with pytest.raises(ConfigError) as exc:
        cfg.get_wiki_root()
    assert "not a valid wiki" in str(exc.value)


def test_get_wiki_root_no_wiki_subdir_raises(fake_home: Path, tmp_path: Path) -> None:
    wiki_root = tmp_path / "no-subdir"
    wiki_root.mkdir()
    cfg.write_config(wiki_root)
    with pytest.raises(ConfigError) as exc:
        cfg.get_wiki_root()
    assert "not a valid wiki" in str(exc.value)


def test_get_wiki_root_path_is_file_raises(fake_home: Path, tmp_path: Path) -> None:
    not_a_dir = tmp_path / "afile.txt"
    not_a_dir.write_text("hi")
    fake_home.parent.mkdir(parents=True, exist_ok=True)
    fake_home.write_text(
        f'schema_version = 1\nwiki_root = "{not_a_dir.as_posix()}"\n',
        encoding="utf-8",
    )
    with pytest.raises(ConfigError) as exc:
        cfg.get_wiki_root()
    assert "not a valid wiki" in str(exc.value)
