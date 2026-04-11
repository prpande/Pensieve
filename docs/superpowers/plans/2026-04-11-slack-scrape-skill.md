# Slack Scrape Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a Claude Code skill (`/slack-scrape`) that scrapes Slack activity via MCP tools into resumable, structured markdown files for Pensieve ingest.

**Architecture:** A single SKILL.md file placed in `~/.claude/skills/slack-scrape/` that instructs Claude how to orchestrate Slack MCP tools in two phases: discover & index (cheap search pass), then fetch & write (resumable content extraction). The skill uses Write/Read/Bash tools for file I/O and Slack MCP tools for data access. No Python code — the skill is a prompt document that Claude follows.

**Tech Stack:** Claude Code skill (SKILL.md), Slack MCP tools (`slack_search_public_and_private`, `slack_read_channel`, `slack_read_thread`, `slack_read_user_profile`, `slack_read_canvas`), JSON index file, Markdown output.

**Spec:** `docs/superpowers/specs/2026-04-11-slack-scrape-skill-design.md`

---

### Task 1: Create the skill file with frontmatter and argument parsing

**Files:**
- Create: `C:\Users\pratyush.pande\.claude\skills\slack-scrape\SKILL.md`

This task creates the skill skeleton: frontmatter, description, argument parsing instructions, and the top-level routing logic (Phase 1 vs Phase 2).

- [ ] **Step 1: Create the skill directory**

Run:
```bash
mkdir -p "$HOME/.claude/skills/slack-scrape"
```

- [ ] **Step 2: Write the skill file with frontmatter and argument parser**

Create `C:\Users\pratyush.pande\.claude\skills\slack-scrape\SKILL.md` with:

```markdown
---
name: slack-scrape
description: >
  Use when the user wants to scrape their Slack activity, export Slack messages,
  create a Slack backup, or says "/slack-scrape". Discovers messages, mentions,
  and reactions for a date range, then fetches full context into markdown files.
---

# Slack Scrape

Scrape your Slack activity into structured markdown files for Pensieve ingest.

## Argument Parsing

Parse the user's input to determine which phase to run:

**Phase 1 — Discover & Index:**
```
/slack-scrape <start-date> [end-date] [--channel <name>]
```
- `start-date` (required): ISO date `YYYY-MM-DD`, inclusive
- `end-date` (optional): ISO date `YYYY-MM-DD`, inclusive. Defaults to today.
- `--channel` (optional): limit discovery to a specific channel name

**Phase 2 — Fetch (resumable):**
```
/slack-scrape --fetch <path-to-index.json>
```
- `--fetch` flag with a path to an existing `index.json`

**Routing:**
- If the args contain `--fetch`, run Phase 2 (fetch workflow below)
- Otherwise, run Phase 1 (discovery workflow below)

## Constants

- `USER_ID`: `U07ENJD06T0`
- `USERNAME`: `pratyush.pande`
```

- [ ] **Step 3: Verify the skill is discoverable**

Run:
```bash
ls "$HOME/.claude/skills/slack-scrape/SKILL.md"
```
Expected: file exists at the path.

Then test skill discovery by starting a new Claude Code session and checking if `/slack-scrape` appears as a skill. If it doesn't appear, verify the frontmatter `name` field matches `slack-scrape`.

- [ ] **Step 4: Commit**

Note: The skill lives outside the repo directory at `~/.claude/skills/slack-scrape/SKILL.md`. Do NOT commit the skill file to the Pensieve repo — it's a user-level Claude Code skill. The repo reference file (`SLACK-SCRAPE-SKILL.md`) will be created in Task 7.

```bash
cd /c/src/Pensieve-slack-scrape
git commit --allow-empty -m "feat: add slack-scrape skill skeleton with argument parsing"
```

---

### Task 2: Implement Phase 1 — Discovery workflow

**Files:**
- Modify: `C:\Users\pratyush.pande\.claude\skills\slack-scrape\SKILL.md`

This task adds the complete Phase 1 instructions to the skill: search queries, deduplication, date bucketing, index writing, and summary output.

- [ ] **Step 1: Add the slugify helper section**

Append to SKILL.md after the Constants section:

