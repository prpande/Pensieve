# Pensieve Global Config & Slack-Scrape Skill Integration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a user-level Pensieve config (`~/.pensieve/config.toml`) written by `pensieve init` and read by both the `pensieve` CLI and the `/slack-scrape` skill, so the skill can write raw output to the configured wiki root from any working directory.

**Architecture:** A new `pensieve.config` module owns config I/O. `pensieve init` writes the config atomically. A new `pensieve root` command prints the configured wiki root to stdout — this is the integration point the slack-scrape skill calls. `find_wiki_root()` is updated to prefer the configured root, with the existing cwd-walk as a fallback.

**Tech Stack:** Python 3.9+, Click, stdlib `tomllib` (3.11+) with `tomli` backport for 3.9–3.10, pytest, monkeypatch for HOME isolation.

**Spec:** `docs/superpowers/specs/2026-04-12-pensieve-config-skill-integration-design.md`

---

## File Structure

**Create:**
- `src/pensieve/config.py` — config I/O, validation, `ConfigError`. New module so `wiki.py` stays focused on wiki content.
- `tests/test_config.py` — unit tests for the config module with HOME monkeypatching.

**Modify:**
- `pyproject.toml` — add conditional `tomli` dependency for Python <3.11.
- `src/pensieve/cli.py` — extend `init` command, add new `root` command, top-level `ConfigError` handling.
- `src/pensieve/wiki.py` — `find_wiki_root()` prefers configured root.
- `tests/test_cli.py` — integration tests for `init`+config and the new `root` command.
- `~/.claude/skills/slack-scrape/SKILL.md` — new "Resolve target wiki root" prerequisite step, path replacements, `--fetch` relative-path resolution.

**Test isolation rule:** every test that touches config must monkeypatch `pensieve.config.CONFIG_PATH` to point under `tmp_path`. Never use the real `Path.home()` in tests.

---

## Task 1: Add `tomli` backport dependency

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Update dependencies**

In `pyproject.toml`, change the `dependencies` array to include the conditional backport:

```toml
dependencies = [
    "click>=8.0",
    "tomli>=2.0; python_version < '3.11'",
]
```

- [ ] **Step 2: Reinstall the package in editable mode**

Run: `pip install -e .`
Expected: success, no resolver errors. On Python 3.11+ `tomli` is skipped; on 3.9/3.10 it installs.

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "Add tomli backport for Python <3.11"
```

---

## Task 2: Create `pensieve.config` module skeleton with `ConfigError`

**Files:**
- Create: `src/pensieve/config.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_config.py`:

```python
"""Tests for pensieve.config — global user config I/O."""

from __future__ import annotations

from pathlib import Path

import pytest

from pensieve import config as cfg
from pensieve.config import ConfigError


@pytest.fixture
def fake_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect CONFIG_PATH under tmp_path so tests never touch real ~/.pensieve."""
    fake_config = tmp_path / "home" / ".pensieve" / "config.toml"
    monkeypatch.setattr(cfg, "CONFIG_PATH", fake_config)
    return fake_config


def test_config_error_is_exception() -> None:
    err = ConfigError("boom")
    assert isinstance(err, Exception)
    assert str(err) == "boom"


def test_schema_version_constant() -> None:
    assert cfg.SCHEMA_VERSION == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pensieve.config'`.

- [ ] **Step 3: Create the module**

Create `src/pensieve/config.py`:

```python
"""Pensieve user-level configuration.

