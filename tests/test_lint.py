"""Tests for pensieve.lint module."""

from pathlib import Path

from pensieve.lint import (
    LintIssue,
    check_broken_links,
    check_index_completeness,
    check_missing_index,
    check_missing_log,
    check_orphan_pages,
    lint,
)
from pensieve.wiki import init_wiki, wiki_dir, write_page, index_path, log_path


# ---------------------------------------------------------------------------
# check_missing_index / check_missing_log
# ---------------------------------------------------------------------------


def test_missing_index_flagged(wiki_root: Path) -> None:
    issues = check_missing_index(wiki_root)
    assert any(i.code == "MISSING_INDEX" for i in issues)


def test_index_present_no_error(wiki_root: Path) -> None:
    init_wiki(wiki_root)
    issues = check_missing_index(wiki_root)
    assert issues == []


def test_missing_log_flagged(wiki_root: Path) -> None:
    issues = check_missing_log(wiki_root)
    assert any(i.code == "MISSING_LOG" for i in issues)


def test_log_present_no_error(wiki_root: Path) -> None:
    init_wiki(wiki_root)
    issues = check_missing_log(wiki_root)
    assert issues == []


# ---------------------------------------------------------------------------
# check_broken_links
# ---------------------------------------------------------------------------


def test_broken_link_detected(wiki_root: Path) -> None:
    wdir = wiki_dir(wiki_root)
    write_page(wdir / "page-a.md", "# A\n\nLinks to [[NonExistentPage]].\n")
    issues = check_broken_links(wiki_root)
    assert any(i.code == "BROKEN_LINK" for i in issues)


def test_valid_link_no_error(wiki_root: Path) -> None:
    wdir = wiki_dir(wiki_root)
    write_page(wdir / "page-a.md", "# A\n\nLinks to [[page-b]].\n")
    write_page(wdir / "page-b.md", "# B\n\nStub.\n")
    issues = check_broken_links(wiki_root)
    assert all(i.code != "BROKEN_LINK" for i in issues)


def test_broken_link_case_insensitive(wiki_root: Path) -> None:
    wdir = wiki_dir(wiki_root)
    write_page(wdir / "page-a.md", "# A\n\nLinks to [[Page-B]].\n")
    write_page(wdir / "page-b.md", "# B\n\nStub.\n")
    issues = check_broken_links(wiki_root)
    assert all(i.code != "BROKEN_LINK" for i in issues)


# ---------------------------------------------------------------------------
# check_orphan_pages
# ---------------------------------------------------------------------------


def test_orphan_page_detected(wiki_root: Path) -> None:
    wdir = wiki_dir(wiki_root)
    write_page(wdir / "orphan.md", "# Orphan\n\nNo one links here.\n")
    issues = check_orphan_pages(wiki_root)
    assert any(i.code == "ORPHAN_PAGE" for i in issues)


def test_linked_page_not_orphan(wiki_root: Path) -> None:
    wdir = wiki_dir(wiki_root)
    write_page(wdir / "page-a.md", "# A\n\nLinks to [[page-b]].\n")
    write_page(wdir / "page-b.md", "# B\n\nStub.\n")
    issues = check_orphan_pages(wiki_root)
    orphan_paths = [i.path.name for i in issues if i.code == "ORPHAN_PAGE"]
    assert "page-b.md" not in orphan_paths


# ---------------------------------------------------------------------------
# check_index_completeness
# ---------------------------------------------------------------------------


def test_page_not_in_index_warned(wiki_root: Path) -> None:
    init_wiki(wiki_root)
    wdir = wiki_dir(wiki_root)
    write_page(wdir / "unlisted.md", "# Unlisted\n\nNot in index.\n")
    issues = check_index_completeness(wiki_root)
    assert any(i.code == "NOT_IN_INDEX" for i in issues)


def test_page_in_index_no_warning(wiki_root: Path) -> None:
    init_wiki(wiki_root)
    wdir = wiki_dir(wiki_root)
    write_page(wdir / "listed.md", "# Listed\n\nIn index.\n")
    idx = index_path(wiki_root)
    idx.write_text("# Index\n\n| Page | Summary |\n| --- | --- |\n| [[listed]] | desc |\n", encoding="utf-8")
    issues = check_index_completeness(wiki_root)
    assert all(i.code != "NOT_IN_INDEX" for i in issues)


# ---------------------------------------------------------------------------
# lint (integration)
# ---------------------------------------------------------------------------


def test_lint_clean_wiki(wiki_root: Path) -> None:
    init_wiki(wiki_root)
    wdir = wiki_dir(wiki_root)
    write_page(wdir / "page-a.md", "# A\n\nLinks to [[page-b]].\n")
    write_page(wdir / "page-b.md", "# B\n\nLinks to [[page-a]].\n")
    # Add pages to index so NOT_IN_INDEX doesn't fire
    idx = index_path(wiki_root)
    idx.write_text(
        "# Index\n\n| Page | Summary |\n| --- | --- |\n| [[page-a]] | A |\n| [[page-b]] | B |\n",
        encoding="utf-8",
    )
    errors = [i for i in lint(wiki_root) if i.severity == "error"]
    assert errors == []


def test_lint_issue_str_representation() -> None:
    issue = LintIssue(severity="error", code="TEST_CODE", message="something broke")
    assert "[ERROR]" in str(issue)
    assert "TEST_CODE" in str(issue)
    assert "something broke" in str(issue)