```markdown
## Helpers

### Slugify a channel name

To convert a channel name to a filesystem-safe slug:
1. Lowercase the name
2. Replace any run of non-alphanumeric characters with a single `-`
3. Trim leading and trailing `-`
4. If the result is empty, use `channel`

Examples:
- `Engineering General` → `engineering-general`
- `dm-with-Jane Smith` → `dm-with-jane-smith`
- `""` (empty/unnamed DM) → `channel`
```

- [ ] **Step 2: Add the Phase 1 discovery workflow**

Append to SKILL.md:

```markdown
## Phase 1: Discover & Index

### Step 1 — Resolve user timezone

Call `slack_read_user_profile` with no arguments (defaults to current user).
Extract the `tz` field (e.g. `Asia/Kolkata`). Store this for date bucketing.
If the timezone is not available, default to `UTC`.

### Step 2 — Calculate date boundaries

Given `start-date` and `end-date` (inclusive):
- Convert `start-date 00:00:00` in the user's timezone to a Unix timestamp → `oldest_ts`
- Convert `end-date+1 00:00:00` in the user's timezone to a Unix timestamp → `newest_ts`
- For Slack search date filters: `after:YYYY-MM-DD` uses the start date, `before:YYYY-MM-DD` uses end-date + 1 day

### Step 3 — Run search queries

Run three searches using `slack_search_public_and_private`. For each query:
- Set `response_format: "concise"` and `include_context: false`
- Set `sort: "timestamp"` and `sort_dir: "asc"`
- Paginate using `cursor` until no more results (cursor is empty/null)
- Collect all results into a flat list

**Query 1 — Your messages:**
```
query: "from:<@U07ENJD06T0> after:YYYY-MM-DD before:YYYY-MM-DD"
```
(where after = start-date, before = end-date + 1 day)

If `--channel` is specified, add `in:<channel-name>` to the query.

**Query 2 — Mentions of you:**
```
query: "to:<@U07ENJD06T0> after:YYYY-MM-DD before:YYYY-MM-DD"
```

If `--channel` is specified, add `in:<channel-name>` to the query.

**Query 3 — Your reactions:**
```
query: "hasmy::*: after:YYYY-MM-DD before:YYYY-MM-DD"
```

If this query returns an error or zero results with a warning, log:
"Warning: Reaction search may not be supported. Only messages and mentions were indexed."
Continue without failing.

If `--channel` is specified, add `in:<channel-name>` to the query.

### Step 4 — Deduplicate and build index

From all collected results:

1. **Extract fields** from each search result:
   - `channel_id`: the channel/conversation ID
   - `channel_name`: the channel display name (or DM participant name)
   - `ts`: the message timestamp
   - `text`: first ~100 characters as preview
   - `type`: classify as `message` (from query 1), `mention` (query 2), or `reaction` (query 3)

2. **Deduplicate** by `(channel_id, ts)` pair. If a message appears in multiple queries, keep the first occurrence but merge the types (e.g. a message you sent that also mentions you → type remains `message`).

3. **Slugify** each channel name using the helper above.

4. **Date-bucket** each hit: convert the `ts` (Unix timestamp) to `YYYY-MM-DD` in the user's timezone.

5. **Build the index JSON:**

```json
{
  "user_id": "U07ENJD06T0",
  "user_tz": "<timezone from step 1>",
  "date_range": ["<start-date>", "<end-date>"],
  "created_at": "<current ISO datetime>",
  "channels": {
    "<channel_id>": {
      "channel_id": "<channel_id>",
      "channel_name": "<display name>",
      "channel_slug": "<slugified name>",
      "type": "<public_channel|private_channel|im|mpim>",
      "hits": [
        {
          "ts": "<message timestamp>",
          "type": "<message|mention|reaction>",
          "date": "<YYYY-MM-DD>",
          "preview": "<first ~100 chars>"
        }
      ]
    }
  },
  "status": {},
  "stats": {
    "total_hits": 0,
    "channels": 0,
    "days": 0
  }
}
```

6. **Populate status map:** For each unique `(channel_id, date)` pair found in hits, add an entry to `status`:
```json
"status": {
  "<channel_id>": {
    "<YYYY-MM-DD>": "pending"
  }
}
```

7. **Calculate stats:**
   - `total_hits`: total number of deduplicated hits
   - `channels`: number of unique channel_ids
   - `days`: number of unique dates across all channels

### Step 5 — Write the index file

Create the directory and write the index:

```bash
mkdir -p raw/slack/scrape-<start-date>_<end-date>
```

Write `raw/slack/scrape-<start-date>_<end-date>/index.json` using the Write tool.

### Step 6 — Print summary

Print to the user:

```
Slack activity index created:
- Date range: <start-date> to <end-date>
- Total hits: <N> (messages: <n>, mentions: <n>, reactions: <n>)
- Channels: <N>
- Days with activity: <N>
- Index saved to: raw/slack/scrape-<start>_<end>/index.json

