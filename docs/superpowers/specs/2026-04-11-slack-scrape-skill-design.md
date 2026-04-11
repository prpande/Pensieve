# Slack Scrape Skill — Design Spec

**Date:** 2026-04-11
**Author:** Pratyush Pande + Claude
**Status:** Approved

---

## Overview

A Claude Code skill (`/slack-scrape`) that exhaustively scrapes a user's Slack
activity for a given date range using the Slack MCP tools, producing structured
markdown files in `raw/slack/` ready for Pensieve's ingest workflow.

The skill operates in two phases — **Discover & Index** (cheap) and **Fetch**
(token-heavy, resumable) — so that quota exhaustion doesn't lose progress.

---

## Goals

- Capture all Slack activity: messages sent, @mentions received, emoji reactions
- Include full thread context and ~10 surrounding channel messages
- Preserve files, links, canvases, and attachments as metadata + inline content
- Output one markdown file per channel per day into `raw/slack/`
- Support resumable fetching via a persistent index file
- Keep Phase 1 (discovery) as token-efficient as possible

## Non-Goals

- Downloading binary file attachments (Slack MCP cannot do this)
- Auto-ingesting into the Pensieve wiki (user triggers ingest separately)
- Direct Slack API access (no user token available; MCP-only)
- Real-time or streaming scraping

---

## Skill Interface

### Phase 1: Discover & Index

```
/slack-scrape 2026-04-07 2026-04-11
```

**Parameters:**
- **Start date** (required) — inclusive, ISO format `YYYY-MM-DD`
- **End date** (optional) — inclusive, defaults to today
- **--channel** (optional) — limit to specific channel name

**Output:**
- Index file at `raw/slack/scrape-<start>_<end>/index.json`
- Terminal summary: total hits, channels, days

### Phase 2: Fetch (resumable)

```
/slack-scrape --fetch raw/slack/scrape-2026-04-07_2026-04-11/index.json
```

**Parameters:**
- **--fetch \<path\>** — path to an existing index.json

**Output:**
- Markdown files at `raw/slack/scrape-<start>_<end>/<YYYY-MM-DD>/<channel-slug>--<channel-id>.md`
- Updated index.json with status per channel-day

**Filename rules:**
- `channel-id` is the immutable Slack channel/conversation ID, always included
- `channel-slug` is for readability: lowercase the display name, replace runs of
  non-alphanumeric characters with `-`, trim leading/trailing `-`, use `channel`
  if the result is empty (e.g. unnamed DMs)
- The `channel-id` suffix makes filenames deterministic, filesystem-safe, and
  stable across renames/collisions (including DMs/group DMs)

**Hardcoded:** User ID `U07ENJD06T0` (pratyush.pande). This is a personal tool.

---

## Phase 1: Discovery Logic

### Three search queries

All use `slack_search_public_and_private` with `response_format: "concise"`,
`include_context: false`, sorted by `timestamp`, paginating via `cursor` until
exhausted.

1. **Your messages:** `from:<@U07ENJD06T0> after:<start> before:<end+1>`
2. **Mentions of you:** `to:<@U07ENJD06T0> after:<start> before:<end+1>`
3. **Your reactions:** `hasmy::*: after:<start> before:<end+1>`
   - If wildcard reaction syntax is unsupported, log a warning and skip.

### Deduplication

Deduplicate by `(channel_id, message_ts)` pair across all three queries.

### Date bucketing

Each hit is assigned to a date bucket (YYYY-MM-DD) based on its message
timestamp. The index status map has one entry per channel per day.

### Index format

```json
{
  "user_id": "U07ENJD06T0",
  "date_range": ["2026-04-07", "2026-04-11"],
  "created_at": "2026-04-11T10:30:00Z",
  "channels": {
    "<channel_id>": {
      "channel_id": "<channel_id>",
      "channel_name": "<channel-name>",
      "channel_slug": "<slugified-name>",
      "type": "public_channel | private_channel | im | mpim",
      "hits": [
        {
          "ts": "1712505600.001",
          "type": "message | mention | reaction",
          "date": "2026-04-07",
          "preview": "First ~100 chars of the message..."
        }
      ]
    }
  },
  "status": {
    "<channel_id>": {
      "2026-04-07": "pending | done | error"
    }
  },
  "stats": {
    "total_hits": 47,
    "channels": 6,
    "days": 5
  }
}
```

### Token budget

For a typical week (~50-100 activity hits): ~3-5 pages per query type,
roughly **10-15 MCP calls** for the entire discovery phase.

---

## Phase 2: Fetch Logic

Reads the index and processes each channel-day pair with status `"pending"` or
`"error"`. Processes chronologically (oldest first).

### Per channel-day steps

