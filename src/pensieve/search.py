"""Simple BM25 search over wiki markdown pages.

No external dependencies required – scoring is computed in pure Python.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path

from pensieve.wiki import all_wiki_pages, read_page, page_title

# ---------------------------------------------------------------------------
# Tokenisation
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(r"[a-zA-Z0-9_']+")


def _tokenise(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text)]


# ---------------------------------------------------------------------------
# BM25 parameters
# ---------------------------------------------------------------------------

_K1 = 1.5
_B = 0.75


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class SearchResult:
    path: Path
    title: str
    score: float
    snippet: str = ""


# ---------------------------------------------------------------------------
# Index building
# ---------------------------------------------------------------------------


def _build_corpus(root: Path) -> tuple[list[Path], list[list[str]]]:
    """Return all wiki pages and their token lists."""
    pages = all_wiki_pages(root)
    corpus: list[list[str]] = []
    for p in pages:
        text = read_page(p)
        # strip YAML frontmatter
        text = re.sub(r"^---.*?---\s*", "", text, flags=re.DOTALL)
        corpus.append(_tokenise(text))
    return pages, corpus


def _avg_dl(corpus: list[list[str]]) -> float:
    if not corpus:
        return 0.0
    return sum(len(doc) for doc in corpus) / len(corpus)


def _df(corpus: list[list[str]]) -> dict[str, int]:
    """Document frequency for each term."""
    df: dict[str, int] = {}
    for doc in corpus:
        for term in set(doc):
            df[term] = df.get(term, 0) + 1
    return df


# ---------------------------------------------------------------------------
# Search entry point
# ---------------------------------------------------------------------------


def search(root: Path, query: str, top_k: int = 10) -> list[SearchResult]:
    """Return the top-*k* wiki pages most relevant to *query*.

    Uses BM25 scoring.  Returns an empty list when the wiki has no pages.
    """
    pages, corpus = _build_corpus(root)
    if not pages:
        return []

    query_tokens = _tokenise(query)
    if not query_tokens:
        return []

    n = len(corpus)
    avgdl = _avg_dl(corpus)
    df = _df(corpus)

    scores: list[float] = []
    for doc in corpus:
        dl = len(doc)
        tf_map: dict[str, int] = {}
        for term in doc:
            tf_map[term] = tf_map.get(term, 0) + 1

        score = 0.0
        for term in query_tokens:
            if term not in tf_map:
                continue
            tf = tf_map[term]
            df_t = df.get(term, 0)
            idf = math.log((n - df_t + 0.5) / (df_t + 0.5) + 1)
            numerator = tf * (_K1 + 1)
            denominator = tf + _K1 * (1 - _B + _B * dl / (avgdl or 1))
            score += idf * (numerator / denominator)
        scores.append(score)

    ranked = sorted(range(n), key=lambda i: scores[i], reverse=True)
    results: list[SearchResult] = []
    for idx in ranked[:top_k]:
        if scores[idx] <= 0:
            break
        p = pages[idx]
        title = page_title(p)
        snippet = _make_snippet(corpus[idx], query_tokens, read_page(p))
        results.append(SearchResult(path=p, title=title, score=scores[idx], snippet=snippet))
    return results


# ---------------------------------------------------------------------------
# Snippet extraction
# ---------------------------------------------------------------------------

_SENTENCE_RE = re.compile(r"[^.!?\n]+[.!?\n]?")


def _make_snippet(tokens: list[str], query_tokens: list[str], raw_text: str, max_len: int = 200) -> str:
    """Extract a sentence from *raw_text* that contains the most query terms.

    Uses the pre-tokenised *tokens* to short-circuit when no query terms appear
    in the document at all; in that case the first sentence is returned.
    """
    query_set = set(query_tokens)
    if not any(t in query_set for t in tokens):
        first_sentence = _SENTENCE_RE.search(raw_text)
        if first_sentence is None:
            return ""
        best_sentence = first_sentence.group().strip()
    else:
        best_sentence = ""
        best_hits = -1
        for sentence in _SENTENCE_RE.finditer(raw_text):
            s = sentence.group().strip()
            hits = sum(1 for t in _tokenise(s) if t in query_set)
            if hits > best_hits:
                best_hits = hits
                best_sentence = s
    if not best_sentence:
        return ""
    if len(best_sentence) > max_len:
        best_sentence = best_sentence[:max_len].rsplit(" ", 1)[0] + "…"
    return best_sentence