To fetch full content, run:
/slack-scrape --fetch raw/slack/scrape-<start>_<end>/index.json
```
```

- [ ] **Step 3: Commit**

```bash
cd /c/src/Pensieve-slack-scrape
git commit -am "feat: add Phase 1 discovery workflow to slack-scrape skill"
```

---

### Task 3: Implement Phase 2 — Fetch workflow

**Files:**
- Modify: `C:\Users\pratyush.pande\.claude\skills\slack-scrape\SKILL.md`

This task adds the complete Phase 2 instructions: reading the index, fetching threads and channel context, resolving users, reading canvases, writing markdown, and updating the index.

- [ ] **Step 1: Add the user name cache section**

Append to SKILL.md after Phase 1:

```markdown
## User Name Cache

Maintain a map of `user_id → display_name` across the entire Phase 2 run.
Before calling `slack_read_user_profile` for a user, check if the ID is already
in the cache. This avoids redundant MCP calls.

Initialize the cache with:
```json
{"U07ENJD06T0": "Pratyush Pande"}
```
```

- [ ] **Step 2: Add the Phase 2 fetch workflow**

Append to SKILL.md:

```markdown
## Phase 2: Fetch

### Step 1 — Read and validate the index

Read the index.json file specified by `--fetch`. Validate:
- File exists and is valid JSON
- Has `channels`, `status`, and `date_range` fields

Extract `user_tz` from the index (default to `UTC` if missing).

### Step 2 — Identify pending work

Collect all `(channel_id, date)` pairs from `status` where the value is
`"pending"` or `"error"`. Sort chronologically (oldest date first, then by
channel_id for determinism).

If no pending work remains, print:
"All channel-days already fetched. Nothing to do."
And stop.

Otherwise, print:
"Resuming fetch: <N> channel-days remaining out of <total>."

### Step 3 — Process each channel-day

For each pending `(channel_id, date)` pair:

**3a. Announce progress:**
Print: `Fetching <channel_name> / <date> ...`

**3b. Fetch channel context for the day:**

Convert date boundaries to Unix timestamps using `user_tz`:
- `day_start` = `<date> 00:00:00` in user_tz → Unix timestamp
- `day_end` = `<date+1> 00:00:00` in user_tz → Unix timestamp

Call `slack_read_channel` with:
- `channel_id`: the channel ID
- `oldest`: `day_start` as string
- `latest`: `day_end` as string
- `limit`: 100
- `response_format`: `"detailed"`

If `next_cursor` is returned, paginate by calling again with `cursor` until all
messages for the day are collected.

Store all messages as `channel_messages` (list, ordered by timestamp ascending).

**3c. Expand threads:**

Look at the hits for this channel-day in the index. For each hit `ts`:
- Find the message in `channel_messages` with that `ts`
- If the message has a `thread_ts` and it's different from its own `ts`, this
  message is a thread reply — find the parent `thread_ts` instead
- If the message IS a thread parent (has `reply_count > 0` or is referenced as
  a `thread_ts`), call `slack_read_thread` with:
  - `channel_id`: the channel ID
  - `message_ts`: the thread parent `ts`
  - `response_format`: `"detailed"`

Deduplicate threads by `thread_ts` — don't fetch the same thread twice.

Store threads as `threads` (map of `thread_ts → list of reply messages`).

**3d. Resolve user names:**

Collect all unique `user` / `user_id` fields from `channel_messages` and all
thread replies. For each ID not in the user name cache:
- Call `slack_read_user_profile` with `user_id`
- Extract `display_name` or `real_name` (prefer display_name if non-empty)
- Add to cache

**3e. Read inline content:**

Scan all messages (channel + thread replies) for:
- **Canvas references**: If a message contains a canvas ID (format `F[A-Z0-9]+`
  in a canvas link), call `slack_read_canvas` with `canvas_id` and store the
  markdown content.
- **File attachments**: Extract file metadata — `name`, `filetype`, `size`,
  `url_private` (permalink), `user` (uploader). Store in a `files` list.
- **Links**: Extract any URLs from message text. No special handling needed —
  they'll appear naturally in the message content.

**3f. Assemble and write markdown:**

Build the markdown file following the output format below, then write it to:
`raw/slack/scrape-<start>_<end>/<date>/<channel-slug>--<channel-id>.md`

Create the date directory first:
```bash
mkdir -p "raw/slack/scrape-<start>_<end>/<date>"
```

**3g. Update index status:**

Set `status[channel_id][date]` to `"done"`. Write the entire index.json back to
disk immediately using the Write tool. This is the resume checkpoint — if the
process stops after this write, the next run will skip this channel-day.

**3h. Error handling:**

If any MCP call in steps 3b-3f fails:
- Set `status[channel_id][date]` to `"error"` in the index
- Write the index to disk (so the error state is persisted)
- Print: `Error fetching <channel_name> / <date>: <error message>. Continuing...`
- Continue to the next channel-day (do NOT stop the entire run)

### Step 4 — Print completion summary

After all channel-days are processed, print:

```
Fetch complete:
- Done: <N> channel-days
- Errors: <N> channel-days
- Files written to: raw/slack/scrape-<start>_<end>/

