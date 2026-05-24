# Chunk Definition Files Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When a per-type DDL output exceeds N objects (default 100, override via `DCMASSIST_EXPORT_OBJECTS_PER_FILE`), spill into numbered files (`table.sql`, `table2.sql`, `table3.sql`, …); log a line for every file written and, when chunking actually happens, mention the env var.

**Architecture:** The orchestrator already accumulates per-type DDL blocks into a list. Today it joins the whole list and stuffs it into a `dict[str, str]` keyed by `file_slug` for `write_outputs` to write. We change two things:

1. The orchestrator now pre-chunks blocks into a `list[tuple[str, list[str]]]` of `(filename, blocks)` per type, naming the first chunk `<slug>.sql` and subsequent chunks `<slug>2.sql`, `<slug>3.sql`, …
2. `write_outputs` accepts a flat `dict[filename → body]` instead of `dict[slug → body]` (the orchestrator does the naming). Each chunk gets one log line ("N tables written to table2.sql"). When chunking actually triggered for a type (more than one chunk), we log the env-var hint.

Macros are unaffected — there's exactly one macro file per type slug.

**Tech Stack:** Python 3.10+, pytest. No new deps.

---

## File Structure

| Path | Purpose | Action |
|------|---------|--------|
| `src/dcmexporter/chunking.py` | Pure helper: chunk size resolution from env, splitting a block list into `[(filename, blocks), ...]` | Create |
| `tests/test_chunking.py` | Tests for chunking helper | Create |
| `src/dcmexporter/render.py` | Switch `write_outputs` `definitions` arg from `dict[slug,body]` to `dict[filename,body]`. Macros unchanged. | Modify |
| `tests/test_render.py` | Update tests to the new `definitions={"table.sql": ...}` shape | Modify |
| `src/dcmexporter/orchestrator.py` | Use chunking helper; log per-file written counts; log env-var hint when a type was chunked | Modify |
| `tests/test_orchestrator.py` | Update assertions to reference `definitions` paths and add chunking-specific test | Modify |

### Why a separate `chunking.py`?

Chunking is pure logic with two well-bounded inputs (block list, chunk size) and a deterministic output (filename → blocks). Extracting it keeps `orchestrator.py` from growing further and makes the logic unit-testable without orchestrator scaffolding.

### Filename convention

Per the spec: first file unchanged (`table.sql`), then `table2.sql`, `table3.sql`, …. **Not** `table1.sql` for the first one — keeping the existing filename means single-type-small-database exports look identical to before.

### Env-var hint behaviour

The hint is logged at INFO level **once per type that was chunked into multiple files**, not once per file. If `Table` chunks into 5 files, exactly one hint line for tables. Format:

```
INFO file size is configurable via DCMASSIST_EXPORT_OBJECTS_PER_FILE (currently 100)
```

The hint repeats per-type (rather than once at the start of the run) so users tailing the log see it next to whichever type triggered chunking.

---

## Task 1: Create chunking helper with tests

**Files:**
- Create: `src/dcmexporter/chunking.py`
- Create: `tests/test_chunking.py`

- [ ] **Step 1: Write the failing tests**

Write `tests/test_chunking.py`:

```python
"""Tests for the per-type DDL chunking helper."""

from __future__ import annotations

import pytest

from dcmexporter.chunking import (
    DEFAULT_OBJECTS_PER_FILE,
    OBJECTS_PER_FILE_ENV,
    chunk_blocks,
    resolve_objects_per_file,
)


def test_default_constant_is_100() -> None:
    assert DEFAULT_OBJECTS_PER_FILE == 100


def test_env_var_name_is_dcmassist() -> None:
    assert OBJECTS_PER_FILE_ENV == "DCMASSIST_EXPORT_OBJECTS_PER_FILE"


def test_resolve_default_when_unset(monkeypatch) -> None:
    monkeypatch.delenv(OBJECTS_PER_FILE_ENV, raising=False)
    assert resolve_objects_per_file() == 100


def test_resolve_reads_env(monkeypatch) -> None:
    monkeypatch.setenv(OBJECTS_PER_FILE_ENV, "50")
    assert resolve_objects_per_file() == 50


def test_resolve_rejects_non_integer(monkeypatch) -> None:
    monkeypatch.setenv(OBJECTS_PER_FILE_ENV, "abc")
    with pytest.raises(ValueError, match=OBJECTS_PER_FILE_ENV):
        resolve_objects_per_file()


def test_resolve_rejects_zero(monkeypatch) -> None:
    """Zero would be a divide-by-zero / infinite-files trap. Reject explicitly."""
    monkeypatch.setenv(OBJECTS_PER_FILE_ENV, "0")
    with pytest.raises(ValueError, match=OBJECTS_PER_FILE_ENV):
        resolve_objects_per_file()


def test_resolve_rejects_negative(monkeypatch) -> None:
    monkeypatch.setenv(OBJECTS_PER_FILE_ENV, "-5")
    with pytest.raises(ValueError, match=OBJECTS_PER_FILE_ENV):
        resolve_objects_per_file()


def test_chunk_empty_returns_empty() -> None:
    assert chunk_blocks([], slug="table", size=100) == []


def test_chunk_single_file_when_under_limit() -> None:
    blocks = ["a", "b", "c"]
    result = chunk_blocks(blocks, slug="table", size=100)
    assert result == [("table.sql", ["a", "b", "c"])]


def test_chunk_single_file_when_exactly_at_limit() -> None:
    blocks = ["a", "b", "c"]
    result = chunk_blocks(blocks, slug="table", size=3)
    assert result == [("table.sql", ["a", "b", "c"])]


def test_chunk_two_files_when_one_over() -> None:
    blocks = ["a", "b", "c", "d"]
    result = chunk_blocks(blocks, slug="table", size=3)
    assert result == [
        ("table.sql", ["a", "b", "c"]),
        ("table2.sql", ["d"]),
    ]


def test_chunk_many_files_uses_2_3_4_naming() -> None:
    blocks = [str(i) for i in range(7)]
    result = chunk_blocks(blocks, slug="view", size=2)
    assert result == [
        ("view.sql", ["0", "1"]),
        ("view2.sql", ["2", "3"]),
        ("view3.sql", ["4", "5"]),
        ("view4.sql", ["6"]),
    ]


def test_chunk_uses_provided_slug() -> None:
    blocks = ["x"]
    result = chunk_blocks(blocks, slug="file_format", size=100)
    assert result == [("file_format.sql", ["x"])]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_chunking.py -v`
Expected: All tests FAIL with `ModuleNotFoundError: No module named 'dcmexporter.chunking'`.

- [ ] **Step 3: Implement the helper**

Write `src/dcmexporter/chunking.py`:

```python
"""Pure helpers for splitting per-type DDL output into numbered files.

Large databases (e.g. EXPERIMENTATION) can produce a single ``table.sql`` over
40 MB, which is awkward to review and to diff. We split the per-type DDL into
chunks of ``DCMASSIST_EXPORT_OBJECTS_PER_FILE`` objects each (default 100),
naming files ``<slug>.sql``, ``<slug>2.sql``, ``<slug>3.sql``, … so a small
export still produces just ``table.sql`` (no behaviour change for users below
the threshold).
"""

from __future__ import annotations

import os

DEFAULT_OBJECTS_PER_FILE = 100
OBJECTS_PER_FILE_ENV = "DCMASSIST_EXPORT_OBJECTS_PER_FILE"


def resolve_objects_per_file() -> int:
    """Return the configured chunk size, or the default if the env var isn't set.

    Raises ValueError on a malformed/non-positive value rather than silently
    falling back to the default — a typo in the env var should be loud.
    """
    raw = os.environ.get(OBJECTS_PER_FILE_ENV)
    if raw is None:
        return DEFAULT_OBJECTS_PER_FILE
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(
            f"{OBJECTS_PER_FILE_ENV}={raw!r} is not a positive integer"
        ) from exc
    if value <= 0:
        raise ValueError(
            f"{OBJECTS_PER_FILE_ENV}={raw!r} is not a positive integer"
        )
    return value


def chunk_blocks(
    blocks: list[str], *, slug: str, size: int
) -> list[tuple[str, list[str]]]:
    """Split a list of DDL blocks into [(filename, blocks)] chunks.

    The first chunk keeps the original ``<slug>.sql`` name; subsequent chunks
    are ``<slug>2.sql``, ``<slug>3.sql``, … (no ``<slug>1.sql``). An empty
    input yields an empty list — the caller decides whether to skip an empty
    type entirely.
    """
    if not blocks:
        return []
    out: list[tuple[str, list[str]]] = []
    for index, start in enumerate(range(0, len(blocks), size), start=1):
        chunk = blocks[start : start + size]
        suffix = "" if index == 1 else str(index)
        out.append((f"{slug}{suffix}.sql", chunk))
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_chunking.py -v`
Expected: All 13 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dcmexporter/chunking.py tests/test_chunking.py
git commit -m "feat: add chunking helper for per-type DDL output"
```

---

## Task 2: Update render.write_outputs to accept filename-keyed definitions

The renderer no longer knows the slug — the caller (orchestrator) does the chunking and hands over fully-named files. This keeps `write_outputs` mechanical: write each (filename, body) pair, no naming logic.

**Files:**
- Modify: `src/dcmexporter/render.py`
- Modify: `tests/test_render.py`

- [ ] **Step 1: Update test expectations**

Replace `tests/test_render.py` with:

```python
"""Tests for the output-folder writer."""