A single TOML file at ~/.pensieve/config.toml is the contract between the
pensieve CLI and any external tool (e.g. the slack-scrape skill) that needs
to know where the wiki lives.
"""

from __future__ import annotations

from pathlib import Path

SCHEMA_VERSION = 1
CONFIG_PATH = Path.home() / ".pensieve" / "config.toml"


class ConfigError(Exception):
    """Raised when the user-level Pensieve config is missing or invalid."""
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/test_config.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add src/pensieve/config.py tests/test_config.py
git commit -m "Add pensieve.config module skeleton with ConfigError"
```

---

## Task 3: Implement `write_config` with atomic replace

**Files:**
- Modify: `src/pensieve/config.py`
- Modify: `tests/test_config.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_config.py`:

```python
def test_write_config_creates_parent_dir(fake_home: Path, tmp_path: Path) -> None:
    wiki_root = tmp_path / "mywiki"
    wiki_root.mkdir()
    cfg.write_config(wiki_root)
    assert fake_home.exists()
    assert fake_home.parent.is_dir()


def test_write_config_writes_valid_toml(fake_home: Path, tmp_path: Path) -> None:
    wiki_root = tmp_path / "mywiki"
    wiki_root.mkdir()
    cfg.write_config(wiki_root)
    text = fake_home.read_text(encoding="utf-8")
    assert "schema_version = 1" in text
    assert f'wiki_root = "{wiki_root.as_posix()}"' in text


def test_write_config_overwrites_existing(fake_home: Path, tmp_path: Path) -> None:
    wiki_a = tmp_path / "wiki-a"
    wiki_b = tmp_path / "wiki-b"
    wiki_a.mkdir()
    wiki_b.mkdir()
    cfg.write_config(wiki_a)
    cfg.write_config(wiki_b)
    text = fake_home.read_text(encoding="utf-8")
    assert wiki_b.as_posix() in text
    assert wiki_a.as_posix() not in text


def test_write_config_no_temp_file_left_behind(fake_home: Path, tmp_path: Path) -> None:
    wiki_root = tmp_path / "mywiki"
    wiki_root.mkdir()
    cfg.write_config(wiki_root)
    leftovers = list(fake_home.parent.glob("*.tmp"))
    assert leftovers == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_config.py -v`
Expected: FAIL with `AttributeError: module 'pensieve.config' has no attribute 'write_config'`.

- [ ] **Step 3: Implement `write_config`**

Append to `src/pensieve/config.py`:

```python
import os


def write_config(wiki_root: Path) -> None:
    """Write the user-level config pointing at *wiki_root*.

    Performs an atomic replace via os.replace() so concurrent readers either
    see the old file or the new file, never a partial write. Cross-platform
    safe — plain os.rename is not atomic on Windows when the destination
    already exists.
    """
    wiki_root = wiki_root.resolve()
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = CONFIG_PATH.with_suffix(CONFIG_PATH.suffix + ".tmp")
    contents = (
        f"schema_version = {SCHEMA_VERSION}\n"
        f'wiki_root = "{wiki_root.as_posix()}"\n'
    )
    tmp_path.write_text(contents, encoding="utf-8")
    os.replace(tmp_path, CONFIG_PATH)
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/test_config.py -v`
Expected: PASS (6 tests total).

- [ ] **Step 5: Commit**

```bash
git add src/pensieve/config.py tests/test_config.py
git commit -m "Implement write_config with os.replace atomic write"
```

---

## Task 4: Implement `load_config` with TOML compat shim

**Files:**
- Modify: `src/pensieve/config.py`
- Modify: `tests/test_config.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_config.py`:

```python
def test_load_config_missing_file_raises(fake_home: Path) -> None:
    with pytest.raises(ConfigError) as exc:
        cfg.load_config()
    assert "not initialised" in str(exc.value)
    assert "pensieve init" in str(exc.value)


def test_load_config_round_trip(fake_home: Path, tmp_path: Path) -> None:
    wiki_root = tmp_path / "mywiki"
    wiki_root.mkdir()
    cfg.write_config(wiki_root)
    data = cfg.load_config()
    assert data["schema_version"] == 1
    assert data["wiki_root"] == wiki_root.as_posix()


def test_load_config_malformed_toml_raises(fake_home: Path) -> None:
    fake_home.parent.mkdir(parents=True, exist_ok=True)
    fake_home.write_text("this is = = not toml", encoding="utf-8")
    with pytest.raises(ConfigError) as exc:
        cfg.load_config()
    assert "Invalid config" in str(exc.value)


def test_load_config_missing_wiki_root_raises(fake_home: Path) -> None:
    fake_home.parent.mkdir(parents=True, exist_ok=True)
    fake_home.write_text("schema_version = 1\n", encoding="utf-8")
    with pytest.raises(ConfigError) as exc:
        cfg.load_config()
    assert "missing 'wiki_root'" in str(exc.value)


def test_load_config_empty_wiki_root_raises(fake_home: Path) -> None:
    fake_home.parent.mkdir(parents=True, exist_ok=True)
    fake_home.write_text('schema_version = 1\nwiki_root = ""\n', encoding="utf-8")
    with pytest.raises(ConfigError) as exc:
        cfg.load_config()
    assert "missing 'wiki_root'" in str(exc.value)


def test_load_config_future_schema_version_raises(fake_home: Path, tmp_path: Path) -> None:
    fake_home.parent.mkdir(parents=True, exist_ok=True)
    fake_home.write_text(
        f'schema_version = 99\nwiki_root = "{tmp_path.as_posix()}"\n',
        encoding="utf-8",
    )
    with pytest.raises(ConfigError) as exc:
        cfg.load_config()
    assert "newer than this Pensieve" in str(exc.value)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_config.py -v`
Expected: FAIL with `AttributeError: module 'pensieve.config' has no attribute 'load_config'`.

- [ ] **Step 3: Add the TOML compat shim and `load_config`**

At the top of `src/pensieve/config.py`, after the existing imports, add:

```python
try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]
```

Then append the function:

```python
def load_config() -> dict:
    """Load and validate the user-level Pensieve config.

    Raises ConfigError with a human-friendly message on any problem.
    Validation here is purely about the config file itself — it does NOT
    check that wiki_root exists on disk. Use get_wiki_root() for that.
    """
    if not CONFIG_PATH.exists():
        raise ConfigError(
            "Pensieve is not initialised. Run 'pensieve init <path>' first."
        )
    try:
        with CONFIG_PATH.open("rb") as fh:
            data = tomllib.load(fh)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"Invalid config at {CONFIG_PATH}: {exc}") from exc

    schema_version = data.get("schema_version", 0)
    if isinstance(schema_version, int) and schema_version > SCHEMA_VERSION:
        raise ConfigError(
            f"Config schema version {schema_version} is newer than this "
            f"Pensieve ({SCHEMA_VERSION}). Upgrade pensieve."
        )

    wiki_root = data.get("wiki_root")
    if not wiki_root:
        raise ConfigError(
            "Config is missing 'wiki_root'. Re-run 'pensieve init <path>'."
        )

    return data
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/test_config.py -v`
Expected: PASS (12 tests total).

- [ ] **Step 5: Commit**

```bash
git add src/pensieve/config.py tests/test_config.py
git commit -m "Implement load_config with TOML compat shim and validation"
```

---

## Task 5: Implement `get_wiki_root` with on-disk validation

**Files:**
- Modify: `src/pensieve/config.py`
- Modify: `tests/test_config.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_config.py`:

```python
def test_get_wiki_root_returns_path(fake_home: Path, tmp_path: Path) -> None:
    wiki_root = tmp_path / "mywiki"
    (wiki_root / "wiki").mkdir(parents=True)
    cfg.write_config(wiki_root)
    result = cfg.get_wiki_root()
    assert isinstance(result, Path)
    assert result == wiki_root.resolve()


def test_get_wiki_root_path_does_not_exist_raises(fake_home: Path, tmp_path: Path) -> None:
    fake_home.parent.mkdir(parents=True, exist_ok=True)
    fake_home.write_text(
        f'schema_version = 1\nwiki_root = "{(tmp_path / "ghost").as_posix()}"\n',
        encoding="utf-8",
    )
    with pytest.raises(ConfigError) as exc:
        cfg.get_wiki_root()
    assert "not a valid wiki" in str(exc.value)


def test_get_wiki_root_no_wiki_subdir_raises(fake_home: Path, tmp_path: Path) -> None:
    wiki_root = tmp_path / "no-subdir"
    wiki_root.mkdir()
    cfg.write_config(wiki_root)
    with pytest.raises(ConfigError) as exc:
        cfg.get_wiki_root()
    assert "not a valid wiki" in str(exc.value)


def test_get_wiki_root_path_is_file_raises(fake_home: Path, tmp_path: Path) -> None:
    not_a_dir = tmp_path / "afile.txt"
    not_a_dir.write_text("hi")
    fake_home.parent.mkdir(parents=True, exist_ok=True)
    fake_home.write_text(
        f'schema_version = 1\nwiki_root = "{not_a_dir.as_posix()}"\n',
        encoding="utf-8",
    )
    with pytest.raises(ConfigError) as exc:
        cfg.get_wiki_root()
    assert "not a valid wiki" in str(exc.value)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_config.py -v`
Expected: FAIL with `AttributeError: module 'pensieve.config' has no attribute 'get_wiki_root'`.

- [ ] **Step 3: Implement `get_wiki_root`**

Append to `src/pensieve/config.py`:

```python
def get_wiki_root() -> Path:
    """Return the configured wiki root, validated against disk.

    Raises ConfigError if the config is missing/invalid OR if the configured
    path does not exist, is not a directory, or does not contain a wiki/
    subdirectory.
    """
    data = load_config()
    wiki_root = Path(data["wiki_root"]).resolve()
    if not wiki_root.is_dir() or not (wiki_root / "wiki").is_dir():
        raise ConfigError(
            f"Configured wiki_root is not a valid wiki: {wiki_root}. "
            f"Re-run 'pensieve init' or fix {CONFIG_PATH}."
        )
    return wiki_root
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/test_config.py -v`
Expected: PASS (16 tests total).

- [ ] **Step 5: Commit**

```bash
git add src/pensieve/config.py tests/test_config.py
git commit -m "Implement get_wiki_root with on-disk validation"
```

---

## Task 6: Update `pensieve init` to write config (with overwrite prompt)

**Files:**
- Modify: `src/pensieve/cli.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cli.py`:

```python
import pytest
from pensieve import config as cfg


@pytest.fixture
def fake_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    fake_config = tmp_path / "home" / ".pensieve" / "config.toml"
    monkeypatch.setattr(cfg, "CONFIG_PATH", fake_config)
    return fake_config


def test_cli_init_writes_config(fake_home: Path, tmp_path: Path) -> None:
    target = tmp_path / "mywiki"
    runner = make_runner()
    result = runner.invoke(main, ["init", str(target)])
    assert result.exit_code == 0
    assert fake_home.exists()
    assert target.resolve().as_posix() in fake_home.read_text(encoding="utf-8")
    assert "Registered as active wiki" in result.output


def test_cli_init_prompts_when_existing_config_points_elsewhere(
    fake_home: Path, tmp_path: Path
) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    runner = make_runner()
    runner.invoke(main, ["init", str(first)])
    # Decline overwrite
    result = runner.invoke(main, ["init", str(second)], input="n\n")
    assert "Existing config points to" in result.output
    assert first.resolve().as_posix() in fake_home.read_text(encoding="utf-8")


def test_cli_init_force_overwrites_without_prompt(
    fake_home: Path, tmp_path: Path
) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    runner = make_runner()
    runner.invoke(main, ["init", str(first)])
    result = runner.invoke(main, ["init", "--force", str(second)])
    assert result.exit_code == 0
    assert second.resolve().as_posix() in fake_home.read_text(encoding="utf-8")


def test_cli_init_same_root_does_not_prompt(fake_home: Path, tmp_path: Path) -> None:
    target = tmp_path / "mywiki"
    runner = make_runner()
    runner.invoke(main, ["init", str(target)])
    result = runner.invoke(main, ["init", str(target)])
    assert result.exit_code == 0
    assert "Existing config points to" not in result.output
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_cli.py -v -k init`
Expected: FAIL — `--force` flag does not exist; config not written.

- [ ] **Step 3: Update the `init` command**

In `src/pensieve/cli.py`, replace the `init` function (lines ~63-76) with:

```python
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
        except Exception:
            # If the existing config is unreadable, fall through and overwrite.
            pass

    cfg.write_config(root)
    click.echo(f"✓ Wiki initialised at {root}")
    click.echo(f"  wiki/   → {wiki_dir(root)}")
    click.echo(f"  raw/    → {root / 'raw'}")
    click.echo(f"✓ Registered as active wiki in {cfg.CONFIG_PATH}")
    click.echo("  Next step: copy CLAUDE.md / AGENTS.md from the repo root into your project.")
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/test_cli.py -v -k init`
Expected: PASS (5 init tests including the existing scaffold test).

- [ ] **Step 5: Run the full test suite**

Run: `pytest -v`
Expected: PASS, no regressions.

- [ ] **Step 6: Commit**

```bash
git add src/pensieve/cli.py tests/test_cli.py
git commit -m "pensieve init: write user config with overwrite prompt"
```

---

## Task 7: Add `pensieve root` command

**Files:**
- Modify: `src/pensieve/cli.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cli.py`:

```python
def test_cli_root_prints_configured_path(fake_home: Path, tmp_path: Path) -> None:
    target = tmp_path / "mywiki"
    runner = make_runner()
    runner.invoke(main, ["init", str(target)])
    result = runner.invoke(main, ["root"])
    assert result.exit_code == 0
    assert result.output.strip() == target.resolve().as_posix()


def test_cli_root_no_config_exits_nonzero(fake_home: Path) -> None:
    runner = make_runner()
    result = runner.invoke(main, ["root"])
    assert result.exit_code == 1
    # Click's CliRunner merges stderr into output by default
    assert "not initialised" in result.output


def test_cli_root_invalid_wiki_root_exits_nonzero(
    fake_home: Path, tmp_path: Path
) -> None:
    fake_home.parent.mkdir(parents=True, exist_ok=True)
    fake_home.write_text(
        f'schema_version = 1\nwiki_root = "{(tmp_path / "ghost").as_posix()}"\n',
        encoding="utf-8",
    )
    runner = make_runner()
    result = runner.invoke(main, ["root"])
    assert result.exit_code == 1
    assert "not a valid wiki" in result.output
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_cli.py -v -k "test_cli_root"`
Expected: FAIL with `Error: No such command 'root'`.

- [ ] **Step 3: Implement the `root` command**

Append to `src/pensieve/cli.py` (after the `rebuild_index_cmd` function):

```python
# ---------------------------------------------------------------------------
# root
# ---------------------------------------------------------------------------


@main.command()
def root() -> None:
    """Print the configured wiki root to stdout.

    This is the integration point for external tools (e.g. the slack-scrape
    skill) that need the wiki location independent of cwd. On success the
    absolute path is printed to stdout with no decoration. On any config
    error the message is printed to stderr and the command exits 1.
    """
    from pensieve.config import ConfigError, get_wiki_root

    try:
        wiki_root_path = get_wiki_root()
    except ConfigError as exc:
        click.echo(str(exc), err=True)
        sys.exit(1)
    click.echo(wiki_root_path.as_posix())
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/test_cli.py -v -k "test_cli_root"`
Expected: PASS (3 tests).

- [ ] **Step 5: Smoke-test the command end-to-end**

Run: `pensieve root`
Expected on this dev machine: prints `C:/src/Pensieve` (or whatever you've initialised), exit 0. If no config exists yet, you'll see the "not initialised" message — that's correct.

- [ ] **Step 6: Commit**

```bash
git add src/pensieve/cli.py tests/test_cli.py
git commit -m "Add pensieve root command for skill integration"
```

---

## Task 8: Make `find_wiki_root()` prefer the configured root

**Files:**
- Modify: `src/pensieve/wiki.py`
- Modify: `tests/test_wiki.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_wiki.py`:

```python
import pytest

from pensieve import config as cfg
from pensieve.wiki import find_wiki_root, init_wiki


@pytest.fixture
def fake_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    fake_config = tmp_path / "home" / ".pensieve" / "config.toml"
    monkeypatch.setattr(cfg, "CONFIG_PATH", fake_config)
    return fake_config


def test_find_wiki_root_prefers_configured_root_over_cwd(
    fake_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    configured = tmp_path / "configured-wiki"
    init_wiki(configured)
    cfg.write_config(configured)

    unrelated = tmp_path / "unrelated"
    unrelated.mkdir()
    monkeypatch.chdir(unrelated)

    assert find_wiki_root() == configured.resolve()


def test_find_wiki_root_falls_back_to_cwd_walk_when_no_config(
    fake_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    walked = tmp_path / "walked-wiki"
    init_wiki(walked)
    (walked / "CLAUDE.md").write_text("# schema")

    monkeypatch.chdir(walked)
    assert find_wiki_root() == walked.resolve()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_wiki.py -v -k find_wiki_root`
Expected: FAIL on the first test — without the change, `find_wiki_root()` from an unrelated cwd returns cwd, not the configured root.

- [ ] **Step 3: Update `find_wiki_root()`**

In `src/pensieve/wiki.py`, replace `find_wiki_root` (lines ~31-45) with:

```python
def find_wiki_root(start: Path | None = None) -> Path:
    """Return the wiki root, preferring the configured root when available.

    Resolution order:
      1. ~/.pensieve/config.toml -> wiki_root (if valid).
      2. Walk up from *start* (default: cwd) looking for a directory that
         contains both a wiki/ subdirectory and a CLAUDE.md or AGENTS.md
         schema file.
      3. Fall back to *start* itself so callers can still operate.
    """
    # Local import to avoid a wiki<->config import cycle at module load.
    from pensieve.config import ConfigError, get_wiki_root

    try:
        return get_wiki_root()
    except ConfigError:
        pass

    current = (start or Path.cwd()).resolve()
    for candidate in [current, *current.parents]:
        has_wiki = (candidate / WIKI_DIR_NAME).is_dir()
        has_schema = (candidate / "CLAUDE.md").exists() or (candidate / "AGENTS.md").exists()
        if has_wiki and has_schema:
            return candidate
    return current
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/test_wiki.py -v -k find_wiki_root`
Expected: PASS (2 tests).

- [ ] **Step 5: Run full test suite to confirm no regressions**

Run: `pytest -v`
Expected: ALL PASS. The existing `search`/`lint`/`log-entry`/`rebuild-index` CLI tests use `--root` explicitly, so the change is invisible to them.

- [ ] **Step 6: Commit**

```bash
git add src/pensieve/wiki.py tests/test_wiki.py
git commit -m "find_wiki_root: prefer configured root with cwd-walk fallback"
```

---

## Task 9: Update slack-scrape SKILL.md to resolve `WIKI_ROOT`

**Files:**
- Modify: `~/.claude/skills/slack-scrape/SKILL.md`

> **Note:** this file lives outside the Pensieve repo. It is not committed
> as part of this PR, but the change must ship at the same time the new
> CLI is released. Track it manually until skills move into the repo.

- [ ] **Step 1: Add a "Step 0 — Resolve target wiki root" section**

Insert before the first "Phase 1" section in `~/.claude/skills/slack-scrape/SKILL.md`:

```markdown
## Step 0 — Resolve target wiki root

Before any Phase 1 or Phase 2 work, run:

    pensieve root

via the Bash tool. Capture stdout (trimmed of whitespace) as `WIKI_ROOT`.
This is the absolute path where all scrape output will be written.

If `pensieve root` exits non-zero, abort with the stderr message verbatim.
Do **not** fall back to cwd, do **not** guess, do **not** paraphrase. The
user must run `pensieve init <path>` first.

All paths in the rest of this skill are relative to `WIKI_ROOT`. Wherever
the skill says "Pensieve project root", it now means `WIKI_ROOT`.
```

- [ ] **Step 2: Replace Phase 1 Step 5 path**

Find the line (around line 185):

```
raw/slack/scrape-<start-date>_<end-date>/index.json
```

Change the surrounding sentence to:

```
<WIKI_ROOT>/raw/slack/scrape-<start-date>_<end-date>/index.json
```

And remove the "Use the Pensieve project root as the base path." sentence
on the next line — `WIKI_ROOT` is now the explicit base path.

- [ ] **Step 3: Update Phase 1 Step 6 summary**

Find the summary block (around line 192-203). Update the `Index file` line
and the run-hint to print absolute paths:

```
  Index file : <WIKI_ROOT>/raw/slack/scrape-<start>_<end>/index.json

Run `/slack-scrape --fetch <WIKI_ROOT>/raw/slack/scrape-<start>_<end>/index.json` to fetch full messages.
```

- [ ] **Step 4: Update Phase 2 Step 3 path**

Find the line (around line 272):

```
raw/slack/scrape-<start>_<end>/<YYYY-MM-DD>/<channel-slug>--<channel-id>.md
```

Change to:

```
<WIKI_ROOT>/raw/slack/scrape-<start>_<end>/<YYYY-MM-DD>/<channel-slug>--<channel-id>.md
```

- [ ] **Step 5: Update Phase 2 `--fetch` argument handling**

Find Phase 2 Step 1 ("Read and Validate Index", around line 225-227). Replace
the path-handling description with:

```markdown
### Step 1 — Read and Validate Index

Read the `index.json` file at the path provided via `--fetch`. Path resolution:

- **Absolute path** — used as-is.
- **Relative path** — resolved against `WIKI_ROOT` (NOT cwd). This preserves
  the copy-paste UX of the Phase 1 summary.

After resolution, verify the file exists and abort with a clear error if it
does not. Validate that it contains the expected top-level keys: `user_id`,
`user_tz`, `date_range`, `channels`, `status`. Abort with a clear error if
the file is missing or malformed.
```

- [ ] **Step 6: Update Phase 2 Step 4 final summary**

Find the final summary block (around line 296). Update the `Output` line:

```
  Output: <WIKI_ROOT>/raw/slack/scrape-<start>_<end>/
```

- [ ] **Step 7: Smoke-test the skill end-to-end**

From a directory **outside** `C:\src\Pensieve` (e.g. `C:\Users\pratyush.pande`):

1. Run `pensieve root` and confirm it prints the expected path.
2. Invoke `/slack-scrape` for a small date range.
3. Confirm `index.json` is created under `<WIKI_ROOT>/raw/slack/...`, not under cwd.
4. Run `/slack-scrape --fetch <relative-path-from-summary>` and confirm it
   resolves correctly.
5. Confirm the channel-day markdown files land under `<WIKI_ROOT>/raw/slack/...`.

If any of these fail, revisit the skill edits — do **not** patch around it
in code.

- [ ] **Step 8: Note the skill update in the PR description**

The skill change is not part of this commit. Add a note to the PR
description: "Skill update applied manually to `~/.claude/skills/slack-scrape/SKILL.md`. Smoke-tested from outside the Pensieve directory."

---

## Self-Review

**Spec coverage check:**
- Architecture (config as contract, skill shells out) → Tasks 2–8.
- Config location `~/.pensieve/config.toml` → Task 2.
- Schema (`schema_version`, `wiki_root`) → Tasks 2, 3.
- TOML compat for Python 3.9+ → Task 1, Task 4 shim.
- Reading rules (5 error cases) → Task 4 (4 cases) + Task 5 (on-disk validation).
- Writing rules (atomic via `os.replace`, parent dir created) → Task 3.
- `pensieve init` config write + overwrite prompt + `--force` → Task 6.
- `pensieve root` command → Task 7.
- `find_wiki_root()` prefers config with cwd-walk fallback → Task 8.
- Skill: Step 0, path replacements, `--fetch` resolution → Task 9.
- Error handling (CLI catches `ConfigError` → stderr → exit 1) → Task 7 (`root`); Task 6 init falls through on unreadable existing config.
- Test isolation (monkeypatch `CONFIG_PATH`) → Tasks 2–8 all use `fake_home` fixture.

All spec sections covered.

**Placeholder scan:** none. Every step has concrete code or commands.

**Type consistency:** `ConfigError`, `SCHEMA_VERSION`, `CONFIG_PATH`, `write_config(wiki_root: Path)`, `load_config() -> dict`, `get_wiki_root() -> Path` are consistent across all tasks. The CLI imports them from `pensieve.config` and uses them with the same signatures defined in Tasks 2–5.

**One known fragility, called out for the implementer:** Task 6 imports `from pensieve import config as cfg` *inside* the `init` function rather than at module top, mirroring Task 8's local import in `wiki.py`. This is intentional — it avoids forcing every CLI startup to read the config and avoids any future import-cycle risk between `cli`, `wiki`, and `config`.
