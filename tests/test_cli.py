"""Tests for the pensieve CLI (click commands)."""

from pathlib import Path

from click.testing import CliRunner

from pensieve.cli import main
from pensieve.wiki import init_wiki, wiki_dir, write_page, log_path, index_path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_runner() -> CliRunner:
    return CliRunner()


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------


def test_cli_init_creates_structure(tmp_path: Path) -> None:
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
