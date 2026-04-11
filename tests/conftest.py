"""Shared pytest fixtures for Pensieve tests."""

import pytest
from pathlib import Path


@pytest.fixture()
def wiki_root(tmp_path: Path) -> Path:
    """Return a fresh wiki root with the standard directory layout."""
    (tmp_path / "wiki").mkdir()
    (tmp_path / "raw" / "assets").mkdir(parents=True)
    # CLAUDE.md presence is needed for find_wiki_root
    (tmp_path / "CLAUDE.md").write_text("# Schema\n", encoding="utf-8")
    return tmp_path