To ingest into the wiki, run:
  Ingest raw/slack/scrape-<start>_<end>/
```

If there were errors:
```
To retry errors, run:
/slack-scrape --fetch raw/slack/scrape-<start>_<end>/index.json
```
```

- [ ] **Step 3: Commit**

```bash
cd /c/src/Pensieve-slack-scrape
git commit -am "feat: add Phase 2 fetch workflow to slack-scrape skill"
```

---

### Task 4: Add the output markdown format template

**Files:**
- Modify: `C:\Users\pratyush.pande\.claude\skills\slack-scrape\SKILL.md`

This task adds the exact markdown template that Phase 2 Step 3f uses to assemble output files.

- [ ] **Step 1: Add the markdown format section**

Append to SKILL.md before the Phase 2 section (or after Phase 2 as a reference section):

```markdown
## Output Markdown Format

When assembling the markdown file for a channel-day, use this exact structure:

### Frontmatter

```yaml
---
type: slack-scrape
channel: <channel_name>
channel_id: <channel_id>
channel_type: <public_channel|private_channel|im|mpim>
date: <YYYY-MM-DD>
scrape_range: <start-date> to <end-date>
user: pratyush.pande
---
```

### Heading

```markdown
# <channel_name> — <YYYY-MM-DD>
```

### Channel Context section

List ALL messages from `channel_messages` in chronological order. For each
message:

```markdown
### HH:MM — <Display Name>[ ⭐]
<message text>
```

- `HH:MM` = message timestamp converted to the user's timezone
- `Display Name` = resolved from user name cache
- Append ` ⭐` if the message was sent by `U07ENJD06T0` (the user)
- Preserve the message text as-is. Convert Slack user references `<@U...>` to
  `@Display Name` using the cache. Convert channel references `<#C...|name>`
  to `#name`.

### Thread sections

For each thread in `threads` (ordered by parent timestamp):

```markdown
---

## Thread: <first ~60 chars of parent message>
_Parent by <Display Name> at HH:MM — <N> replies_

> **HH:MM — <Display Name>**[ ⭐]
> <message text line 1>
> <message text line 2>

> **HH:MM — <Display Name>**[ ⭐]
> <reply text>
```

- Each reply is a blockquote block
- Separate replies with a blank line between blockquote blocks
- ⭐ marker on the user's own messages
- Convert Slack references same as channel context

### Files & Links table

If any files were found in channel or thread messages:

```markdown
---

## Files & Links

| File | Type | Shared by | Link |
|---|---|---|---|
| <filename> | <filetype> | <Display Name> | [Slack link](<url>) |
```

If no files were found, omit this entire section.

### Canvas sections

For each canvas that was successfully read:

```markdown
## Canvas: <canvas title or "Untitled">
_Canvas ID: <canvas_id>, created by <Display Name>_

> <inlined canvas markdown content, each line prefixed with > >
```

If no canvases were found, omit this section.

### Footer

```markdown
---

_Scraped by pensieve slack-scrape on <today's date YYYY-MM-DD>_
```
```

- [ ] **Step 2: Commit**

```bash
cd /c/src/Pensieve-slack-scrape
git commit -am "feat: add output markdown format template to slack-scrape skill"
```

---

### Task 5: Smoke test Phase 1 against live Slack

**Files:**
- No code changes — this is a validation task

Test the skill by running Phase 1 against the live Slack workspace with a narrow date range (1-2 days) to minimize MCP calls.

- [ ] **Step 1: Run Phase 1 with a 1-day range**

In a Claude Code session, run:
```
/slack-scrape 2026-04-10 2026-04-10
```

- [ ] **Step 2: Verify index output**

Read `raw/slack/scrape-2026-04-10_2026-04-10/index.json` and verify:
- `user_id` is `U07ENJD06T0`
- `date_range` is `["2026-04-10", "2026-04-10"]`
- `channels` map has entries with valid `channel_id`, `channel_name`, `channel_slug`
- `hits` arrays have `ts`, `type`, `date`, `preview` fields
- `status` map has `"pending"` entries for each channel-day
- `stats` counts match the data

- [ ] **Step 3: Check for issues and fix**

If the index has problems (missing fields, wrong format, empty results when
activity is expected), adjust the skill's Phase 1 instructions and re-test.

- [ ] **Step 4: Commit any fixes**

```bash
cd /c/src/Pensieve-slack-scrape
git commit -am "fix: adjust Phase 1 based on smoke test results"
```

---

### Task 6: Smoke test Phase 2 against live Slack

**Files:**
- No code changes — this is a validation task

Test Phase 2 using the index from Task 5.

- [ ] **Step 1: Run Phase 2**

```
/slack-scrape --fetch raw/slack/scrape-2026-04-10_2026-04-10/index.json
```

- [ ] **Step 2: Verify output markdown files**

For each generated markdown file in `raw/slack/scrape-2026-04-10_2026-04-10/`:
- Has correct YAML frontmatter
- Has `# channel-name — date` heading
- Channel Context section has timestamped messages
- ⭐ markers appear on your messages
- Thread sections show full thread content
- User IDs are resolved to display names (no raw `U...` IDs in output)
- Files & Links table appears if files were shared
- Filename follows `<slug>--<channel-id>.md` pattern

- [ ] **Step 3: Verify resume behavior**

Check that `index.json` now shows `"done"` for all processed channel-days.

Then run Phase 2 again:
```
/slack-scrape --fetch raw/slack/scrape-2026-04-10_2026-04-10/index.json
```

It should print: "All channel-days already fetched. Nothing to do."

- [ ] **Step 4: Commit any fixes**

```bash
cd /c/src/Pensieve-slack-scrape
git commit -am "fix: adjust Phase 2 based on smoke test results"
```

---

### Task 7: Add the skill reference file to the repo

**Files:**
- Create: `C:\src\Pensieve-slack-scrape\SLACK-SCRAPE-SKILL.md`
- Modify: `C:\src\Pensieve-slack-scrape\README.md`

Add documentation about the skill to the repo so it's discoverable.

- [ ] **Step 1: Create the skill reference file**

Create `SLACK-SCRAPE-SKILL.md` with:

```markdown
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
```

- [ ] **Step 2: Update README.md**

Add a section to README.md about the Slack scrape skill, after the existing "Development" section:

```markdown
## Slack Scrape

A Claude Code skill that scrapes your Slack activity into `raw/slack/` for
wiki ingest.  See [SLACK-SCRAPE-SKILL.md](SLACK-SCRAPE-SKILL.md) for usage.
```

- [ ] **Step 3: Commit**

```bash
cd /c/src/Pensieve-slack-scrape
git add SLACK-SCRAPE-SKILL.md README.md
git commit -m "docs: add slack-scrape skill reference and update README"
```

- [ ] **Step 4: Push all changes**

```bash
cd /c/src/Pensieve-slack-scrape
git push
```
