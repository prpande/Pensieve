"""Pensieve CLI – utility tool for LLM-maintained knowledge wikis."""

from __future__ import annotations

import sys
from pathlib import Path

import click

from pensieve import __version__
from pensieve.wiki import (
    append_log_entry,
    find_wiki_root,
    init_wiki,
    rebuild_index,
    wiki_dir,
)
from pensieve.search import search as do_search
from pensieve.lint import lint as do_lint


# ---------------------------------------------------------------------------
# Shared option
# ---------------------------------------------------------------------------


def _root_option(fn):
    return click.option(
        "--root",
        default=None,
        type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
        help="Wiki root directory (auto-detected if omitted).",
    )(fn)


# ---------------------------------------------------------------------------
# CLI group
# ---------------------------------------------------------------------------


@click.group()
@click.version_option(__version__, prog_name="pensieve")
def main() -> None:
    """Pensieve – LLM-maintained personal knowledge wiki tool.

    \b
    Typical workflow
    ────────────────
    1. pensieve init            # scaffold directories and seed files
    2. Drop sources into raw/
    3. Ask the LLM to ingest them (guided by CLAUDE.md / AGENTS.md)
    4. pensieve search <query>  # find relevant wiki pages
    5. pensieve lint            # health-check the wiki
    6. pensieve rebuild-index   # refresh index.md
    """


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------


@main.command()
@click.argument("path", default=".", type=click.Path(file_okay=False, dir_okay=True, path_type=Path))
@click.option("--force", is_flag=True, default=False, help="Overwrite existing config without prompting.")
def init(path: Path, force: bool) -> None:
    """Initialise a new wiki inside PATH (default: current directory).

    Creates wiki/, raw/, raw/assets/ directories and seeds wiki/index.md
    and wiki/log.md if they do not already exist. Also registers PATH as
    the active wiki in ~/.pensieve/config.toml.
    """
    from pensieve import config as cfg

    root = path.resolve()
    init_wiki(root)

    # Overwrite-protection: if a config exists pointing somewhere else,
    # confirm before clobbering it.
    if cfg.CONFIG_PATH.exists() and not force:
        try:
            existing = cfg.load_config()
            existing_root = Path(existing["wiki_root"]).resolve()
            if existing_root != root:
                click.echo(f"Existing config points to {existing_root}.")
                if not click.confirm("Overwrite?", default=False):
                    click.echo("Aborted. Wiki scaffold left in place; config unchanged.")
                    return
        except cfg.ConfigError:
            # Existing config is unreadable; fall through and overwrite.
            pass

    cfg.write_config(root)
    click.echo(f"✓ Wiki initialised at {root}")
    click.echo(f"  wiki/   → {wiki_dir(root)}")
    click.echo(f"  raw/    → {root / 'raw'}")
    click.echo(f"✓ Registered as active wiki in {cfg.CONFIG_PATH}")
    click.echo("  Next step: copy CLAUDE.md / AGENTS.md from the repo root into your project.")


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------


@main.command()
@click.argument("query")
@click.option("-k", "--top", default=10, show_default=True, help="Number of results to return.")
@click.option("--snippet/--no-snippet", default=True, show_default=True, help="Print a matching snippet.")
@_root_option
def search(query: str, top: int, snippet: bool, root: Path | None) -> None:
    """Search wiki pages for QUERY using BM25 scoring.

    Prints the top matching pages sorted by relevance.  The LLM can use
    the result paths to decide which pages to read before answering.
    """
    effective_root = root or find_wiki_root()
    results = do_search(effective_root, query, top_k=top)
    if not results:
        click.echo("No matching pages found.")
        return
    for i, r in enumerate(results, 1):
        rel = r.path.relative_to(wiki_dir(effective_root))
        click.echo(f"{i:2}. [{r.score:.2f}] {r.title}  ({rel})")
        if snippet and r.snippet:
            click.echo(f"     {r.snippet}")


# ---------------------------------------------------------------------------
# log-entry
# ---------------------------------------------------------------------------


@main.command("log-entry")
@click.argument("event_type")
@click.argument("title")
@click.option("--body", default="", help="Optional body text for the log entry.")
@_root_option
def log_entry(event_type: str, title: str, body: str, root: Path | None) -> None:
    """Append a structured entry to wiki/log.md.

    \b
    EVENT_TYPE  Short label: ingest | query | lint | note | …
    TITLE       Human-readable description of this event

    The entry is formatted as:
      ## [YYYY-MM-DD] <event_type> | <title>
    which can be parsed with simple tools:
      grep "^## \\[" wiki/log.md | tail -5
    """
    effective_root = root or find_wiki_root()
    append_log_entry(effective_root, event_type, title, body)
    click.echo(f"✓ Log entry appended: {event_type} | {title}")


# ---------------------------------------------------------------------------
# lint
# ---------------------------------------------------------------------------


@main.command()
@click.option("--strict", is_flag=True, default=False, help="Exit with non-zero status if any warnings exist.")
@_root_option
def lint(strict: bool, root: Path | None) -> None:
    """Health-check the wiki.

    Checks for broken wikilinks, orphan pages, pages missing from the index,
    and missing core files (index.md, log.md).
    """
    effective_root = root or find_wiki_root()
    issues = do_lint(effective_root)
    if not issues:
        click.echo("✓ No issues found.")
        return

    errors = [i for i in issues if i.severity == "error"]
    warnings = [i for i in issues if i.severity == "warning"]
    infos = [i for i in issues if i.severity == "info"]

    for issue in issues:
        click.echo(str(issue))

    click.echo(
        f"\n{len(issues)} issue(s): "
        f"{len(errors)} error(s), {len(warnings)} warning(s), {len(infos)} info(s)."
    )

    if errors or (strict and warnings):
        sys.exit(1)


# ---------------------------------------------------------------------------
# rebuild-index
# ---------------------------------------------------------------------------


@main.command("rebuild-index")
@_root_option
def rebuild_index_cmd(root: Path | None) -> None:
    """Rebuild wiki/index.md by scanning all wiki pages.

    The index table lists every page with a one-line summary extracted from
    its first non-heading paragraph.  Run this after bulk-adding pages.
    """
    effective_root = root or find_wiki_root()
    rebuild_index(effective_root)
    click.echo(f"✓ index.md rebuilt at {wiki_dir(effective_root) / 'index.md'}")