from __future__ import annotations

from pathlib import Path

import pytest

from dcmexporter.render import OutFolderError, prepare_out_folder, write_outputs


def test_write_outputs_creates_layout(tmp_path: Path) -> None:
    out = tmp_path / "out"
    write_outputs(
        out_folder=out,
        manifest="manifest_version: 2\n",
        makefile=".PHONY: plan\n",
        definitions={"table.sql": "DEFINE TABLE foo;\n"},
        macros={"table": "{% macro define_table() %}{% endmacro %}\n"},
    )
    assert (out / "manifest.yml").read_text() == "manifest_version: 2\n"
    assert (out / "Makefile").read_text() == ".PHONY: plan\n"
    assert (
        out / "sources" / "definitions" / "table.sql"
    ).read_text() == "DEFINE TABLE foo;\n"
    assert (out / "sources" / "macros" / "table.sql").exists()


def test_write_outputs_writes_chunked_definitions(tmp_path: Path) -> None:
    out = tmp_path / "out"
    write_outputs(
        out_folder=out,
        manifest="m",
        makefile="M",
        definitions={
            "table.sql": "block 1",
            "table2.sql": "block 2",
            "table3.sql": "block 3",
        },
        macros=None,
    )
    defs = out / "sources" / "definitions"
    assert (defs / "table.sql").read_text() == "block 1"
    assert (defs / "table2.sql").read_text() == "block 2"
    assert (defs / "table3.sql").read_text() == "block 3"


def test_write_outputs_skips_macros_when_none(tmp_path: Path) -> None:
    out = tmp_path / "out"
    write_outputs(
        out_folder=out,
        manifest="m",
        makefile="M",
        definitions={"table.sql": "x"},
        macros=None,
    )
    assert not (out / "sources" / "macros").exists()


def test_prepare_out_folder_refuses_existing_nonempty(tmp_path: Path) -> None:
    out = tmp_path / "out"
    out.mkdir()
    (out / "stale.txt").write_text("hello")
    with pytest.raises(OutFolderError):
        prepare_out_folder(out, force=False)


def test_prepare_out_folder_force_clears_existing(tmp_path: Path) -> None:
    out = tmp_path / "out"
    out.mkdir()
    (out / "stale.txt").write_text("hello")
    prepare_out_folder(out, force=True)
    assert out.exists()
    assert not (out / "stale.txt").exists()


def test_write_outputs_skips_empty_definition_files(tmp_path: Path) -> None:
    out = tmp_path / "out"
    write_outputs(
        out_folder=out,
        manifest="m",
        makefile="M",
        definitions={"table.sql": "x", "view.sql": ""},
        macros=None,
    )
    assert (out / "sources" / "definitions" / "table.sql").exists()
    assert not (out / "sources" / "definitions" / "view.sql").exists()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_render.py -v`
Expected: tests using `"table.sql"` keys fail because the current code does `f"{slug}.sql"` and would write `table.sql.sql` (or possibly succeed but write to the wrong path — verify by reading the failure carefully).

- [ ] **Step 3: Update `write_outputs`**

Replace the body of `src/dcmexporter/render.py` with:

```python
"""Write generated artefacts into the output folder."""

from __future__ import annotations

import shutil
from pathlib import Path


class OutFolderError(RuntimeError):
    """Raised when --out-folder is unsafe to write to."""


