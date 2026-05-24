# Rich Status Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the single-line carriage-return status updater with a Rich `Live` panel dashboard that shows database, current activity, discovery progress, and running counts in colour.

**Architecture:** A new `StatusDashboard` class wraps `rich.live.Live` + `rich.panel.Panel`. State is held in fields on the dashboard (database name, "now" line, "schema" line, counts) and any setter call re-renders the panel. The dashboard is a context manager: `__enter__` starts `Live`, `__exit__` stops it. When stderr isn't a TTY, or `NO_COLOR`/`DCMEXPORTER_NO_STATUS=1` is set, the dashboard never starts and every method becomes a silent no-op (preserving today's "stay silent in CI/logs" behaviour). The orchestrator switches from `status.update(str)` calls to structured setters: `set_now`, `set_schema`, `set_counts`. Plugins keep their existing `progress` callback contract — orchestrator just passes `status.set_schema` as the callback.

**Tech Stack:** Python 3.10+, [`rich`](https://rich.readthedocs.io/) (`>=13.7`), pytest. No new architecture beyond replacing one file's contents.

---

## File Structure

| Path | Purpose | Action |
|------|---------|--------|
| `pyproject.toml` | Add `rich>=13.7` runtime dep | Modify |
| `src/dcmexporter/status.py` | `StatusDashboard` class — Rich-backed live panel | Replace contents |
| `src/dcmexporter/orchestrator.py` | Drive dashboard with structured updates instead of free-form strings | Modify |
| `tests/test_status.py` | Tests for dashboard: silent paths, render content, env vars | Replace contents |

No changes needed to plugins — `_base.py` already passes a `progress` callback up; the orchestrator just hands it `status.set_schema` instead of `status.update`.

### Panel layout (the rendered shape)

```
╭─ dcmexporter ───────────────────────────────╮
│ database:  MYDB                             │
│ now:       Table  MYDB.PUBLIC.ORDERS  12/847│
│ schema:    discovering Views in MYDB.PUBLIC │
├─────────────────────────────────────────────┤
│ exported=531  errors=0  skipped=2           │
╰─────────────────────────────────────────────╯
```

Colour scheme:
- `database:` label → `dim`
- `now:` value → `cyan`
- `schema:` value → `magenta`
- `exported=N` → `green`
- `errors=N` → `red` when N > 0, else `dim`
- `skipped=N` → `yellow` when N > 0, else `dim`

---

## Task 1: Add rich dependency

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add `rich>=13.7` to project dependencies**

Edit the `dependencies` list in `pyproject.toml`:

```toml
dependencies = [
    "click>=8.1",
    "snowflake-connector-python>=3.7",
    "pyyaml>=6.0",
    "sqlglot>=25.0",
    "jinja2>=3.1",
    "rich>=13.7",
]
```

- [ ] **Step 2: Sync the lockfile**

Run: `uv sync`
Expected: completes without error; rich is installed.

- [ ] **Step 3: Verify rich import works**

Run: `uv run python -c "from rich.live import Live; from rich.panel import Panel; from rich.console import Console; print('ok')"`
Expected: prints `ok`.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "deps: add rich for status dashboard"
```

---

## Task 2: Write failing tests for StatusDashboard contract

We're replacing the entire test file because the dashboard's API changes (`update`/`clear` → `set_now`/`set_schema`/`set_counts` + context manager). Write the tests against the new shape now so the implementation has a clear target.

**Files:**
- Modify: `tests/test_status.py`

- [ ] **Step 1: Replace the test file with the new contract**

Overwrite `tests/test_status.py` with:

```python
"""Tests for the StatusDashboard helper."""

from __future__ import annotations

import io

from dcmexporter.status import StatusDashboard


class _TtyStream(io.StringIO):
    def isatty(self) -> bool:  # type: ignore[override]
        return True


def test_silent_when_not_tty(monkeypatch) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("DCMEXPORTER_NO_STATUS", raising=False)
    stream = io.StringIO()
    with StatusDashboard(stream=stream) as dash:
        dash.set_database("MYDB")
        dash.set_now("connecting...")
        dash.set_schema("discovering Tables in MYDB.PUBLIC")
        dash.set_counts(exported=1, errors=0, skipped=0)
    assert stream.getvalue() == ""


def test_disabled_by_no_status_env(monkeypatch) -> None:
    monkeypatch.setenv("DCMEXPORTER_NO_STATUS", "1")
    stream = _TtyStream()
    with StatusDashboard(stream=stream) as dash:
        dash.set_database("MYDB")
        dash.set_now("nope")
    assert stream.getvalue() == ""


def test_disabled_by_no_color_env(monkeypatch) -> None:
    """NO_COLOR is the standard opt-out for ANSI; the dashboard depends on
    colour to be readable, so we treat NO_COLOR as 'no dashboard' rather than
    rendering a degraded plain panel."""
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.delenv("DCMEXPORTER_NO_STATUS", raising=False)
    stream = _TtyStream()
    with StatusDashboard(stream=stream) as dash:
        dash.set_database("MYDB")
        dash.set_now("nope")
    assert stream.getvalue() == ""


def test_renders_panel_content_when_tty(monkeypatch) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("DCMEXPORTER_NO_STATUS", raising=False)
    stream = _TtyStream()
    with StatusDashboard(stream=stream) as dash:
        dash.set_database("MYDB")
        dash.set_now("Table MYDB.PUBLIC.ORDERS 12/847")
        dash.set_schema("discovering Views in MYDB.PUBLIC")
        dash.set_counts(exported=531, errors=0, skipped=2)
    out = stream.getvalue()
    assert "MYDB" in out
    assert "ORDERS" in out
    assert "discovering Views" in out
    assert "exported=531" in out
    assert "errors=0" in out
    assert "skipped=2" in out


def test_log_writes_above_panel(monkeypatch) -> None:
    """Errors and warnings need to scroll above the live panel rather than
    overwrite it. Verify .log() output appears in the stream."""
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("DCMEXPORTER_NO_STATUS", raising=False)
    stream = _TtyStream()
    with StatusDashboard(stream=stream) as dash:
        dash.set_database("MYDB")
        dash.log("[dcmexporter] discover failed for Tag: <reason>")
    assert "discover failed for Tag" in stream.getvalue()


def test_setters_safe_before_enter() -> None:
    """Calling setters on an unentered dashboard must not raise. Useful so
    callers can construct the dashboard and update fields conditionally."""
    dash = StatusDashboard(stream=io.StringIO())
    dash.set_database("MYDB")
    dash.set_now("hello")
    dash.set_schema("schema")
    dash.set_counts(exported=0, errors=0, skipped=0)
    dash.log("a message")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_status.py -v`
Expected: All 6 tests FAIL with `ImportError`/`AttributeError` because `StatusDashboard` doesn't exist yet.

- [ ] **Step 3: Commit**

```bash
git add tests/test_status.py
git commit -m "test: rewrite status tests against StatusDashboard contract"
```

---

## Task 3: Implement StatusDashboard

**Files:**
- Modify: `src/dcmexporter/status.py` (full rewrite)

- [ ] **Step 1: Replace the file contents**

Overwrite `src/dcmexporter/status.py` with:

```python
"""Rich-backed live status dashboard for long export runs.

Long export runs (80K+ tables) emit very little until they finish, which makes
the CLI feel hung. This module renders a self-refreshing panel via
``rich.live.Live`` when stderr is a TTY and stays silent otherwise so logs/CI
output don't fill with control characters. Errors and the final summary still
print as normal lines (use ``.log()`` to write above the panel).
"""

from __future__ import annotations

import os
from types import TracebackType
from typing import IO

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text


class StatusDashboard:
    """Live panel dashboard. Use as a context manager.

    All setters are safe to call before ``__enter__`` and after ``__exit__``;
    they update the held state and either re-render the live panel or do
    nothing if the dashboard is disabled or not currently running.
    """

    def __init__(self, stream: IO[str] | None = None) -> None:
        self._stream: IO[str] | None = stream
        self._enabled = self._is_tty(stream) and not _disabled_by_env()
        self._database = ""
        self._now = ""
        self._schema = ""
        self._exported = 0
        self._errors = 0
        self._skipped = 0
        self._console: Console | None = None
        self._live: Live | None = None

    # --- context manager ---------------------------------------------------

    def __enter__(self) -> "StatusDashboard":
        if not self._enabled:
            return self
        self._console = Console(
            file=self._stream,
            force_terminal=True,
            highlight=False,
        )
        self._live = Live(
            self._render(),
            console=self._console,
            refresh_per_second=8,
            transient=True,
        )
        self._live.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._live is not None:
            self._live.stop()
            self._live = None
        self._console = None

    # --- state setters -----------------------------------------------------

    def set_database(self, database: str) -> None:
        self._database = database
        self._refresh()

    def set_now(self, message: str) -> None:
        self._now = message
        self._refresh()

    def set_schema(self, message: str) -> None:
        self._schema = message
        self._refresh()

    def set_counts(self, *, exported: int, errors: int, skipped: int) -> None:
        self._exported = exported
        self._errors = errors
        self._skipped = skipped
        self._refresh()

    def log(self, message: str) -> None:
        """Write a one-shot line that scrolls above the live panel.

        Use for warnings/errors that would otherwise be overwritten by the
        next refresh. No-op when the dashboard is disabled.
        """
        if self._console is None:
            return
        self._console.log(message)

    # --- internals ---------------------------------------------------------

    def _refresh(self) -> None:
        if self._live is None:
            return
        self._live.update(self._render())

    def _render(self) -> Panel:
        body = Table.grid(padding=(0, 2))
        body.add_column(style="dim", no_wrap=True)
        body.add_column(overflow="ellipsis")
        body.add_row("database:", Text(self._database))
        body.add_row("now:", Text(self._now, style="cyan"))
        body.add_row("schema:", Text(self._schema, style="magenta"))

        counts = Text()
        counts.append(f"exported={self._exported}", style="green")
        counts.append("  ")
        errors_style = "red" if self._errors else "dim"
        counts.append(f"errors={self._errors}", style=errors_style)
        counts.append("  ")
        skipped_style = "yellow" if self._skipped else "dim"
        counts.append(f"skipped={self._skipped}", style=skipped_style)

        return Panel(
            Group(body, Text(""), counts),
            title="dcmexporter",
            title_align="left",
            border_style="dim",
        )

    @staticmethod
    def _is_tty(stream: IO[str] | None) -> bool:
        if stream is None:
            return False
        isatty = getattr(stream, "isatty", None)
        return bool(isatty and isatty())


def _disabled_by_env() -> bool:
    if os.environ.get("NO_COLOR"):
        return True
    return os.environ.get("DCMEXPORTER_NO_STATUS") == "1"
```

- [ ] **Step 2: Run the new tests**

Run: `uv run pytest tests/test_status.py -v`
Expected: All 6 tests PASS.

- [ ] **Step 3: Run the full suite to catch downstream breakage**

Run: `uv run pytest -v`
Expected: most tests pass; `test_orchestrator.py` (or similar) MAY fail because the orchestrator still calls `status.update`/`status.clear` which no longer exist. That's expected and Task 4 fixes it. If everything passes, even better — proceed to Task 4 anyway because the orchestrator still needs to be wired to the new structured API.

- [ ] **Step 4: Commit**

```bash
git add src/dcmexporter/status.py
git commit -m "feat: replace StatusLine with Rich-backed StatusDashboard"
```

---

## Task 4: Wire orchestrator to the new dashboard

**Files:**
- Modify: `src/dcmexporter/orchestrator.py`

The current orchestrator calls `status.update(str)` and `status.clear()`. We replace those with structured setters and use `with`-statement scoping. Counts are pushed to the dashboard whenever they change so the panel always reflects current state.

- [ ] **Step 1: Replace the export() function**

Open `src/dcmexporter/orchestrator.py`. Replace the existing `export()` function (lines 19–156) with:

```python
def export(cfg: Config) -> int:
    registry = build_registry()
    account_identifier = ""
    conn: Any | None = None
    log: RunLog | None = None

    try:
        # Prepare the output folder before opening the log so the log file
        # itself isn't blown away by --force later.
        try:
            prepare_out_folder(cfg.out_folder, force=cfg.force)
        except OutFolderError as exc:
            print(f"[dcmexporter] {exc}", file=sys.stderr)
            return 5

        log = RunLog(cfg.out_folder / "dcmexporter.log")
        log.info(f"export starting database={cfg.database} out_folder={cfg.out_folder}")

        with StatusDashboard() as status:
            status.set_database(cfg.database)
            status.set_now("connecting to Snowflake...")
            conn = open_connection(cfg.connection)
            account_identifier = resolve_account_identifier(conn)
            cursor = conn.cursor()
            log.info(f"connected to Snowflake account={account_identifier}")

            type_names = filter_types(cfg)
            definitions: dict[str, str] = {}
            macros: dict[str, str] | None = {} if cfg.use_macros else None

            exported = 0
            errors = 0
            skipped_missing = 0
            for type_name in type_names:
                if type_name not in V1_TYPES:
                    if not cfg.includes:
                        log.warn(f"skipping unsupported type: {type_name}")
                        status.log(
                            f"[dcmexporter] skipping unsupported type: {type_name}"
                        )
                    continue
                plugin = registry.get(type_name)

                try:
                    status.set_schema(f"discovering {type_name}s...")
                    log.info(f"discovering {type_name}s")
                    fqns = plugin.discover(
                        cursor,
                        cfg.database,
                        cfg.schemas or None,
                        progress=status.set_schema,
                    )
                    log.info(f"discovered {len(fqns)} {type_name}(s)")
                    for schema, count in _counts_by_schema(fqns):
                        log.info(f"  {schema}: {count} {type_name}(s)")
                except Exception as exc:  # noqa: BLE001
                    log.error(f"discover failed for {type_name}: {exc}")
                    status.log(
                        f"[dcmexporter] discover failed for {type_name}: {exc}"
                    )
                    errors += 1
                    status.set_counts(
                        exported=exported, errors=errors, skipped=skipped_missing
                    )
                    continue

                blocks: list[str] = []
                total = len(fqns)
                for index, fqn in enumerate(fqns, start=1):
                    progress = f"{index}/{total} " if total > 1 else ""
                    status.set_now(f"{type_name} {progress}{fqn}")
                    try:
                        ddl = plugin.get_ddl(cursor, fqn)
                        block = plugin.to_define_and_invocation(
                            ddl,
                            comment=cfg.comment,
                            use_macros=cfg.use_macros,
                            database=cfg.database,
                        )
                    except Exception as exc:  # noqa: BLE001
                        log.error(f"{type_name} {fqn}: {exc}")
                        if _is_missing_or_unauthorized(exc):
                            skipped_missing += 1
                        else:
                            errors += 1
                        status.set_counts(
                            exported=exported,
                            errors=errors,
                            skipped=skipped_missing,
                        )
                        continue
                    blocks.append(block)
                    exported += 1
                    status.set_counts(
                        exported=exported,
                        errors=errors,
                        skipped=skipped_missing,
                    )

                definitions[plugin.file_slug] = "\n".join(blocks)
                if macros is not None:
                    macros[plugin.file_slug] = plugin.macro_definition()

            status.set_now("writing output files...")
            status.set_schema("")
            log.info("writing output files")
            manifest = render_manifest(cfg, account_identifier=account_identifier)
            makefile = render_makefile(cfg)
            write_outputs(
                out_folder=cfg.out_folder,
                manifest=manifest,
                makefile=makefile,
                definitions=definitions,
                macros=macros,
            )

        if cfg.templating_configuration_keys and cfg.configurations:
            keys = ", ".join(cfg.templating_configuration_keys)
            print(
                f"[dcmexporter] reminder: fill values for keys [{keys}] "
                "under each configuration in manifest.yml",
                file=sys.stderr,
            )

        log.info(
            f"export finished exported={exported} errors={errors} "
            f"skipped_missing={skipped_missing}"
        )
        summary = f"[dcmexporter] exported={exported} errors={errors}"
        if skipped_missing:
            summary += f" skipped_missing={skipped_missing}"
        summary += f" log={log.path}"
        print(summary, file=sys.stderr)

        if exported == 0 and errors > 0:
            return 4
        return 0
    finally:
        if log is not None:
            log.close()
        if conn is not None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass
```

- [ ] **Step 2: Update the import line**

In `src/dcmexporter/orchestrator.py`, change:

```python
from dcmexporter.status import StatusLine
```

to:

```python
from dcmexporter.status import StatusDashboard
```

- [ ] **Step 3: Run the full test suite**

Run: `uv run pytest -v`
Expected: All tests PASS. Counts in `test_orchestrator*` (if any) remain unchanged because the summary line and exit codes weren't touched.

- [ ] **Step 4: Smoke-test against a small live database**

Run: `uv run dcmexporter export --database GLOBAL_OPS --force`
Expected:
- A panel appears in the terminal showing `database: GLOBAL_OPS`, current type/object, schema progress, and growing `exported=N` count
- After completion, the panel disappears (transient mode) and the existing `[dcmexporter] exported=… errors=…` summary line prints
- `out/dcmexporter.log` contains the same per-schema breakdown as before

If the user can't run live, skip to Step 5.

- [ ] **Step 5: Smoke-test the silent path**

Run: `uv run dcmexporter export --database GLOBAL_OPS --force 2>/tmp/dcm-stderr-pipe.log` (stderr piped — not a TTY)
Expected: `/tmp/dcm-stderr-pipe.log` contains only the summary line and any warnings/errors — no escape sequences or panel.

- [ ] **Step 6: Run linters**

Run: `uv run ruff check && uv run ruff format --check && uv run mypy src tests`
Expected: All green. If mypy complains about `rich`, add a stub-ignore override in `pyproject.toml`:

```toml
[[tool.mypy.overrides]]
module = ["rich.*"]
ignore_missing_imports = true
```

(Only add the override if mypy actually fails on rich.)

- [ ] **Step 7: Commit**

```bash
git add src/dcmexporter/orchestrator.py pyproject.toml
git commit -m "feat: wire orchestrator to StatusDashboard structured API"
```

---

## Task 5: Update PR body

**Files:**
- None (GitHub only)

- [ ] **Step 1: Append the new feature to PR #2's body**

Run:

```bash
gh pr view 2 --json body --jq .body > /tmp/pr-body.md
```

Edit `/tmp/pr-body.md` and add a bullet under `## Summary`:

```
- Replace single-line `\r` status updater with a Rich `Live` panel dashboard (database, current activity, discovery progress, running counts; coloured; transient so it disappears when the run ends). Stays silent on non-TTY, NO_COLOR, or DCMEXPORTER_NO_STATUS=1.
```

Then run:

```bash
gh pr edit 2 --body-file /tmp/pr-body.md
```

Expected: PR body updated; `gh pr view 2` shows the new bullet.

- [ ] **Step 2: Push**

```bash
git push
```

Expected: branch updated, CI re-runs.

---

## Self-Review Notes

**Spec coverage:**
- Live panel dashboard layout with header (database / now / schema) and footer (counts) → Task 3 `_render`
- Colour-coded status (green ok, yellow skipped, red errors, plus cyan now / magenta schema / dim labels) → Task 3 `_render`
- Stay silent for non-TTY → Task 3 `_is_tty` + Task 2 test `test_silent_when_not_tty`
- Preserve `NO_COLOR` and `DCMEXPORTER_NO_STATUS=1` env opt-outs → Task 3 `_disabled_by_env` + Task 2 tests for both
- Errors/warnings still readable → Task 3 `.log()` writes above the live panel; Task 4 routes existing print-to-stderr calls through it
- Plan-first then implement → this document

**No placeholders:** every code block above is the file content or full function body required.

**Type consistency:** `set_counts` keyword args (`exported`, `errors`, `skipped`) match between Task 2 tests, Task 3 implementation, and Task 4 orchestrator calls. `set_now`/`set_schema` are single-string setters in all tasks. `progress=status.set_schema` (Task 4) matches the `progress(prefix)` callable contract used by `_base.py:discover` (read at plan time, line 60–67).
