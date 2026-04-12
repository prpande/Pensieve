"""Tests for the pensieve CLI (click commands)."""

import pytest
from pathlib import Path

from click.testing import CliRunner

from pensieve.cli import main
from pensieve.wiki import init_wiki, wiki_dir, write_page, log_path, index_path
from pensieve import config as cfg


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_runner() -> CliRunner:
    return CliRunner()


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------


def test_cli_init_creates_structure(fake_home: Path, tmp_path: Path) -> None:
    # fake_home redirects CONFIG_PATH under tmp_path; prevents writes to real ~/.pensieve.
    runner = make_runner()
    result = runner.invoke(main, ["init", str(tmp_path)])
    assert result.exit_code == 0
    assert (tmp_path / "wiki").is_dir()
    assert (tmp_path / "raw").is_dir()
    assert (tmp_path / "wiki" / "index.md").exists()
    assert (tmp_path / "wiki" / "log.md").exists()


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------


def test_cli_search_no_results(wiki_root: Path) -> None:
    runner = make_runner()
    result = runner.invoke(main, ["search", "--root", str(wiki_root), "totally absent"])
    assert result.exit_code == 0
    assert "No matching pages" in result.output


def test_cli_search_finds_page(wiki_root: Path) -> None:
    wdir = wiki_dir(wiki_root)
    write_page(wdir / "attention.md", "# Attention\n\nAttention mechanism in deep learning.\n")
    runner = make_runner()
    result = runner.invoke(main, ["search", "--root", str(wiki_root), "attention deep learning"])
    assert result.exit_code == 0
    assert "Attention" in result.output


# ---------------------------------------------------------------------------
# log-entry
# ---------------------------------------------------------------------------


def test_cli_log_entry(wiki_root: Path) -> None:
    init_wiki(wiki_root)
    runner = make_runner()
    result = runner.invoke(
        main,
        ["log-entry", "--root", str(wiki_root), "ingest", "Some Paper"],
    )
    assert result.exit_code == 0
    content = log_path(wiki_root).read_text(encoding="utf-8")
    assert "ingest | Some Paper" in content


def test_cli_log_entry_with_body(wiki_root: Path) -> None:
    init_wiki(wiki_root)
    runner = make_runner()
    result = runner.invoke(
        main,
        ["log-entry", "--root", str(wiki_root), "--body", "Extra info here.", "note", "Observation"],
    )
    assert result.exit_code == 0
    content = log_path(wiki_root).read_text(encoding="utf-8")
    assert "Extra info here." in content


# ---------------------------------------------------------------------------
# lint
# ---------------------------------------------------------------------------


def test_cli_lint_clean(wiki_root: Path) -> None:
    init_wiki(wiki_root)
    runner = make_runner()
    result = runner.invoke(main, ["lint", "--root", str(wiki_root)])
    assert result.exit_code == 0
    assert "No issues" in result.output


def test_cli_lint_reports_errors(wiki_root: Path) -> None:
    init_wiki(wiki_root)
    wdir = wiki_dir(wiki_root)
    write_page(wdir / "bad.md", "# Bad\n\nLinks to [[ghost-page]].\n")
    runner = make_runner()
    result = runner.invoke(main, ["lint", "--root", str(wiki_root)])
    assert result.exit_code != 0
    assert "BROKEN_LINK" in result.output


def test_cli_lint_strict_exits_nonzero_on_warnings(wiki_root: Path) -> None:
    init_wiki(wiki_root)
    wdir = wiki_dir(wiki_root)
    write_page(wdir / "orphan.md", "# Orphan\n\nNo links.\n")
    runner = make_runner()
    result = runner.invoke(main, ["lint", "--root", str(wiki_root), "--strict"])
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# rebuild-index
# ---------------------------------------------------------------------------


def test_cli_rebuild_index(wiki_root: Path) -> None:
    init_wiki(wiki_root)
    wdir = wiki_dir(wiki_root)
    write_page(wdir / "new-page.md", "# New Page\n\nContent here.\n")
    runner = make_runner()
    result = runner.invoke(main, ["rebuild-index", "--root", str(wiki_root)])
    assert result.exit_code == 0
    content = index_path(wiki_root).read_text(encoding="utf-8")
    assert "new-page" in content.lower()


# ---------------------------------------------------------------------------
# fake_home fixture + init config tests
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    fake_config = tmp_path / "home" / ".pensieve" / "config.toml"
    monkeypatch.setattr(cfg, "CONFIG_PATH", fake_config)
    return fake_config


def test_cli_init_writes_config(fake_home: Path, tmp_path: Path) -> None:
    target = tmp_path / "mywiki"
    runner = make_runner()
    result = runner.invoke(main, ["init", str(target)])
    assert result.exit_code == 0
    assert fake_home.exists()
    assert target.resolve().as_posix() in fake_home.read_text(encoding="utf-8")
    assert "Registered as active wiki" in result.output


def test_cli_init_prompts_when_existing_config_points_elsewhere(
    fake_home: Path, tmp_path: Path
) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    runner = make_runner()
    runner.invoke(main, ["init", str(first)])
    # Decline overwrite
    result = runner.invoke(main, ["init", str(second)], input="n\n")
    assert result.exit_code == 0
    assert "Existing config points to" in result.output
    assert first.resolve().as_posix() in fake_home.read_text(encoding="utf-8")


def test_cli_init_accepts_overwrite_prompt(fake_home: Path, tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    runner = make_runner()
    runner.invoke(main, ["init", str(first)])
    result = runner.invoke(main, ["init", str(second)], input="y\n")
    assert result.exit_code == 0
    assert second.resolve().as_posix() in fake_home.read_text(encoding="utf-8")
    assert "Registered as active wiki" in result.output


def test_cli_init_force_overwrites_without_prompt(
    fake_home: Path, tmp_path: Path
) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    runner = make_runner()
    runner.invoke(main, ["init", str(first)])
    result = runner.invoke(main, ["init", "--force", str(second)])
    assert result.exit_code == 0
    assert second.resolve().as_posix() in fake_home.read_text(encoding="utf-8")


def test_cli_init_same_root_does_not_prompt(fake_home: Path, tmp_path: Path) -> None:
    target = tmp_path / "mywiki"
    runner = make_runner()
    runner.invoke(main, ["init", str(target)])
    result = runner.invoke(main, ["init", str(target)])
    assert result.exit_code == 0
    assert "Existing config points to" not in result.output


# ---------------------------------------------------------------------------
# root
# ---------------------------------------------------------------------------


def test_cli_root_prints_configured_path(fake_home: Path, tmp_path: Path) -> None:
    target = tmp_path / "mywiki"
    runner = make_runner()
    runner.invoke(main, ["init", str(target)])
    result = runner.invoke(main, ["root"])
    assert result.exit_code == 0
    assert result.output.strip() == target.resolve().as_posix()


def test_cli_root_no_config_exits_nonzero(fake_home: Path) -> None:
    runner = make_runner()
    result = runner.invoke(main, ["root"])
    assert result.exit_code == 1
    # Click's CliRunner merges stderr into output by default
    assert "not initialised" in result.output


def test_cli_root_invalid_wiki_root_exits_nonzero(
    fake_home: Path, tmp_path: Path
) -> None:
    fake_home.parent.mkdir(parents=True, exist_ok=True)
    fake_home.write_text(
        f'schema_version = 1\nwiki_root = "{(tmp_path / "ghost").as_posix()}"\n',
        encoding="utf-8",
    )
    runner = make_runner()
    result = runner.invoke(main, ["root"])
    assert result.exit_code == 1
    assert "not a valid wiki" in result.output
