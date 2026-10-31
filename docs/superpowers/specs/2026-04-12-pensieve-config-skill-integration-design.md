---
date: 2026-04-12
status: draft
topic: pensieve-config-skill-integration
---

# Pensieve Global Config & Slack-Scrape Skill Integration

## Problem

The `slack-scrape` skill currently hardcodes "Pensieve project root" as the
base path for raw scrape output. This works only when the skill is invoked
from inside `C:\src\Pensieve` and assumes the user has exactly one wiki at a
known location. As Pensieve matures into a pip/npm-installable package,
the skill needs a stable, location-independent way to discover where the
wiki lives.

## Goal

Introduce a user-level config file written by `pensieve init` and read by
both the `pensieve` CLI and the `slack-scrape` skill. The skill should be
able to write raw Slack data to the configured wiki root regardless of the
current working directory.

## Non-goals

- Multi-wiki support. Pensieve is the LLM Wiki — there is one wiki per user
  in the MVP. Multi-wiki can be added later without breaking the v1 schema.
- Migrating other skills or external tools. Only `slack-scrape` is in scope.
- Replacing the existing `find_wiki_root()` cwd-walk fallback. It stays as
  a secondary path for in-repo development ergonomics.

## Architecture

A single user-level config file is the contract between Pensieve and any
tool that needs to know where the wiki lives. `pensieve init` writes it;
`pensieve` commands and the slack-scrape skill read it.

```
~/.pensieve/config.toml          ← single source of truth
        ▲                ▲
        │                │
   pensieve init     pensieve root
   (writes)          (reads, prints wiki_root)
                          ▲
                          │
                  /slack-scrape skill
                  (shells out, writes raw/slack/...)
```

The skill never parses TOML itself and never walks directories — it asks
`pensieve root` and trusts the answer. Pensieve owns config format and
discovery; the skill owns Slack scraping. Clean boundary.

## Config file

**Location:** `~/.pensieve/config.toml` (resolved via `Path.home()`).

`~/.pensieve/` was chosen over `platformdirs` because it adds no dependency,
behaves identically across Windows/macOS/Linux, and matches the pattern used
by `gh`, `aws`, and `docker`. A single-file config does not justify the
indirection that `platformdirs` introduces.

**Schema (v1):**

```toml
schema_version = 1
wiki_root = "C:/src/Pensieve"
```

- `schema_version` — integer. Future versions can migrate or refuse to load.
- `wiki_root` — absolute path to the wiki directory (the one created by
  `pensieve init`, containing a `wiki/` subdirectory). A schema file
  (`CLAUDE.md` or `AGENTS.md`) is *not* required for validity, since
  `pensieve init` does not create or copy schema files — they are added
  manually as a follow-up step. Validation checks only that the path
  exists and contains a `wiki/` directory.

**Reading rules:**

- TOML parsing: use stdlib `tomllib` on Python 3.11+, fall back to the
  `tomli` backport package on Python 3.9–3.10. The project's
  `requires-python = ">=3.9"` constraint must not be raised by this change.
  Add `tomli; python_version < "3.11"` to the project dependencies.
- Missing file → `Pensieve is not initialised. Run 'pensieve init <path>' first.`
- Missing or empty `wiki_root` → `Config is missing 'wiki_root'. Re-run 'pensieve init <path>'.`
- `wiki_root` set in config but path does not exist on disk, or is not a
  directory, or does not contain a `wiki/` subdirectory →
  `Configured wiki_root is not a valid wiki: <path>. Re-run 'pensieve init' or fix ~/.pensieve/config.toml.`
- `schema_version` greater than supported →
  `Config schema version <N> is newer than this Pensieve (<M>). Upgrade pensieve.`

**Writing rules:**

- `pensieve init` is the only writer.
- Atomic write: write to `config.toml.tmp` in the same directory as the
  destination, then call `os.replace()` to atomically replace the existing
  file. `os.replace()` is the cross-platform primitive — plain `os.rename`
  is not atomic on Windows when the destination already exists.
- Parent dir `~/.pensieve/` is created if missing.

## CLI changes

All changes live in `src/pensieve/`.

### New module: `src/pensieve/config.py`

Owns everything config-related. Keeps `wiki.py` focused on wiki I/O.

```python
SCHEMA_VERSION = 1
CONFIG_PATH = Path.home() / ".pensieve" / "config.toml"

def load_config() -> dict          # reads CONFIG_PATH, validates, raises ConfigError
def write_config(wiki_root: Path)  # atomic write, creates parent dir
def get_wiki_root() -> Path        # convenience: validated Path

class ConfigError(Exception): ...
```

`ConfigError` carries human-friendly messages. The CLI catches it at the
top level, prints to stderr, and exits 1.

### Modified: `pensieve init <path>` (`cli.py`)

New behavior, in order:

1. Resolve `<path>` to absolute.
2. Call existing `init_wiki(root)` to scaffold `wiki/`, `raw/`, `raw/assets/`, seeds.
3. Call `write_config(root)` to register it globally.
4. Echo:
   - `✓ Wiki initialised at <root>`
   - `✓ Registered as active wiki in ~/.pensieve/config.toml`

If `~/.pensieve/config.toml` already exists with a different `wiki_root`,
prompt before overwriting (unless `--force` is passed). Re-running init by
accident must not silently re-point the global config.