def _is_nonempty_dir(path: Path) -> bool:
    return path.exists() and path.is_dir() and any(path.iterdir())


def prepare_out_folder(out_folder: Path, *, force: bool) -> None:
    """Make `out_folder` ready for writing.

    Refuses if non-empty and `force=False`. With `force=True`, clears existing
    contents. Always ensures the folder exists at the end. Called up-front so
    the orchestrator can open the log file inside it before doing any work.
    """
    if _is_nonempty_dir(out_folder) and not force:
        raise OutFolderError(
            f"Output folder {out_folder} exists and is non-empty; pass --force to overwrite"
        )
    if _is_nonempty_dir(out_folder) and force:
        for child in out_folder.iterdir():
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
    out_folder.mkdir(parents=True, exist_ok=True)


def write_outputs(
    *,
    out_folder: Path,
    manifest: str,
    makefile: str,
    definitions: dict[str, str],
    macros: dict[str, str] | None,
) -> None:
    """Write all generated files into out_folder.

    `definitions` is keyed by full filename (``"table.sql"``, ``"table2.sql"``,
    …); the orchestrator decides chunk names. Macros are still keyed by slug
    because there's exactly one macro file per type.

    The folder must already exist — call `prepare_out_folder` first.
    """
    out_folder.mkdir(parents=True, exist_ok=True)
    (out_folder / "manifest.yml").write_text(manifest)
    (out_folder / "Makefile").write_text(makefile)

    definitions_dir = out_folder / "sources" / "definitions"
    definitions_dir.mkdir(parents=True, exist_ok=True)
    for filename, body in definitions.items():
        if not body:
            continue
        (definitions_dir / filename).write_text(body)

    if macros:
        macros_dir = out_folder / "sources" / "macros"
        macros_dir.mkdir(parents=True, exist_ok=True)
        for slug, body in macros.items():
            (macros_dir / f"{slug}.sql").write_text(body)
```

- [ ] **Step 4: Run the render tests**

Run: `uv run pytest tests/test_render.py -v`
Expected: All 6 tests PASS.

- [ ] **Step 5: Run the full suite (will see orchestrator failures — expected)**

Run: `uv run pytest -v`
Expected: `tests/test_orchestrator.py` will fail because the orchestrator still passes `definitions[plugin.file_slug] = ...` (a slug-keyed dict). That breakage is fixed in Task 3. Other tests pass.

If pre-commit runs the full test suite or mypy across the whole tree and fails on the orchestrator type mismatch, that is a real blocker for committing this in isolation — STOP and report BLOCKED. The controller can advise combining Tasks 2+3 into one commit.

- [ ] **Step 6: Commit (only if pre-commit passes)**

```bash
git add src/dcmexporter/render.py tests/test_render.py
git commit -m "refactor: write_outputs takes filename-keyed definitions"
```

If pre-commit fails because the orchestrator's call site is now type-mismatched, report BLOCKED — Tasks 2+3 will need to land together (the same way Tasks 3+4 did in the previous plan).

---

## Task 3: Wire orchestrator to chunk and log per-file counts

**Files:**
- Modify: `src/dcmexporter/orchestrator.py`
- Modify: `tests/test_orchestrator.py`

- [ ] **Step 1: Update orchestrator imports and the export() function**

In `src/dcmexporter/orchestrator.py`, add an import:

```python
from dcmexporter.chunking import (
    OBJECTS_PER_FILE_ENV,
    chunk_blocks,
    resolve_objects_per_file,
)
```

Then replace the per-type loop's "save the result" tail and the writing section. The relevant sections of the current file are around lines 116 (`definitions[plugin.file_slug] = ...`) and 122–131 (the `write_outputs` call).

Specifically:

(a) At the top of `export()`, just after `registry = build_registry()`, resolve the chunk size once so the env-var error fires before connecting to Snowflake:

```python
registry = build_registry()
objects_per_file = resolve_objects_per_file()
```

(b) Change the type-name loop's tail. Currently:

```python
            definitions[plugin.file_slug] = "\n".join(blocks)
            if macros is not None:
                macros[plugin.file_slug] = plugin.macro_definition()
