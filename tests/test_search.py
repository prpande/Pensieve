"""Tests for pensieve.search module."""

from pathlib import Path

from pensieve.search import search, _tokenise
from pensieve.wiki import init_wiki, wiki_dir, write_page


# ---------------------------------------------------------------------------
# tokenise
# ---------------------------------------------------------------------------


def test_tokenise_basic() -> None:
    tokens = _tokenise("Hello World!")
    assert "hello" in tokens
    assert "world" in tokens


def test_tokenise_empty() -> None:
    assert _tokenise("") == []


# ---------------------------------------------------------------------------
# search – empty wiki
# ---------------------------------------------------------------------------


def test_search_empty_wiki(wiki_root: Path) -> None:
    results = search(wiki_root, "anything")
    assert results == []


# ---------------------------------------------------------------------------
# search – relevance ordering
# ---------------------------------------------------------------------------


def test_search_finds_matching_page(wiki_root: Path) -> None:
    wdir = wiki_dir(wiki_root)
    write_page(wdir / "transformers.md", "# Transformers\n\nTransformers use attention mechanisms.\n")
    write_page(wdir / "cooking.md", "# Cooking\n\nRecipes for pasta and soup.\n")
    results = search(wiki_root, "attention transformer")
    assert results, "Expected at least one result"
    assert results[0].path.name == "transformers.md"


def test_search_returns_top_k(wiki_root: Path) -> None:
    wdir = wiki_dir(wiki_root)
    for i in range(5):
        write_page(wdir / f"page-{i}.md", f"# Page {i}\n\nContent about topic {i}.\n")
    results = search(wiki_root, "topic", top_k=3)
    assert len(results) <= 3


def test_search_no_match_returns_empty(wiki_root: Path) -> None:
    wdir = wiki_dir(wiki_root)
    write_page(wdir / "cooking.md", "# Cooking\n\nRecipes for pasta and soup.\n")
    results = search(wiki_root, "zzzyyyxxx_no_match_ever")
    assert results == []


def test_search_score_positive(wiki_root: Path) -> None:
    wdir = wiki_dir(wiki_root)
    write_page(wdir / "ml.md", "# Machine Learning\n\nML models learn from data.\n")
    results = search(wiki_root, "machine learning")
    assert all(r.score > 0 for r in results)


def test_search_result_has_snippet(wiki_root: Path) -> None:
    wdir = wiki_dir(wiki_root)
    write_page(wdir / "attention.md", "# Attention\n\nAttention is all you need for transformers.\n")
    results = search(wiki_root, "attention transformers")
    assert results
    assert results[0].snippet != ""