### New: `pensieve root` (`cli.py`)

```
$ pensieve root
C:/src/Pensieve
```

- Prints `wiki_root` from the config to stdout, no trailing decoration, exit 0.
- On any `ConfigError`, prints message to stderr and exits 1.
- Designed to be `$(pensieve root)`-friendly. This is the skill's
  integration point.

### Modified: `find_wiki_root()` in `wiki.py`

Updated so it prefers the configured root when available:

1. Try `get_wiki_root()` from config — if it succeeds, return that.
2. Fall back to existing cwd-walk behavior (preserves dev ergonomics
   when running from inside the repo without a config).
3. If both fail, return cwd as today.

Existing commands (`search`, `lint`, `log-entry`, `rebuild-index`)
automatically benefit from the global config without per-command changes.
The `--root` flag still overrides everything.

## Skill changes (`~/.claude/skills/slack-scrape/SKILL.md`)

Small, surgical edits. The skill currently says "Use the Pensieve project
root as the base path" in two places (Phase 1 Step 5, Phase 2 Step 3).
Both get replaced with the same pattern.

### New prerequisite step — "Resolve target wiki root"

Add as Step 0, runs once per invocation, before Phase 1 or Phase 2 work:

> Run `pensieve root` via Bash. Capture stdout (trimmed) as `WIKI_ROOT`.
> This is the absolute path where all scrape output will be written.
>
> If the command exits non-zero, abort with the stderr message — do **not**
> fall back to cwd, do **not** guess. The user must run `pensieve init <path>`
> first.
>
> All paths in the rest of this skill are relative to `WIKI_ROOT`. Wherever
> the skill currently says "Pensieve project root", it now means `WIKI_ROOT`.

### Path replacements

- Phase 1 Step 5: `raw/slack/scrape-<start>_<end>/index.json` →
  `<WIKI_ROOT>/raw/slack/scrape-<start>_<end>/index.json`
- Phase 2 Step 3: `raw/slack/scrape-<start>_<end>/<YYYY-MM-DD>/<channel-slug>--<channel-id>.md` →
  `<WIKI_ROOT>/raw/slack/...`
- Summary print lines (Phase 1 Step 6, Phase 2 Step 4) updated to show
  absolute paths so the user can copy-paste them.

### `--fetch` argument handling

Today the user runs `/slack-scrape --fetch raw/slack/scrape-X_Y/index.json`.
Two acceptable forms after this change:

- **Absolute path** — used as-is.
- **Relative path** — resolved against `WIKI_ROOT`, not cwd. Preserves the
  existing copy-paste UX from the Phase 1 summary.

The skill validates the resolved path exists before doing anything else.

### Out of scope

No other behavioral changes. Identity resolution, MCP calls, channel
slugging, markdown format, canvas handling — all untouched. This change is
purely about *where* output lands.

## Error handling

One coherent error story across both layers.

### Pensieve CLI (`ConfigError` cases)

| Situation | Message | Exit |
|---|---|---|
| `~/.pensieve/config.toml` missing | `Pensieve is not initialised. Run 'pensieve init <path>' first.` | 1 |
| File exists, malformed TOML | `Invalid config at ~/.pensieve/config.toml: <parse error>` | 1 |
| `wiki_root` missing/empty | `Config is missing 'wiki_root'. Re-run 'pensieve init <path>'.` | 1 |
| `wiki_root` path is not a valid wiki directory | `Configured wiki_root is not a valid wiki: <path>. Re-run 'pensieve init' or fix ~/.pensieve/config.toml.` | 1 |
| `schema_version` greater than supported | `Config schema version <N> is newer than this Pensieve (<M>). Upgrade pensieve.` | 1 |
| `pensieve init` finds existing config pointing elsewhere | Prompt: `Existing config points to <old>. Overwrite? [y/N]` (or `--force` to skip) | 0/1 |

All messages go to stderr. `pensieve root` only writes to stdout on success
— never mixed.

### Skill layer

The skill does no error categorization of its own. It runs `pensieve root`,
and on non-zero exit, surfaces stderr verbatim to the user and aborts. The
Pensieve CLI already produced an actionable message — the skill should not
paraphrase or swallow it.

## Testing

### Unit tests (`tests/test_config.py`, new file)

- `write_config` creates parent dir, writes valid TOML, atomic rename works.
- `load_config` round-trips a written config.
- Each `ConfigError` case above has a test asserting the message and
  exception type.
- `get_wiki_root` returns a `Path` and validates existence.

### Integration tests (extend existing CLI tests)

- `pensieve init <tmpdir>` creates both the wiki scaffold and the config
  file pointing at it.
- `pensieve root` after init prints the expected absolute path on stdout,
  exits 0.
- `pensieve root` with no config prints error to stderr, exits 1.
- `pensieve init` over an existing config with a different root prompts;
  `--force` skips the prompt.
- `find_wiki_root()` returns the configured root when a config exists, even
  when called from an unrelated cwd.

### Skill testing

Manual smoke test only — invoke `/slack-scrape` from a directory outside
`C:\src\Pensieve` and confirm files land under the configured `wiki_root`.
No automated test for the skill itself; it is prose, not code.

### Test isolation

Config tests must use a temp HOME (monkeypatch `Path.home`) so they never
touch the real `~/.pensieve/config.toml`. Critical — easy to forget,
painful when forgotten.