**Step 1 — Expand threads**

For each hit timestamp, call `slack_read_thread` with `channel_id` and
`message_ts` using `response_format: "detailed"`. Skip if the message has no
thread replies.

**Step 2 — Fetch channel context**

Call `slack_read_channel` with:
- `channel_id`
- `oldest` = start of that day as Unix timestamp
- `latest` = end of that day as Unix timestamp
- `limit` = 100

Timezone note: Slack timestamps are Unix epoch (UTC). Date bucketing uses the
user's local timezone (derived from their Slack profile via
`slack_read_user_profile` at skill start). Day boundaries for channel reads
use the same local timezone converted to Unix timestamps.

Paginate if needed. This provides ~10 messages before/after the user's activity.

**Step 3 — Resolve user names**

Collect unique user IDs from fetched messages. Call `slack_read_user_profile`
for each unknown ID. Cache resolved names across the entire run to avoid
repeat lookups.

**Step 4 — Read inline content**

- **Canvases:** Call `slack_read_canvas` to inline content.
- **Code snippets / text files:** Capture from MCP message detail.
- **Binary files (images, PDFs):** Record metadata + Slack permalink only.

**Step 5 — Write markdown file**

Write to `raw/slack/scrape-<start>_<end>/<YYYY-MM-DD>/<channel-slug>--<channel-id>.md`.

**Step 6 — Update index**

Set channel-day status to `"done"`. Write updated index.json to disk
immediately. This is the resume checkpoint.

### Error handling

If an MCP call fails (rate limit, timeout), mark the channel-day as `"error"`
with a reason string. On resume, `"error"` entries are retried alongside
`"pending"` ones.

---

## Output Markdown Format

```markdown
---
type: slack-scrape
channel: engineering-general
channel_id: C0ABC123
channel_type: public_channel
date: 2026-04-07
scrape_range: 2026-04-07 to 2026-04-11
user: pratyush.pande
---

# engineering-general — 2026-04-07

## Channel Context

Messages from the channel timeline around your activity.

### 09:12 — Jane Smith
We need to finalize the API contract before the sprint ends.

### 09:15 — Bob Lee
Agreed. I'll draft the OpenAPI spec today.

### 09:18 — Pratyush Pande ⭐
@Bob can you include the webhook payload schema too?

---

## Thread: API contract finalization
_Parent by Jane Smith at 09:12 — 5 replies_

> **09:12 — Jane Smith**
> We need to finalize the API contract before the sprint ends.

> **09:15 — Bob Lee**
> Agreed. I'll draft the OpenAPI spec today.

> **09:18 — Pratyush Pande** ⭐
> @Bob can you include the webhook payload schema too?

> **09:22 — Bob Lee**
> Sure, will add it.
> (file) [api-contract-v2.yaml](https://...) (yaml, 12KB, uploaded by Bob Lee)

> **09:30 — Jane Smith**
> Looks good. Let's review in standup.

---

## Files & Links

| File | Type | Shared by | Link |
|---|---|---|---|
| api-contract-v2.yaml | yaml | Bob Lee | [Slack link](https://...) |

## Canvas: Sprint Planning Notes
_Canvas ID: F1234567890, created by Jane Smith_

> (inlined canvas content here)

---

_Scraped by pensieve slack-scrape on 2026-04-11_
```

### Conventions

- **⭐** marker on the user's own messages for easy scanning/grepping
- **Channel Context** section shows timeline flow with surrounding messages
- **Thread** sections expand each thread with full replies
- **Files & Links** table collects all attachments
- **Canvas** sections inline readable content
- Timestamps in `HH:MM` format
- User IDs resolved to display names throughout

---

## File Structure

```
raw/slack/
  scrape-2026-04-07_2026-04-11/
    index.json                                    <- discovery index + resume state
    2026-04-07/
      engineering-general--C0ABC123.md
      dm-jane-smith--D0XYZ789.md
    2026-04-08/
      engineering-general--C0ABC123.md
      project-alpha--C0DEF456.md
    ...
```

---

## Implementation Notes

- **Skill type:** Claude Code skill, invoked via `/slack-scrape`
- **MCP dependency:** `claude_ai_Slack` tools (search, read_channel, read_thread, read_user_profile, read_canvas)
- **No external dependencies:** No Python packages, no Slack API tokens
- **Token efficiency strategy:**
  - Phase 1 uses `concise` format and `include_context: false`
  - Phase 2 uses `detailed` format only when fetching actual content
  - User name cache avoids repeat profile lookups
  - Index-based resume avoids re-fetching completed channel-days
- **Future upgrade path:** If a Slack user token becomes available, Phase 2
  could be replaced with a Python script using `slack_sdk` for significantly
  lower token cost
