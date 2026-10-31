"""Tests for pensieve.wiki module."""

from pathlib import Path

import pytest

from pensieve import config as cfg
from pensieve.wiki import (
    INDEX_FILE,
    LOG_FILE,
    all_wiki_pages,
    append_log_entry,
    build_index,
    find_wiki_root,
    init_wiki,
    log_path,
    outbound_links,
    page_first_paragraph,
    page_title,
    rebuild_index,
    wiki_dir,
    write_page,
)


# ---------------------------------------------------------------------------
# init_wiki
# ---------------------------------------------------------------------------


def test_init_creates_directories(tmp_path: Path) -> None:
    init_wiki(tmp_path)
    assert (tmp_path / "wiki").is_dir()
    assert (tmp_path / "raw").is_dir()
    assert (tmp_path / "raw" / "assets").is_dir()


def test_init_creates_index_and_log(tmp_path: Path) -> None:
    init_wiki(tmp_path)
    assert (tmp_path / "wiki" / INDEX_FILE).exists()
    assert (tmp_path / "wiki" / LOG_FILE).exists()


def test_init_is_idempotent(tmp_path: Path) -> None:
    init_wiki(tmp_path)
    init_wiki(tmp_path)  # should not raise


def test_init_preserves_existing_files(tmp_path: Path) -> None:
    init_wiki(tmp_path)
    idx = tmp_path / "wiki" / INDEX_FILE
    idx.write_text("# Existing\n", encoding="utf-8")
    init_wiki(tmp_path)
    assert idx.read_text(encoding="utf-8") == "# Existing\n"


# ---------------------------------------------------------------------------
# page helpers
# ---------------------------------------------------------------------------


def test_page_title_from_heading(wiki_root: Path) -> None:
    p = wiki_dir(wiki_root) / "test-page.md"
    write_page(p, "# My Test Page\n\nSome content.\n")
    assert page_title(p) == "My Test Page"


def test_page_title_fallback(wiki_root: Path) -> None:
    p = wiki_dir(wiki_root) / "my-page.md"
    write_page(p, "No heading here.\n")
    assert page_title(p) == "my-page"


def test_page_first_paragraph_skips_heading(wiki_root: Path) -> None:
    p = wiki_dir(wiki_root) / "para-test.md"
    write_page(p, "# Heading\n\nThis is the first paragraph.\n\nSecond paragraph.\n")
    para = page_first_paragraph(p)
    assert "first paragraph" in para
    assert "Heading" not in para


def test_page_first_paragraph_no_crash_on_empty(wiki_root: Path) -> None:
    p = wiki_dir(wiki_root) / "empty.md"
    write_page(p, "")
    assert page_first_paragraph(p) == ""


# ---------------------------------------------------------------------------
# outbound_links
# ---------------------------------------------------------------------------


def test_outbound_links_basic(wiki_root: Path) -> None:
    p = wiki_dir(wiki_root) / "linker.md"
    write_page(p, "See [[Target Page]] and [[another-page]].\n")
    links = outbound_links(p)
    assert "Target Page" in links
    assert "another-page" in links


def test_outbound_links_alias_stripped(wiki_root: Path) -> None:
    p = wiki_dir(wiki_root) / "linker2.md"
    write_page(p, "See [[Real Page|alias text]].\n")
    links = outbound_links(p)
    assert "Real Page" in links
    assert "alias text" not in links


# ---------------------------------------------------------------------------
# all_wiki_pages
# ---------------------------------------------------------------------------


def test_all_wiki_pages_excludes_index_and_log(wiki_root: Path) -> None:
    wdir = wiki_dir(wiki_root)
    (wdir / INDEX_FILE).write_text("", encoding="utf-8")
    (wdir / LOG_FILE).write_text("", encoding="utf-8")
    (wdir / "real-page.md").write_text("# Real\n", encoding="utf-8")
    pages = all_wiki_pages(wiki_root)
    names = [p.name for p in pages]
    assert "real-page.md" in names
    assert INDEX_FILE not in names
    assert LOG_FILE not in names


# ---------------------------------------------------------------------------
# append_log_entry
# ---------------------------------------------------------------------------


def test_append_log_entry_creates_file(wiki_root: Path) -> None:
    init_wiki(wiki_root)
    append_log_entry(wiki_root, "ingest", "Some Article")
    content = log_path(wiki_root).read_text(encoding="utf-8")
    assert "ingest | Some Article" in content


def test_append_log_entry_header_format(wiki_root: Path) -> None:
    init_wiki(wiki_root)
    append_log_entry(wiki_root, "query", "How does attention work?")
    content = log_path(wiki_root).read_text(encoding="utf-8")
    assert "## [" in content
    assert "query | How does attention work?" in content


def test_append_log_entry_appends_multiple(wiki_root: Path) -> None:
    init_wiki(wiki_root)
    append_log_entry(wiki_root, "ingest", "First")
    append_log_entry(wiki_root, "query", "Second")
    content = log_path(wiki_root).read_text(encoding="utf-8")
    assert "First" in content
    assert "Second" in content


def test_append_log_entry_with_body(wiki_root: Path) -> None:
    init_wiki(wiki_root)
    append_log_entry(wiki_root, "lint", "Health check", body="Found 3 orphan pages.")
    content = log_path(wiki_root).read_text(encoding="utf-8")
    assert "Found 3 orphan pages." in content


# ---------------------------------------------------------------------------
# rebuild_index
# ---------------------------------------------------------------------------


def test_rebuild_index_lists_pages(wiki_root: Path) -> None:
    wdir = wiki_dir(wiki_root)
    write_page(wdir / "alpha.md", "# Alpha\n\nFirst page about alpha.\n")
    write_page(wdir / "beta.md", "# Beta\n\nSecond page about beta.\n")
    rebuild_index(wiki_root)
    content = (wdir / INDEX_FILE).read_text(encoding="utf-8")
    assert "alpha" in content.lower()
    assert "beta" in content.lower()


def test_rebuild_index_excludes_index_and_log(wiki_root: Path) -> None:
    init_wiki(wiki_root)
    rebuild_index(wiki_root)
    content = (wiki_dir(wiki_root) / INDEX_FILE).read_text(encoding="utf-8")
    # index.md should not link to itself
    assert "[[index]]" not in content
    assert "[[log]]" not in content


# ---------------------------------------------------------------------------
# find_wiki_root
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    fake_config = tmp_path / "home" / ".pensieve" / "config.toml"
    monkeypatch.setattr(cfg, "CONFIG_PATH", fake_config)
    return fake_config


def test_find_wiki_root_prefers_configured_root_over_cwd(
    fake_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    configured = tmp_path / "configured-wiki"
    init_wiki(configured)
    cfg.write_config(configured)

    unrelated = tmp_path / "unrelated"
    unrelated.mkdir()
    monkeypatch.chdir(unrelated)

    assert find_wiki_root() == configured.resolve()


def test_find_wiki_root_falls_back_to_cwd_walk_when_no_config(
    fake_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    walked = tmp_path / "walked-wiki"
    init_wiki(walked)
    (walked / "CLAUDE.md").write_text("# schema")

    monkeypatch.chdir(walked)
    assert find_wiki_root() == walked.resolve()
