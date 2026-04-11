# Pensieve

**Pensieve** is an LLM-maintained personal knowledge wiki.  Drop source
documents into `raw/`, ask your LLM agent (Claude Code, Codex, etc.) to
ingest them, and the wiki grows automatically — summarised, cross-referenced,
and always up to date.

---

## Quick start

```bash
pip install -e .            # install the pensieve CLI
pensieve init               # scaffold wiki/ and raw/ directories
```

Copy `CLAUDE.md` (or `AGENTS.md`) into your project root so your LLM agent
knows how to operate the wiki.  Then open Claude Code (or your preferred
agent) and say:

```
Ingest raw/my-article.md
```

The agent will follow the workflow in `CLAUDE.md`, create wiki pages, update
the index, and append to the log.

---

## Architecture

```
<project-root>/
├── CLAUDE.md / AGENTS.md  ← schema that guides the LLM
├── raw/                   ← your source documents (immutable)
│   └── assets/            ← images and binary attachments
└── wiki/                  ← LLM-generated pages (the wiki)
    ├── index.md           ← master catalog
    ├── log.md             ← operations log
    └── *.md               ← entity, concept, and source pages
```

The three-layer model:
1. **Raw sources** — immutable truth; the LLM reads but never edits these.
2. **Wiki** — LLM-owned artefact; created and maintained automatically.
3. **Schema** (`CLAUDE.md`) — the configuration that makes the LLM a
   disciplined wiki maintainer rather than a generic chatbot.

---

## CLI reference

| Command | Description |
| --- | --- |
| `pensieve init [path]` | Scaffold directory structure and seed files |
| `pensieve search <query>` | BM25 search over wiki pages |
| `pensieve log-entry <type> <title>` | Append a structured entry to `log.md` |
| `pensieve lint` | Health-check (broken links, orphans, index gaps) |
| `pensieve rebuild-index` | Regenerate `index.md` from current wiki pages |

Run `pensieve --help` or `pensieve <command> --help` for full option details.

---

## Operations

### Ingest

Ask the LLM: *"Ingest `raw/my-article.md`"*.

The agent will:
1. Read the source.
2. Summarise key takeaways.
3. Create `wiki/source-<slug>.md` with a structured summary.
4. Update entity and concept pages (5-15 pages per source).
5. Update `wiki/index.md`.
6. Append to `wiki/log.md`.

### Query

Ask the LLM any question.  The agent runs `pensieve search`, reads the top
results, and synthesises an answer with wiki citations.  Good answers are
filed back into the wiki as new pages.

### Lint

Ask the LLM: *"Lint the wiki"* or run:

```bash
pensieve lint
```

Checks for broken wikilinks, orphan pages, pages missing from the index, and
missing core files.  Fix errors immediately; review warnings periodically.

---

## Log format

Log entries use a consistent prefix for easy grep:

```
## [YYYY-MM-DD] <event_type> | <title>
```

```bash
# Last 5 entries
grep "^## \[" wiki/log.md | tail -5
```

---

## Development

```bash
pip install -e .
pytest
```

---

## Slack Scrape

A Claude Code skill that scrapes your Slack activity into `raw/slack/` for
wiki ingest.  See [SLACK-SCRAPE-SKILL.md](SLACK-SCRAPE-SKILL.md) for usage.

---

## Inspiration

Inspired by Vannevar Bush's *Memex* (1945) — a personal, curated knowledge
store with associative trails.  The part Bush couldn't solve was maintenance.
LLMs handle that.