```

Replace with:

```python
            chunks = chunk_blocks(
                blocks, slug=plugin.file_slug, size=objects_per_file
            )
            for filename, chunk_blocks_list in chunks:
                definitions[filename] = "\n".join(chunk_blocks_list)
                log.info(
                    f"{len(chunk_blocks_list)} {plugin.file_slug}(s) written "
                    f"to {filename}"
                )
            if len(chunks) > 1:
                log.info(
                    f"file size is configurable via {OBJECTS_PER_FILE_ENV} "
                    f"(currently {objects_per_file})"
                )
            if macros is not None:
                macros[plugin.file_slug] = plugin.macro_definition()
```

Note: `definitions` is now `dict[str, str]` keyed by **filename** (`"table.sql"`, `"table2.sql"`, …), not slug.

(c) The `write_outputs` call site is unchanged in shape — it already passes `definitions=definitions` — but now those keys are filenames. This matches Task 2's `write_outputs` contract.

The complete updated `export()` body (drop-in replacement for lines 19–161 of the current file) is:

```python
def export(cfg: Config) -> int:
    registry = build_registry()
    try:
        objects_per_file = resolve_objects_per_file()
    except ValueError as exc:
        print(f"[dcmexporter] {exc}", file=sys.stderr)
        return 5
    account_identifier = ""
    conn: Any | None = None
    log: RunLog | None = None

    try:
        try:
            prepare_out_folder(cfg.out_folder, force=cfg.force)
        except OutFolderError as exc:
            print(f"[dcmexporter] {exc}", file=sys.stderr)
            return 5

        log = RunLog(cfg.out_folder / "dcmexporter.log")
        log.info(f"export starting database={cfg.database} out_folder={cfg.out_folder}")

        with StatusDashboard(stream=sys.stderr) as status:
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
                    status.log(f"[dcmexporter] discover failed for {type_name}: {exc}")
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

                chunks = chunk_blocks(
                    blocks, slug=plugin.file_slug, size=objects_per_file
                )
                for filename, chunk in chunks:
                    definitions[filename] = "\n".join(chunk)
                    log.info(
                        f"{len(chunk)} {plugin.file_slug}(s) written to {filename}"
                    )
                if len(chunks) > 1:
                    log.info(
                        f"file size is configurable via {OBJECTS_PER_FILE_ENV} "
                        f"(currently {objects_per_file})"
                    )
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

Note: I renamed the inner loop variable `chunk_blocks_list` to plain `chunk` in the final form to avoid shadowing the imported `chunk_blocks` function. Use exactly this version.

- [ ] **Step 2: Update existing orchestrator tests + add chunking test**

Open `tests/test_orchestrator.py`. The existing tests already pass `Config` with `out_folder=tmp_path / "out"`. They reference `out / "sources" / "definitions" / "table.sql"` which still works because a single-file export still writes `table.sql`. But we need to add one test that exercises chunking.

Append this test to the end of `tests/test_orchestrator.py`:

```python
def test_export_chunks_definitions_when_over_threshold(
    tmp_path: Path, monkeypatch
) -> None:
    """With a small DCMASSIST_EXPORT_OBJECTS_PER_FILE, a per-type DDL list
    that exceeds the threshold should split into table.sql, table2.sql, etc.,
    and the log should record one line per file plus an env-var hint."""
    monkeypatch.setenv("DCMASSIST_EXPORT_OBJECTS_PER_FILE", "2")

    out = tmp_path / "out"
    fake_cursor = MagicMock()
    fake_conn = MagicMock()
    fake_conn.account = "AB12345"
    fake_conn.cursor.return_value = fake_cursor

    def execute_side_effect(sql, *args, **kwargs):
        fake_cursor._last_sql = sql

    def fetchall_side_effect():
        if "SHOW SCHEMAS" in fake_cursor._last_sql:
            return [{"name": "PUBLIC", "database_name": "MYDB"}]
        if "SHOW TABLES" in fake_cursor._last_sql:
            return [
                {"name": f"T{i}", "schema_name": "PUBLIC"} for i in range(5)
            ]
        return []

    def fetchone_side_effect():
        if "GET_DDL" in fake_cursor._last_sql:
            return [
                f"CREATE OR REPLACE TABLE MYDB.PUBLIC.{fake_cursor._last_sql.split('.')[-1].rstrip(\"', TRUE)\")} (X INT)"
            ]
        return None

    fake_cursor.execute.side_effect = execute_side_effect
    fake_cursor.fetchall.side_effect = fetchall_side_effect
    fake_cursor.fetchone.side_effect = fetchone_side_effect

    with patch("dcmexporter.orchestrator.open_connection") as oc:
        oc.return_value = fake_conn
        code = export(_cfg(out))

    assert code == 0
    defs = out / "sources" / "definitions"
    assert (defs / "table.sql").exists()
    assert (defs / "table2.sql").exists()
    assert (defs / "table3.sql").exists()  # 5 blocks at size=2 → 3 files
    assert not (defs / "table4.sql").exists()

    log_text = (out / "dcmexporter.log").read_text()
    assert "2 table(s) written to table.sql" in log_text
    assert "2 table(s) written to table2.sql" in log_text
    assert "1 table(s) written to table3.sql" in log_text
    assert "DCMASSIST_EXPORT_OBJECTS_PER_FILE" in log_text


def test_export_invalid_objects_per_file_returns_5(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """A malformed env var must surface clearly and not start the export."""
    monkeypatch.setenv("DCMASSIST_EXPORT_OBJECTS_PER_FILE", "abc")
    out = tmp_path / "out"
    code = export(_cfg(out))
    assert code == 5
    err = capsys.readouterr().err
    assert "DCMASSIST_EXPORT_OBJECTS_PER_FILE" in err
```

