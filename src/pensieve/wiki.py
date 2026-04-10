"""Wiki page management: read/write pages, frontmatter, index, and log."""

from __future__ import annotations

import re
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

WIKI_DIR_NAME = "wiki"
RAW_DIR_NAME = "raw"
INDEX_FILE = "index.md"
LOG_FILE = "log.md"

# Wikilink pattern: [[Page Name]] or [[Page Name|alias]]
WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(?:[|#][^\]]*)?\]\]")

# Log entry header pattern (parseable with grep)
LOG_HEADER_PREFIX = "## ["

# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def find_wiki_root(start: Path | None = None) -> Path:
    """Walk up from *start* (default: cwd) to find the wiki root directory.

    The root is the directory that contains both a ``wiki/`` sub-directory
    and either a ``CLAUDE.md`` or ``AGENTS.md`` file.  If no such directory
    is found the function returns the original *start* directory so callers
    can still operate relative to wherever they are.
    """
    current = (start or Path.cwd()).resolve()
    for candidate in [current, *current.parents]:
        has_wiki = (candidate / WIKI_DIR_NAME).is_dir()
        has_schema = (candidate / "CLAUDE.md").exists() or (candidate / "AGENTS.md").exists()
        if has_wiki and has_schema:
            return candidate
    return current


def wiki_dir(root: Path) -> Path:
    return root / WIKI_DIR_NAME


def raw_dir(root: Path) -> Path:
    return root / RAW_DIR_NAME


def index_path(root: Path) -> Path:
    return wiki_dir(root) / INDEX_FILE


def log_path(root: Path) -> Path:
    return wiki_dir(root) / LOG_FILE


# ---------------------------------------------------------------------------
# Page I/O
# ---------------------------------------------------------------------------


def all_wiki_pages(root: Path) -> list[Path]:
    """Return all ``*.md`` files inside the wiki directory (excluding index & log)."""
    wdir = wiki_dir(root)
    excluded = {INDEX_FILE, LOG_FILE}
    return sorted(p for p in wdir.rglob("*.md") if p.name not in excluded)


def read_page(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_page(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def page_title(path: Path) -> str:
    """Return the first H1 heading from a page, or the stem if none found."""
    text = read_page(path)
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("# "):
            return line[2:].strip()
    return path.stem


def page_first_paragraph(path: Path) -> str:
    """Return a short (~one paragraph) description from a page."""
    text = read_page(path)
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    for para in paragraphs:
        # skip headings, YAML frontmatter delimiters, and horizontal rules
        if not para.startswith(("#", "---", "===")):
            # strip inline markdown (bold, italic, links)
            clean = re.sub(r"\*+([^*]+)\*+", r"\1", para)
            clean = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", clean)
            clean = re.sub(r"\[\[([^\]|]+)(?:\|[^\]]*)?\]\]", r"\1", clean)
            return textwrap.shorten(clean, width=160, placeholder="…")
    return ""


def outbound_links(path: Path) -> list[str]:
    """Return all wikilink targets ``[[Target]]`` found in a page."""
    text = read_page(path)
    return WIKILINK_RE.findall(text)


# ---------------------------------------------------------------------------
# Index management
# ---------------------------------------------------------------------------

_INDEX_HEADER = textwrap.dedent(
    """\
    # Wiki Index

    This file is auto-maintained by Pensieve.
    Update it with `pensieve rebuild-index` or by editing it directly.

    """
)


def build_index(root: Path) -> str:
    """Generate a fresh index.md content from all wiki pages."""
    pages = all_wiki_pages(root)
    lines: list[str] = [_INDEX_HEADER]
    lines.append("| Page | Summary |\n| --- | --- |")
    for page in pages:
        rel = page.relative_to(wiki_dir(root))
        title = page_title(page)
        summary = page_first_paragraph(page)
        link = f"[[{page.stem}]]"
        lines.append(f"| {link} | {summary} |")
    lines.append("")
    return "\n".join(lines)


def rebuild_index(root: Path) -> None:
    content = build_index(root)
    write_page(index_path(root), content)


# ---------------------------------------------------------------------------
# Log management
# ---------------------------------------------------------------------------


def _now_utc() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")


def append_log_entry(root: Path, event_type: str, title: str, body: str = "") -> None:
    """Append a structured log entry to log.md.

    Format: ``## [YYYY-MM-DD] <event_type> | <title>``
    followed by an optional *body* paragraph.
    """
    log = log_path(root)
    date_str = _now_utc()
    header = f"{LOG_HEADER_PREFIX}{date_str}] {event_type} | {title}"
    entry_parts = [f"\n{header}\n"]
    if body.strip():
        entry_parts.append(body.strip() + "\n")
    entry = "\n".join(entry_parts)
    with log.open("a", encoding="utf-8") as fh:
        fh.write(entry)


# ---------------------------------------------------------------------------
# Scaffold helpers
# ---------------------------------------------------------------------------

_INITIAL_INDEX = textwrap.dedent(
    """\
    # Wiki Index

    This file is auto-maintained by Pensieve.
    Update it with `pensieve rebuild-index` or by editing it directly.

    | Page | Summary |
    | --- | --- |
    """
)

_INITIAL_LOG = textwrap.dedent(
    """\
    # Log

    Append-only record of all wiki operations.
    Each entry starts with `## [YYYY-MM-DD] <event_type> | <title>`
    so it can be filtered with simple tools:

    ```
    grep "^## \\[" wiki/log.md | tail -5
    ```

    """
)


def init_wiki(root: Path) -> None:
    """Create the directory scaffold and seed files if they don't exist."""
    for d in [wiki_dir(root), raw_dir(root), raw_dir(root) / "assets"]:
        d.mkdir(parents=True, exist_ok=True)

    idx = index_path(root)
    if not idx.exists():
        write_page(idx, _INITIAL_INDEX)

    lg = log_path(root)
    if not lg.exists():
        write_page(lg, _INITIAL_LOG)
