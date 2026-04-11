# Slack Scrape Skill

A Claude Code skill for scraping Slack activity into Pensieve-ready markdown.

## Installation

The skill is installed as a user-level Claude Code skill at:
```
~/.claude/skills/slack-scrape/SKILL.md
```

## Usage

### Phase 1: Discover & Index
```
/slack-scrape 2026-04-07 2026-04-11
/slack-scrape 2026-04-01 2026-04-30 --channel engineering-general
```

### Phase 2: Fetch (resumable)
```
/slack-scrape --fetch raw/slack/scrape-2026-04-07_2026-04-11/index.json
```

### Ingest into wiki
After fetching, ingest the raw files:
```
Ingest raw/slack/scrape-2026-04-07_2026-04-11/
```

## Design
See `docs/superpowers/specs/2026-04-11-slack-scrape-skill-design.md`