The fake `fetchone_side_effect` above uses string slicing on the last GET_DDL SQL to recover the table name. If that proves brittle, simplify it to a counter:

```python
    counter = {"i": 0}

    def fetchone_side_effect():
        if "GET_DDL" in fake_cursor._last_sql:
            counter["i"] += 1
            return [f"CREATE OR REPLACE TABLE MYDB.PUBLIC.T{counter['i']} (X INT)"]
        return None
```

Use the counter form — it's clearer and doesn't depend on parsing the SQL.

The final shape of `test_export_chunks_definitions_when_over_threshold` should be:

```python
def test_export_chunks_definitions_when_over_threshold(
    tmp_path: Path, monkeypatch
) -> None:
    """With a small DCMASSIST_EXPORT_OBJECTS_PER_FILE, a per-type DDL list
    that exceeds the threshold should split into table.sql, table2.sql, etc.,
    and the log should record one line per file plus an env-var hint."""
    monkeypatch.setenv("DCMASSIST_EXPORT_OBJECTS_PER_FILE", "2")

    out = tmp_path / "out"
    fake_cursor = MagicMock()
    fake_conn = MagicMock()
    fake_conn.account = "AB12345"
    fake_conn.cursor.return_value = fake_cursor

    counter = {"i": 0}

    def execute_side_effect(sql, *args, **kwargs):
        fake_cursor._last_sql = sql

    def fetchall_side_effect():
        if "SHOW SCHEMAS" in fake_cursor._last_sql:
            return [{"name": "PUBLIC", "database_name": "MYDB"}]
        if "SHOW TABLES" in fake_cursor._last_sql:
            return [{"name": f"T{i}", "schema_name": "PUBLIC"} for i in range(5)]
        return []

    def fetchone_side_effect():
        if "GET_DDL" in fake_cursor._last_sql:
            counter["i"] += 1
            return [f"CREATE OR REPLACE TABLE MYDB.PUBLIC.T{counter['i']} (X INT)"]
        return None

    fake_cursor.execute.side_effect = execute_side_effect
    fake_cursor.fetchall.side_effect = fetchall_side_effect
    fake_cursor.fetchone.side_effect = fetchone_side_effect

    with patch("dcmexporter.orchestrator.open_connection") as oc:
        oc.return_value = fake_conn
        code = export(_cfg(out))

    assert code == 0
    defs = out / "sources" / "definitions"
    assert (defs / "table.sql").exists()
    assert (defs / "table2.sql").exists()
    assert (defs / "table3.sql").exists()
    assert not (defs / "table4.sql").exists()

    log_text = (out / "dcmexporter.log").read_text()
    assert "2 table(s) written to table.sql" in log_text
    assert "2 table(s) written to table2.sql" in log_text
    assert "1 table(s) written to table3.sql" in log_text
    assert "DCMASSIST_EXPORT_OBJECTS_PER_FILE" in log_text
```

- [ ] **Step 3: Run full test suite**

