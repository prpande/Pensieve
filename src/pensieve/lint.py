"""Wiki health checks (lint)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from pensieve.wiki import (
    all_wiki_pages,
    index_path,
    log_path,
    outbound_links,
    page_title,
    wiki_dir,
    WIKILINK_RE,
)

# ---------------------------------------------------------------------------
# Issue types
# ---------------------------------------------------------------------------


@dataclass
class LintIssue:
    severity: str  # "error" | "warning" | "info"
    code: str
    message: str
    path: Path | None = None

    def __str__(self) -> str:
        loc = f"  [{self.path.name}]" if self.path else ""
        return f"[{self.severity.upper()}] {self.code}{loc}: {self.message}"


# ---------------------------------------------------------------------------
# Lint checks
# ---------------------------------------------------------------------------


def _page_stem_map(root: Path) -> dict[str, Path]:
    """Map lowercase page stems to their paths."""
    return {p.stem.lower(): p for p in all_wiki_pages(root)}


def check_broken_links(root: Path) -> list[LintIssue]:
    """Flag wikilinks that point to non-existent pages."""
    issues: list[LintIssue] = []
    stem_map = _page_stem_map(root)
    for page in all_wiki_pages(root):
        for target in outbound_links(page):
            if target.lower() not in stem_map:
                issues.append(
                    LintIssue(
                        severity="error",
                        code="BROKEN_LINK",
                        message=f"[[{target}]] does not exist",
                        path=page,
                    )
                )
    return issues


def check_orphan_pages(root: Path) -> list[LintIssue]:
    """Flag pages with no inbound wikilinks from other wiki pages.

    The index and log are excluded from consideration.
    """
    issues: list[LintIssue] = []
    pages = all_wiki_pages(root)
    stem_map = _page_stem_map(root)

    # Build a set of all link targets mentioned across all pages
    all_targets: set[str] = set()
    for page in pages:
        for target in outbound_links(page):
            all_targets.add(target.lower())

    for page in pages:
        if page.stem.lower() not in all_targets:
            issues.append(
                LintIssue(
                    severity="warning",
                    code="ORPHAN_PAGE",
                    message="Page has no inbound wikilinks",
                    path=page,
                )
            )
    return issues


def check_missing_index(root: Path) -> list[LintIssue]:
    if not index_path(root).exists():
        return [LintIssue(severity="error", code="MISSING_INDEX", message="wiki/index.md is missing")]
    return []


def check_missing_log(root: Path) -> list[LintIssue]:
    if not log_path(root).exists():
        return [LintIssue(severity="error", code="MISSING_LOG", message="wiki/log.md is missing")]
    return []


def check_index_completeness(root: Path) -> list[LintIssue]:
    """Warn about wiki pages not mentioned in index.md."""
    issues: list[LintIssue] = []
    idx = index_path(root)
    if not idx.exists():
        return issues
    index_text = idx.read_text(encoding="utf-8").lower()
    for page in all_wiki_pages(root):
        stem_lower = page.stem.lower()
        # Accept either [[stem]] or plain stem mention
        if f"[[{stem_lower}]]" not in index_text and stem_lower not in index_text:
            issues.append(
                LintIssue(
                    severity="warning",
                    code="NOT_IN_INDEX",
                    message="Page not mentioned in index.md",
                    path=page,
                )
            )
    return issues


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def lint(root: Path) -> list[LintIssue]:
    """Run all lint checks and return a deduplicated list of issues."""
    all_issues: list[LintIssue] = []
    all_issues.extend(check_missing_index(root))
    all_issues.extend(check_missing_log(root))
    all_issues.extend(check_broken_links(root))
    all_issues.extend(check_orphan_pages(root))
    all_issues.extend(check_index_completeness(root))
    return all_issues