Run: `uv run pytest -v`
Expected: All tests PASS (chunking test plus the existing 166).

- [ ] **Step 4: Run linters and type checker**

Run: `uv run ruff check src tests && uv run ruff format --check src tests && uv run mypy src`
Expected: All green.

- [ ] **Step 5: Smoke-test against a live database**

Run: `uv run dcmexporter export --database EXPERIMENTATION --force`
Expected:
- `out/sources/definitions/` contains numbered files for any type with more than 100 objects (e.g. `table.sql`, `table2.sql`, …).
- `out/dcmexporter.log` contains lines like `100 table(s) written to table.sql`, `100 table(s) written to table2.sql`, etc.
- Exactly one `file size is configurable via DCMASSIST_EXPORT_OBJECTS_PER_FILE (currently 100)` line per type that was chunked.

If the user can't run live, skip this step.

- [ ] **Step 6: Commit**

If Task 2 was already committed alone:

```bash
git add src/dcmexporter/orchestrator.py src/dcmexporter/chunking.py tests/test_orchestrator.py
git commit -m "feat: chunk per-type definitions into numbered files"
```

(Note: `chunking.py` should already be committed from Task 1; only re-stage if you're combining commits because Task 2 was blocked.)

If Tasks 2+3 must be combined per Task 2 Step 6's blocker note:

```bash
git add src/dcmexporter/render.py tests/test_render.py src/dcmexporter/orchestrator.py tests/test_orchestrator.py
git commit -m "feat: chunk per-type definitions into numbered files"
```

---

## Task 4: Update PR body and push

**Files:**
- None (GitHub only)

- [ ] **Step 1: Append the new feature to PR #2's body**

Run:

```bash
gh pr view 2 --json body --jq .body > /tmp/pr-body.md
```

Append a bullet under `## Summary` → `### What changed`:

```
- **Per-type definitions split into numbered files when over 100 objects.** Default `100` is configurable via `DCMASSIST_EXPORT_OBJECTS_PER_FILE`. The first file keeps the original name (`table.sql`); subsequent files are `table2.sql`, `table3.sql`, … The log records one line per file written and one env-var hint per type that was chunked.
```

Then run:

```bash
gh pr edit 2 --body-file /tmp/pr-body.md
```

- [ ] **Step 2: Push**

```bash
git push
```

---

## Self-Review Notes

**Spec coverage:**
- "When 100 objects have been outputted start outputting to a different file (numbered 2,3,4,5)" → Task 1 `chunk_blocks` (first file unsuffixed, subsequent files suffixed `2,3,…`). Task 1 test `test_chunk_many_files_uses_2_3_4_naming`.
- "Whenever a file is written write an entry in the log stating how many objects have been written (e.g. 34 tables written to table6.sql)" → Task 3 `log.info(f"{len(chunk)} {plugin.file_slug}(s) written to {filename}")`. Task 3 test asserts three such log lines exist.
- "Default 100 objects per file, configurable via env var DCMASSIST_EXPORT_OBJECTS_PER_FILE" → Task 1 `DEFAULT_OBJECTS_PER_FILE = 100`, `OBJECTS_PER_FILE_ENV = "DCMASSIST_EXPORT_OBJECTS_PER_FILE"`, `resolve_objects_per_file()`. Task 1 tests cover unset/set/invalid/zero/negative.
- "Whenever there are more than the specified number of objects write an entry in the log stating that the number of objects in the file is configurable via this env var" → Task 3 `if len(chunks) > 1: log.info(...)`. Test asserts the env-var name appears in the log.

**Placeholder scan:** No "TBD" / "implement later" / vague "handle edge cases" in any task. The "if blocked, escalate" notes in Task 2 are explicit (because the same blocker actually happened in the previous plan).

**Type consistency:**
- `chunk_blocks(blocks, *, slug, size) -> list[tuple[str, list[str]]]` — same signature in helper definition (Task 1) and call site (Task 3).
- `OBJECTS_PER_FILE_ENV` constant — same name in tests, helper, orchestrator log message.
- `definitions: dict[str, str]` keyed by **filename** — consistent across `write_outputs` (Task 2), orchestrator (Task 3), and tests (Task 2 + Task 3).
- The PR body bullet says "configurable via `DCMASSIST_EXPORT_OBJECTS_PER_FILE`" matching the constant.
