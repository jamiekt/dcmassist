# Real Snowflake Discovery Fixes — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the six bugs that surface when `dcmexporter export` runs against a real Snowflake account: invalid SQL for Database/Schema discovery, mis-indexed tuple parsing for per-schema row metadata, the 10K-row SHOW limit on large databases, the unsupported `GET_DDL('STAGE', …)` call, and the broken `--schema` filter syntax.

**Architecture:** Switch the connector to `DictCursor` so all rows are dicts keyed by Snowflake's real column names (`name`, `database_name`, `schema_name`). Refactor the shared base plugin to discover schemas first and iterate `SHOW … IN SCHEMA` per-schema (works around the 10K cap and gives consistent shapes). Override `discover` on Database/Schema (account-level vs database-level forms) and override `get_ddl` on Stage (use `DESC STAGE` + a pure synthesizer to build `CREATE OR REPLACE STAGE`). Keep credentials out of the synthesized DDL — emit only `URL` + `STORAGE_INTEGRATION`; skip stages without an integration.

**Tech Stack:** snowflake-connector-python (DictCursor), pytest with `unittest.mock`, ruff/mypy. No new dependencies.

---

## Background — confirmed via live probe

The previous (mock-only) tests fed idealized dicts and passed; they didn't reflect what Snowflake actually returns. Confirmed shapes (real run, 2026-05-23):

| SHOW form | columns (relevant subset) | row type |
|---|---|---|
| `SHOW DATABASES` | `name`, `is_default`, `is_current`, … (no `database_name`) | tuple by default |
| `SHOW SCHEMAS IN DATABASE X` | `name`, `database_name`, … (no `schema_name`) | tuple |
| `SHOW VIEWS IN ...` | `name`, `database_name`, `schema_name`, … | tuple |
| `SHOW TABLES IN ...` | `name`, `database_name`, `schema_name`, … | tuple |
| `SHOW SEQUENCES IN ...` | `name`, `database_name`, `schema_name`, … | tuple |
| `SHOW STAGES IN ...` | `name`, `database_name`, `schema_name`, `url`, `type`, `storage_integration`, … | tuple |
| `SHOW FILE FORMATS IN ...` | `name`, `database_name`, `schema_name`, … | tuple |
| `SHOW TAGS IN ...` | `name`, `database_name`, `schema_name`, … | tuple |
| `SHOW WAREHOUSES` | `name`, … (no `database_name`/`schema_name`) | tuple |

Other confirmed facts:
- `cursor = conn.cursor(DictCursor)` returns dicts keyed by these column names. **All plugins will use this.**
- `GET_DDL('STAGE', '<fqn>')` returns `Invalid object type: 'STAGE'` (verified on a real existing stage, not just nonexistent).
- `GET_DDL('WAREHOUSE', '<name>')` works.
- `GET_DDL('FILE_FORMAT', '<fqn>')` works.
- `SHOW SCHEMAS LIKE 'X' IN DATABASE Y` is the correct filter syntax (the current `SHOW SCHEMAS IN SCHEMA Y.X` is invalid).
- `INFORMATION_SCHEMA` exists in every database and contains 60+ system views — must be excluded.
- Real DBs can have 80K+ tables: `SHOW TABLES IN DATABASE` exceeds Snowflake's 10K-row cap. Per-schema iteration is mandatory.

---

## File Structure

**Modify:**
- `src/dcmexporter/connection.py` — return a `DictCursor`
- `src/dcmexporter/objects/_base.py` — dict-only `_rows_to_fqns`; schema-iteration `discover`; INFORMATION_SCHEMA exclusion
- `src/dcmexporter/objects/database.py` — custom `discover` using `SHOW DATABASES LIKE`
- `src/dcmexporter/objects/schema.py` — custom `discover` (LIKE-based filtering)
- `src/dcmexporter/objects/stage.py` — custom `get_ddl` using `DESC STAGE` + synthesizer
- `src/dcmexporter/objects/warehouse.py` — drop the now-redundant tuple branch
- `tests/test_objects/test_*.py` — fixtures use real column names; multi-call mocks for schema-iteration

**Create:**
- `src/dcmexporter/objects/_stage_ddl.py` — pure stage DDL synthesizer (no cursor)
- `tests/test_objects/test_stage_ddl.py` — unit tests for the synthesizer

---

## Task 1: Switch connection to DictCursor

**Files:**
- Modify: `src/dcmexporter/connection.py`
- Modify: `tests/test_connection.py`

- [ ] **Step 1: Read current connection.py and connection test**

Run: `cat src/dcmexporter/connection.py tests/test_connection.py`
Goal: confirm `open_connection` currently returns a plain connection and the orchestrator does `conn.cursor()` (no DictCursor argument).

- [ ] **Step 2: Add a failing test asserting cursor() returns a DictCursor-shaped cursor**

Append to `tests/test_connection.py`:

```python
def test_open_connection_yields_dict_cursor(monkeypatch) -> None:
    """The connection wrapper must return DictCursor by default so plugins receive
    dict rows keyed by Snowflake column names. See plan: 2026-05-23-real-snowflake-discovery-fixes."""
    captured: dict = {}

    class FakeCursor:
        pass

    class FakeConn:
        def cursor(self, cursor_class=None):
            captured["cursor_class"] = cursor_class
            return FakeCursor()

    monkeypatch.setattr(
        "dcmexporter.connection.snowflake_connect", lambda **_: FakeConn()
    )

    from dcmexporter.connection import open_connection
    from snowflake.connector import DictCursor

    conn = open_connection(None)
    conn.cursor()  # plugins call cursor() — wrapper must inject DictCursor
    assert captured["cursor_class"] is DictCursor
```

- [ ] **Step 3: Run the test — expect failure**

Run: `uv run pytest tests/test_connection.py::test_open_connection_yields_dict_cursor -v`
Expected: FAIL — `captured["cursor_class"]` is `None` because nothing forces DictCursor yet.

- [ ] **Step 4: Implement DictCursor injection**

Replace the body of `open_connection` in `src/dcmexporter/connection.py` so it wraps the underlying connection and forces `cursor()` to use `DictCursor`. Replace the existing `open_connection` function with:

```python
from snowflake.connector import DictCursor


class _DictCursorConnection:
    """Thin wrapper that makes every `cursor()` call use a DictCursor.

    Plugins call `conn.cursor()` with no arguments; this delegates to the real
    connection but injects DictCursor so rows come back as dicts keyed by
    Snowflake's column names.
    """

    def __init__(self, inner: Any) -> None:
        self._inner = inner

    def cursor(self, cursor_class: Any = None) -> Any:
        return self._inner.cursor(cursor_class or DictCursor)

    def close(self) -> None:
        self._inner.close()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


def open_connection(connection_name: str | None) -> Any:
    """Open a Snowflake connection following snow CLI's resolution rules.

    Order of precedence:
    1. Explicit `connection_name` argument.
    2. SNOWFLAKE_DEFAULT_CONNECTION_NAME env var.
    3. snowflake-connector's own default behaviour (reads `~/.snowflake/connections.toml`).

    The returned connection always yields DictCursor-backed cursors so plugins
    receive dict rows keyed by Snowflake's column names.
    """
    name = connection_name or os.environ.get("SNOWFLAKE_DEFAULT_CONNECTION_NAME")
    try:
        if name:
            inner = snowflake_connect(connection_name=name)
        else:
            inner = snowflake_connect()
    except Exception as exc:  # noqa: BLE001 — we re-raise as a domain error
        raise SnowflakeConnectionError(
            f"Failed to open Snowflake connection (name={name!r}): {exc}"
        ) from exc
    return _DictCursorConnection(inner)
```

Add to the existing imports at the top of the file (after the existing `from snowflake.connector import connect as snowflake_connect` block):

```python
try:
    from snowflake.connector import DictCursor
except ImportError:  # pragma: no cover
    class DictCursor:  # type: ignore[no-redef]
        pass
```

- [ ] **Step 5: Run all connection tests — expect pass**

Run: `uv run pytest tests/test_connection.py -v`
Expected: PASS for the new test plus all existing connection tests.

- [ ] **Step 6: Run full suite to confirm no regressions**

Run: `uv run pytest tests/ -q`
Expected: same number of failures (or all pass) as before; no new failures from this change. Plugin tests pass dicts to MagicMock cursors directly, so they don't go through the wrapper.

- [ ] **Step 7: Commit**

```bash
git add src/dcmexporter/connection.py tests/test_connection.py
git commit -m "feat(connection): force DictCursor so plugins receive dict rows"
```

---

## Task 2: Make `_rows_to_fqns` dict-only with real Snowflake column names

**Files:**
- Modify: `src/dcmexporter/objects/_base.py:57-70`

The current `_rows_to_fqns` accepts both dict and tuple rows, with a positional `row[3]` fallback for schema. With DictCursor we always get dicts. The current dict branch reads `schema_name` (correct for views/tables/etc.) and falls back to `schema` and `name`. That's mostly right — but the comment is wrong and we can simplify.

- [ ] **Step 1: Read current `_rows_to_fqns`**

Run: `sed -n '55,72p' src/dcmexporter/objects/_base.py`
Goal: confirm current behavior (it reads `row["schema_name"]`).

- [ ] **Step 2: Add a failing test asserting dict-only behavior with real column names**

Create or append to `tests/test_objects/test_base_helpers.py`:

```python
"""Tests for V1ObjectPlugin shared helpers."""

from __future__ import annotations

import pytest

from dcmexporter.objects._base import V1ObjectPlugin


class _MinimalPlugin(V1ObjectPlugin):
    type_name = "Test"
    file_slug = "test"
    SHOW_FORM = "SHOW THINGS"
    GET_DDL_TYPE = "THING"
    MACRO_BODY = "{% macro define_test() %}{% endmacro %}"


def test_rows_to_fqns_uses_schema_name_key() -> None:
    """Real Snowflake column is `schema_name` (per SHOW VIEWS/TABLES/etc)."""
    plugin = _MinimalPlugin()
    rows = [{"name": "T1", "schema_name": "PUBLIC", "database_name": "MYDB"}]
    out = plugin._rows_to_fqns(rows, "MYDB")
    assert [str(f) for f in out] == ["MYDB.PUBLIC.T1"]


def test_rows_to_fqns_rejects_tuple_rows() -> None:
    """With DictCursor mandatory, tuple rows are an error."""
    plugin = _MinimalPlugin()
    with pytest.raises((TypeError, KeyError)):
        plugin._rows_to_fqns([("created", "T1", "MYDB", "PUBLIC")], "MYDB")
```

- [ ] **Step 3: Run the tests — expect the second to fail**

Run: `uv run pytest tests/test_objects/test_base_helpers.py -v`
Expected: `test_rows_to_fqns_uses_schema_name_key` PASSES (current code already supports `schema_name`); `test_rows_to_fqns_rejects_tuple_rows` FAILS because the current tuple branch silently parses the tuple.

- [ ] **Step 4: Replace `_rows_to_fqns` with a dict-only version**

In `src/dcmexporter/objects/_base.py`, replace the current `_rows_to_fqns` (and update its imports/types if needed) with:

```python
def _rows_to_fqns(self, rows: list[dict[str, Any]], database: str) -> list[FQN]:
    """Convert DictCursor rows into FQNs.

    Snowflake's `SHOW <type> IN [DATABASE|SCHEMA]` returns rows with `name` and,
    for per-schema types, `schema_name`. Account-level types (Database, Warehouse)
    have no `schema_name` and use `schema=None`.
    """
    out: list[FQN] = []
    for row in rows:
        if not isinstance(row, dict):
            raise TypeError(
                f"{self.type_name} discover received a non-dict row "
                f"({type(row).__name__}); cursor must be a DictCursor"
            )
        out.append(
            FQN(
                database=database,
                schema=row.get("schema_name"),
                name=row["name"],
            )
        )
    return out
```

Also update the method's type signature to reflect `list[dict[str, Any]]` if mypy complains. The list type passed by `discover` will need to be widened where it's called.

- [ ] **Step 5: Run the helper tests — expect pass**

Run: `uv run pytest tests/test_objects/test_base_helpers.py -v`
Expected: both tests PASS.

- [ ] **Step 6: Run full suite — observe which tests now fail**

Run: `uv run pytest tests/ -q 2>&1 | tail -40`
Expected: many existing per-plugin tests fail because their fixtures pass dicts without `database_name` (fine — schema_name is what we use) OR because they pass tuple rows (none do currently — they all use dicts). Confirm only test failures are about row-shape changes, not logic changes. Document the failures — they'll be fixed in subsequent tasks as those plugins' tests get updated.

- [ ] **Step 7: Commit**

```bash
git add src/dcmexporter/objects/_base.py tests/test_objects/test_base_helpers.py
git commit -m "refactor(objects): dict-only _rows_to_fqns; reject tuple rows"
```

---

## Task 3: Schema-iteration discovery in base + INFORMATION_SCHEMA exclusion

**Files:**
- Modify: `src/dcmexporter/objects/_base.py:42-55`

Real DBs have >10K tables, blowing past Snowflake's `SHOW TABLES IN DATABASE` cap. Fix: when no schema filter is given, list schemas first then loop `SHOW <TYPE> IN SCHEMA <db>.<schema>` per schema. This also gives a consistent code path with the schemas-filter case. Always exclude `INFORMATION_SCHEMA`.

This refactor only affects per-schema plugins (Table, View, Sequence, Stage, File format, Tag). Database, Schema, Warehouse override `discover` (Database/Schema added in later tasks; Warehouse already does).

- [ ] **Step 1: Add a failing test for schema-iteration discovery**

In `tests/test_objects/test_base_helpers.py`, append:

```python
from unittest.mock import MagicMock


def test_discover_iterates_schemas_when_no_filter() -> None:
    """When schemas=None, base discover lists schemas first then SHOWs per-schema.
    Avoids Snowflake's 10K-row limit on SHOW <type> IN DATABASE for large DBs.
    """
    cursor = MagicMock()
    sql_log: list[str] = []

    def execute(sql: str) -> None:
        sql_log.append(sql)

    schemas_response = [
        {"name": "PUBLIC", "database_name": "MYDB"},
        {"name": "INFORMATION_SCHEMA", "database_name": "MYDB"},
        {"name": "ANALYTICS", "database_name": "MYDB"},
    ]
    things_in_public = [{"name": "T1", "schema_name": "PUBLIC"}]
    things_in_analytics = [{"name": "T2", "schema_name": "ANALYTICS"}]

    fetch_responses = iter([schemas_response, things_in_public, things_in_analytics])
    cursor.execute.side_effect = execute
    cursor.fetchall.side_effect = lambda: next(fetch_responses)

    plugin = _MinimalPlugin()
    out = plugin.discover(cursor, "MYDB", None)

    assert sql_log == [
        "SHOW SCHEMAS IN DATABASE MYDB",
        "SHOW THINGS IN SCHEMA MYDB.ANALYTICS",
        "SHOW THINGS IN SCHEMA MYDB.PUBLIC",
    ]
    assert [str(f) for f in out] == ["MYDB.ANALYTICS.T2", "MYDB.PUBLIC.T1"]


def test_discover_with_schemas_filter_skips_schema_listing() -> None:
    cursor = MagicMock()
    sql_log: list[str] = []

    def execute(sql: str) -> None:
        sql_log.append(sql)

    cursor.execute.side_effect = execute
    cursor.fetchall.return_value = [
        {"name": "T", "schema_name": "S"},
    ]

    plugin = _MinimalPlugin()
    out = plugin.discover(cursor, "MYDB", ("S",))

    assert sql_log == ["SHOW THINGS IN SCHEMA MYDB.S"]
    assert [str(f) for f in out] == ["MYDB.S.T"]
```

- [ ] **Step 2: Run — expect failure**

Run: `uv run pytest tests/test_objects/test_base_helpers.py::test_discover_iterates_schemas_when_no_filter tests/test_objects/test_base_helpers.py::test_discover_with_schemas_filter_skips_schema_listing -v`
Expected: FAIL — current `discover` runs `SHOW THINGS IN DATABASE MYDB` once, doesn't list schemas first.

- [ ] **Step 3: Replace base `discover`**

In `src/dcmexporter/objects/_base.py`, replace the current `discover` method with:

```python
def discover(
    self, cursor: Any, database: str, schemas: tuple[str, ...] | None
) -> list[FQN]:
    if not self.SHOW_FORM:
        raise NotImplementedError(self.type_name)

    target_schemas = self._target_schemas(cursor, database, schemas)

    rows: list[FQN] = []
    for schema in sorted(target_schemas):
        cursor.execute(f"{self.SHOW_FORM} IN SCHEMA {database}.{schema}")
        rows.extend(self._rows_to_fqns(cursor.fetchall(), database))
    return sorted(rows, key=lambda f: (f.schema or "", f.name))


def _target_schemas(
    self, cursor: Any, database: str, schemas: tuple[str, ...] | None
) -> list[str]:
    """Resolve which schemas to enumerate.

    With an explicit filter we trust the caller. Without one we list every schema
    in the database first (cheap — schemas are few) and exclude INFORMATION_SCHEMA,
    which holds Snowflake's system views and would otherwise pollute every export.
    """
    if schemas:
        return list(schemas)
    cursor.execute(f"SHOW SCHEMAS IN DATABASE {database}")
    return [
        row["name"]
        for row in cursor.fetchall()
        if row["name"] != "INFORMATION_SCHEMA"
    ]
```

- [ ] **Step 4: Run base helper tests — expect pass**

Run: `uv run pytest tests/test_objects/test_base_helpers.py -v`
Expected: all base-helper tests PASS.

- [ ] **Step 5: Update per-schema plugin tests (Table, View, Sequence, Stage, File format, Tag)**

Each of these test files currently asserts `cursor.execute.assert_called_once_with("SHOW <X> IN DATABASE MYDB")` and feeds a single fetchall response. They need updating to mock the schema-listing call + per-schema SHOW calls.

For each of `tests/test_objects/test_table.py`, `test_view.py`, `test_sequence.py`, `test_stage.py`, `test_file_format.py`, `test_tag.py`, replace the first two test functions with the pattern below (substituting the right SHOW form and type-name).

`tests/test_objects/test_table.py` first two tests become:

```python
def test_discover_lists_schemas_then_iterates() -> None:
    cursor = MagicMock()
    sql_log: list[str] = []
    cursor.execute.side_effect = lambda sql: sql_log.append(sql)
    fetch_responses = iter(
        [
            [{"name": "PUBLIC", "database_name": "MYDB"}],
            [
                {"name": "T1", "schema_name": "PUBLIC", "database_name": "MYDB"},
                {"name": "T2", "schema_name": "PUBLIC", "database_name": "MYDB"},
            ],
        ]
    )
    cursor.fetchall.side_effect = lambda: next(fetch_responses)

    out = plugin.discover(cursor, "MYDB", None)
    assert sql_log == [
        "SHOW SCHEMAS IN DATABASE MYDB",
        "SHOW TABLES IN SCHEMA MYDB.PUBLIC",
    ]
    assert [str(f) for f in out] == ["MYDB.PUBLIC.T1", "MYDB.PUBLIC.T2"]


def test_discover_filters_by_schema() -> None:
    cursor = MagicMock()
    sql_log: list[str] = []
    cursor.execute.side_effect = lambda sql: sql_log.append(sql)
    cursor.fetchall.return_value = [
        {"name": "T", "schema_name": "S", "database_name": "MYDB"}
    ]
    out = plugin.discover(cursor, "MYDB", ("S",))
    assert sql_log == ["SHOW TABLES IN SCHEMA MYDB.S"]
    assert [str(f) for f in out] == ["MYDB.S.T"]
```

Apply the same pattern to test_view.py (substitute "VIEWS"), test_sequence.py (substitute "SEQUENCES"), test_stage.py (substitute "STAGES"), test_file_format.py (substitute "FILE FORMATS"), test_tag.py (substitute "TAGS").

- [ ] **Step 6: Run all object tests — expect pass**

Run: `uv run pytest tests/test_objects/ -v`
Expected: all PASS. The test_database.py, test_schema.py, test_warehouse.py tests still use the old single-call pattern — those are fixed in their dedicated tasks below.

Note: `test_database.py` and `test_schema.py` will FAIL here. That's expected — they're addressed in Tasks 4 and 5. Skip them with `-k "not (database or schema)"` if you want a clean signal, OR let them fail and document.

Run instead: `uv run pytest tests/test_objects/ -v -k "not (test_database or test_schema)"`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/dcmexporter/objects/_base.py tests/test_objects/test_base_helpers.py tests/test_objects/test_table.py tests/test_objects/test_view.py tests/test_objects/test_sequence.py tests/test_objects/test_stage.py tests/test_objects/test_file_format.py tests/test_objects/test_tag.py
git commit -m "refactor(objects): list schemas first then SHOW per-schema (10K limit fix)"
```

---

## Task 4: Database custom discover (`SHOW DATABASES LIKE`)

**Files:**
- Modify: `src/dcmexporter/objects/database.py`
- Modify: `tests/test_objects/test_database.py`

`SHOW DATABASES IN DATABASE X` is invalid Snowflake syntax. Database is account-level — use `SHOW DATABASES LIKE '<db>'`.

- [ ] **Step 1: Update test_database.py to expect `SHOW DATABASES LIKE`**

Read: `cat tests/test_objects/test_database.py`

Replace the first two test functions with:

```python
def test_discover_uses_show_databases_like() -> None:
    cursor = MagicMock()
    sql_log: list[str] = []
    cursor.execute.side_effect = lambda sql: sql_log.append(sql)
    cursor.fetchall.return_value = [{"name": "MYDB"}]
    out = plugin.discover(cursor, "MYDB", None)
    assert sql_log == ["SHOW DATABASES LIKE 'MYDB'"]
    assert [str(f) for f in out] == ["MYDB"]


def test_discover_ignores_schemas_argument() -> None:
    """Database is account-level; --schema is meaningless. Same SQL either way."""
    cursor = MagicMock()
    sql_log: list[str] = []
    cursor.execute.side_effect = lambda sql: sql_log.append(sql)
    cursor.fetchall.return_value = [{"name": "MYDB"}]
    plugin.discover(cursor, "MYDB", ("ANY",))
    assert sql_log == ["SHOW DATABASES LIKE 'MYDB'"]
```

- [ ] **Step 2: Run — expect failure**

Run: `uv run pytest tests/test_objects/test_database.py -v`
Expected: FAIL — current discover still uses base method which now does `SHOW SCHEMAS IN DATABASE MYDB` first, so SQL log will not match.

- [ ] **Step 3: Add custom `discover` to DatabasePlugin**

In `src/dcmexporter/objects/database.py`, add a `discover` method to the class:

```python
class DatabasePlugin(V1ObjectPlugin):
    type_name = "Database"
    file_slug = "database"
    SHOW_FORM = "SHOW DATABASES"
    GET_DDL_TYPE = "DATABASE"
    SUPPORTS_COMMENT = True
    MACRO_BODY = (
        # ... (unchanged macro body)
    )

    def discover(self, cursor, database, schemas):  # type: ignore[override]
        # Database is account-level: SHOW DATABASES has no IN DATABASE clause.
        # The --schema filter is meaningless here.
        cursor.execute(f"SHOW DATABASES LIKE '{database}'")
        from dcmexporter.types import FQN

        return [
            FQN(database=database, schema=None, name=row["name"])
            for row in cursor.fetchall()
        ]
```

- [ ] **Step 4: Run database tests — expect pass**

Run: `uv run pytest tests/test_objects/test_database.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dcmexporter/objects/database.py tests/test_objects/test_database.py
git commit -m "fix(database): SHOW DATABASES LIKE; account-level discovery"
```

---

## Task 5: Schema custom discover (LIKE-based filter syntax)

**Files:**
- Modify: `src/dcmexporter/objects/schema.py`
- Modify: `tests/test_objects/test_schema.py`

`SHOW SCHEMAS IN SCHEMA MYDB.S` is invalid. Correct filter form is `SHOW SCHEMAS LIKE 'S' IN DATABASE MYDB`. Real `SHOW SCHEMAS` returns `name` (schema) and `database_name` (parent) — no `schema_name`. The schema's FQN is `db.schema.schema` because schema = name = the same string.

- [ ] **Step 1: Update test_schema.py for the new SQL forms**

Replace the first two test functions in `tests/test_objects/test_schema.py`:

```python
def test_discover_uses_show_schemas_in_database_when_no_filter() -> None:
    cursor = MagicMock()
    sql_log: list[str] = []
    cursor.execute.side_effect = lambda sql: sql_log.append(sql)
    cursor.fetchall.return_value = [
        {"name": "PUBLIC", "database_name": "MYDB"},
        {"name": "INFORMATION_SCHEMA", "database_name": "MYDB"},
        {"name": "ANALYTICS", "database_name": "MYDB"},
    ]
    out = plugin.discover(cursor, "MYDB", None)
    assert sql_log == ["SHOW SCHEMAS IN DATABASE MYDB"]
    # INFORMATION_SCHEMA is excluded (system schema).
    assert [str(f) for f in out] == ["MYDB.ANALYTICS.ANALYTICS", "MYDB.PUBLIC.PUBLIC"]


def test_discover_filters_with_like_per_schema() -> None:
    cursor = MagicMock()
    sql_log: list[str] = []
    cursor.execute.side_effect = lambda sql: sql_log.append(sql)
    fetch_responses = iter(
        [
            [{"name": "S1", "database_name": "MYDB"}],
            [{"name": "S2", "database_name": "MYDB"}],
        ]
    )
    cursor.fetchall.side_effect = lambda: next(fetch_responses)

    out = plugin.discover(cursor, "MYDB", ("S1", "S2"))
    assert sql_log == [
        "SHOW SCHEMAS LIKE 'S1' IN DATABASE MYDB",
        "SHOW SCHEMAS LIKE 'S2' IN DATABASE MYDB",
    ]
    assert [str(f) for f in out] == ["MYDB.S1.S1", "MYDB.S2.S2"]
```

- [ ] **Step 2: Run — expect failure**

Run: `uv run pytest tests/test_objects/test_schema.py -v`
Expected: FAIL — current schema plugin uses base discover, gets the wrong SQL.

- [ ] **Step 3: Add custom discover to SchemaPlugin**

In `src/dcmexporter/objects/schema.py`, add a `discover` method:

```python
class SchemaPlugin(V1ObjectPlugin):
    type_name = "Schema"
    file_slug = "schema"
    SHOW_FORM = "SHOW SCHEMAS"
    GET_DDL_TYPE = "SCHEMA"
    SUPPORTS_COMMENT = True
    MACRO_BODY = (
        # ... unchanged
    )

    def discover(self, cursor, database, schemas):  # type: ignore[override]
        from dcmexporter.types import FQN

        rows: list[dict] = []
        if schemas:
            # Filter form: one query per requested name (Snowflake LIKE doesn't
            # accept arbitrary lists; safer to enumerate explicitly).
            for name in schemas:
                cursor.execute(f"SHOW SCHEMAS LIKE '{name}' IN DATABASE {database}")
                rows.extend(cursor.fetchall())
        else:
            cursor.execute(f"SHOW SCHEMAS IN DATABASE {database}")
            rows.extend(
                row
                for row in cursor.fetchall()
                if row["name"] != "INFORMATION_SCHEMA"
            )

        out = [
            FQN(database=database, schema=row["name"], name=row["name"])
            for row in rows
        ]
        return sorted(out, key=lambda f: f.name)
```

- [ ] **Step 4: Run schema tests — expect pass**

Run: `uv run pytest tests/test_objects/test_schema.py -v`
Expected: all PASS.

- [ ] **Step 5: Run full object suite to confirm**

Run: `uv run pytest tests/test_objects/ -v`
Expected: all PASS (except possibly warehouse — fixed in Task 6).

- [ ] **Step 6: Commit**

```bash
git add src/dcmexporter/objects/schema.py tests/test_objects/test_schema.py
git commit -m "fix(schema): LIKE-based filter; INFORMATION_SCHEMA excluded"
```

---

## Task 6: Warehouse plugin — drop redundant tuple branch

**Files:**
- Modify: `src/dcmexporter/objects/warehouse.py`
- Modify: `tests/test_objects/test_warehouse.py`

DictCursor means rows are always dicts; the warehouse `discover` has a stale `if isinstance(row, dict)` branch that's now dead code. Tighten it.

- [ ] **Step 1: Read current warehouse.py and its test**

Run: `cat src/dcmexporter/objects/warehouse.py tests/test_objects/test_warehouse.py`

- [ ] **Step 2: Update test_warehouse.py to use dict rows only and assert no `database_name` is required**

Replace the first two test functions in `tests/test_objects/test_warehouse.py`:

```python
def test_discover_uses_show_warehouses() -> None:
    cursor = MagicMock()
    sql_log: list[str] = []
    cursor.execute.side_effect = lambda sql: sql_log.append(sql)
    cursor.fetchall.return_value = [
        {"name": "WH1", "state": "STARTED"},
        {"name": "WH2", "state": "SUSPENDED"},
    ]
    out = plugin.discover(cursor, "MYDB", None)
    assert sql_log == ["SHOW WAREHOUSES"]
    assert [str(f) for f in out] == ["WH1", "WH2"]


def test_discover_ignores_schemas_argument() -> None:
    """Warehouse is account-level; schemas filter has no effect."""
    cursor = MagicMock()
    sql_log: list[str] = []
    cursor.execute.side_effect = lambda sql: sql_log.append(sql)
    cursor.fetchall.return_value = [{"name": "WH1"}]
    plugin.discover(cursor, "MYDB", ("ANY",))
    assert sql_log == ["SHOW WAREHOUSES"]
```

- [ ] **Step 3: Run — expect existing tests still pass or near-pass**

Run: `uv run pytest tests/test_objects/test_warehouse.py -v`
Expected: probably PASS already since warehouse already returns dicts in tests. If any fail, note which.

- [ ] **Step 4: Simplify warehouse.discover**

In `src/dcmexporter/objects/warehouse.py`, replace the discover method with the simpler dict-only form:

```python
def discover(self, cursor, database, schemas):  # type: ignore[override]
    # Warehouses are account-level, not database-level. --schema is ignored.
    from dcmexporter.types import FQN

    cursor.execute("SHOW WAREHOUSES")
    rows = cursor.fetchall()
    out = [FQN(database=database, schema=None, name=row["name"]) for row in rows]
    return sorted(out, key=lambda f: f.name)
```

- [ ] **Step 5: Run warehouse tests — expect pass**

Run: `uv run pytest tests/test_objects/test_warehouse.py -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add src/dcmexporter/objects/warehouse.py tests/test_objects/test_warehouse.py
git commit -m "refactor(warehouse): drop tuple branch; DictCursor implies dicts"
```

---

## Task 7: Stage DDL synthesizer (pure helper, no cursor)

**Files:**
- Create: `src/dcmexporter/objects/_stage_ddl.py`
- Create: `tests/test_objects/test_stage_ddl.py`

`GET_DDL('STAGE', …)` is unsupported by Snowflake. Replacement: call `DESC STAGE` and synthesize a minimal `CREATE OR REPLACE STAGE` DDL using only `URL` + `STORAGE_INTEGRATION` (skipping AWS credentials and other secrets). Stages without a storage integration are not exportable in v1 — raise an error so the orchestrator's per-object catch logs them.

The synthesizer is a pure function: `synthesize_stage_ddl(fqn, desc_rows) -> str`. Test in isolation.

- [ ] **Step 1: Create the synthesizer test file with failing tests**

Create `tests/test_objects/test_stage_ddl.py`:

```python
"""Tests for the stage DDL synthesizer."""

from __future__ import annotations

import pytest

from dcmexporter.objects._stage_ddl import (
    StageNotExportable,
    synthesize_stage_ddl,
)
from dcmexporter.types import FQN


def _row(parent: str, prop: str, value: str) -> dict:
    """A DESC STAGE row as DictCursor returns it."""
    return {
        "parent_property": parent,
        "property": prop,
        "property_value": value,
        "property_type": "String",
        "property_default": "",
    }


def test_minimal_external_stage_with_integration() -> None:
    fqn = FQN("MYDB", "PUBLIC", "MYSTAGE")
    rows = [
        _row("STAGE_LOCATION", "URL", '["s3://bucket/path/"]'),
        _row("STAGE_INTEGRATION", "STORAGE_INTEGRATION", "MY_INT"),
        _row("STAGE_CREDENTIALS", "AWS_ROLE", "arn:aws:iam::123:role/secret"),
    ]
    out = synthesize_stage_ddl(fqn, rows)
    assert out.startswith("CREATE OR REPLACE STAGE MYDB.PUBLIC.MYSTAGE")
    assert "URL = 's3://bucket/path/'" in out
    assert "STORAGE_INTEGRATION = MY_INT" in out
    # Credentials must NEVER end up in synthesized DDL.
    assert "AWS_ROLE" not in out
    assert "arn:aws:iam" not in out
    assert out.rstrip().endswith(";")


def test_stage_without_integration_raises() -> None:
    """Legacy stages with embedded credentials only — refuse to export."""
    fqn = FQN("MYDB", "PUBLIC", "OLDSTAGE")
    rows = [
        _row("STAGE_LOCATION", "URL", '["s3://bucket/path/"]'),
        _row("STAGE_CREDENTIALS", "AWS_KEY_ID", "AKIA..."),
    ]
    with pytest.raises(StageNotExportable):
        synthesize_stage_ddl(fqn, rows)


def test_stage_with_no_url_raises() -> None:
    fqn = FQN("MYDB", "PUBLIC", "S")
    rows = [_row("STAGE_INTEGRATION", "STORAGE_INTEGRATION", "INT")]
    with pytest.raises(StageNotExportable):
        synthesize_stage_ddl(fqn, rows)


def test_url_unwrapped_from_json_list() -> None:
    """DESC STAGE returns URL as a JSON-encoded list string: '["s3://..."]'."""
    fqn = FQN("MYDB", "PUBLIC", "S")
    rows = [
        _row("STAGE_LOCATION", "URL", '["s3://bucket/x/"]'),
        _row("STAGE_INTEGRATION", "STORAGE_INTEGRATION", "INT"),
    ]
    out = synthesize_stage_ddl(fqn, rows)
    assert "URL = 's3://bucket/x/'" in out
    assert '["s3' not in out
```

- [ ] **Step 2: Run — expect failure (module does not exist)**

Run: `uv run pytest tests/test_objects/test_stage_ddl.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'dcmexporter.objects._stage_ddl'`.

- [ ] **Step 3: Implement the synthesizer**

Create `src/dcmexporter/objects/_stage_ddl.py`:

```python
"""Synthesize CREATE OR REPLACE STAGE DDL from DESC STAGE output.

Snowflake does NOT support GET_DDL('STAGE', …) — verified live 2026-05-23. The
workaround is to read structured properties via DESC STAGE and emit a minimal
DDL covering URL + STORAGE_INTEGRATION. AWS/Azure credentials and other secrets
are deliberately excluded — exported DDL is committed to a DCM project (i.e.
git), and credentials belong to the storage integration, not the stage.

Stages without a storage integration (i.e. legacy stages with embedded
credentials only) are not exportable in v1 and raise StageNotExportable; the
orchestrator's per-object catch will log and skip them.
"""

from __future__ import annotations

import json

from dcmexporter.types import FQN


class StageNotExportable(RuntimeError):
    """Raised when a stage cannot be safely synthesized into committable DDL."""


def synthesize_stage_ddl(fqn: FQN, desc_rows: list[dict]) -> str:
    """Build a minimal CREATE OR REPLACE STAGE statement.

    Inputs:
      fqn: the stage's fully-qualified name.
      desc_rows: raw rows from `DESC STAGE <fqn>`. Each row has the keys
        `parent_property`, `property`, `property_value` (DictCursor shape).

    Output: a SQL string ending in `;`.

    Raises StageNotExportable if URL or STORAGE_INTEGRATION is missing.
    """
    properties: dict[tuple[str, str], str] = {
        (row["parent_property"], row["property"]): row["property_value"]
        for row in desc_rows
    }

    url_raw = properties.get(("STAGE_LOCATION", "URL"), "")
    url = _unwrap_url(url_raw)
    integration = properties.get(("STAGE_INTEGRATION", "STORAGE_INTEGRATION"), "")

    if not url:
        raise StageNotExportable(
            f"stage {fqn}: DESC STAGE returned no STAGE_LOCATION/URL"
        )
    if not integration:
        raise StageNotExportable(
            f"stage {fqn}: no STORAGE_INTEGRATION; v1 refuses to export "
            "stages with embedded credentials"
        )

    return (
        f"CREATE OR REPLACE STAGE {fqn}\n"
        f"  URL = '{url}'\n"
        f"  STORAGE_INTEGRATION = {integration}\n"
        ";"
    )


def _unwrap_url(raw: str) -> str:
    """DESC STAGE encodes URL as a JSON array string: '["s3://..."]'.

    Be lenient: if it parses as a list with one string, use that. Otherwise
    treat the raw value as the URL (works for the rare scalar case).
    """
    if not raw:
        return ""
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        return raw
    if isinstance(parsed, list) and parsed and isinstance(parsed[0], str):
        return parsed[0]
    if isinstance(parsed, str):
        return parsed
    return raw
```

- [ ] **Step 4: Run synthesizer tests — expect pass**

Run: `uv run pytest tests/test_objects/test_stage_ddl.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dcmexporter/objects/_stage_ddl.py tests/test_objects/test_stage_ddl.py
git commit -m "feat(stage): pure synthesizer for CREATE STAGE from DESC STAGE rows"
```

---

## Task 8: Wire the stage synthesizer into StagePlugin.get_ddl

**Files:**
- Modify: `src/dcmexporter/objects/stage.py`
- Modify: `tests/test_objects/test_stage.py`

- [ ] **Step 1: Update test_stage.py to assert DESC STAGE is used**

Replace the `test_get_ddl_calls_get_ddl_function` test in `tests/test_objects/test_stage.py` with:

```python
def test_get_ddl_uses_desc_stage_and_synthesizer() -> None:
    """Stage uses DESC STAGE + synthesizer; GET_DDL('STAGE',...) is unsupported."""
    cursor = MagicMock()
    sql_log: list[str] = []
    cursor.execute.side_effect = lambda sql: sql_log.append(sql)
    cursor.fetchall.return_value = [
        {
            "parent_property": "STAGE_LOCATION",
            "property": "URL",
            "property_value": '["s3://bucket/x/"]',
            "property_type": "String",
            "property_default": "",
        },
        {
            "parent_property": "STAGE_INTEGRATION",
            "property": "STORAGE_INTEGRATION",
            "property_value": "MY_INT",
            "property_type": "String",
            "property_default": "",
        },
    ]
    fqn = FQN("MYDB", "PUBLIC", "S")
    out = plugin.get_ddl(cursor, fqn)
    assert sql_log == ["DESC STAGE MYDB.PUBLIC.S"]
    assert "CREATE OR REPLACE STAGE MYDB.PUBLIC.S" in out
    assert "STORAGE_INTEGRATION = MY_INT" in out
```

Also update the `test_to_define_and_invocation_*` tests in test_stage.py to use the synthesized DDL form as their input:

Find both `test_to_define_and_invocation_macro_mode` and `test_to_define_and_invocation_raw_mode` and update their input `ddl=` argument from the existing `"CREATE OR REPLACE STAGE …"` string to:

```python
ddl = (
    "CREATE OR REPLACE STAGE MYDB.PUBLIC.S\n"
    "  URL = 's3://bucket/x/'\n"
    "  STORAGE_INTEGRATION = MY_INT\n"
    ";"
)
```

(The shape of the post-synthesizer DDL.)

- [ ] **Step 2: Run — expect failure**

Run: `uv run pytest tests/test_objects/test_stage.py -v`
Expected: FAIL — current stage.py uses inherited get_ddl which calls SELECT GET_DDL.

- [ ] **Step 3: Override `get_ddl` in stage.py**

In `src/dcmexporter/objects/stage.py`, add the override:

```python
class StagePlugin(V1ObjectPlugin):
    type_name = "Stage"
    file_slug = "stage"
    SHOW_FORM = "SHOW STAGES"
    GET_DDL_TYPE = "STAGE"  # unused for stages — kept to satisfy V1ObjectPlugin
    SUPPORTS_COMMENT = True
    MACRO_BODY = (
        # ... unchanged
    )

    def get_ddl(self, cursor, fqn):  # type: ignore[override]
        # Snowflake doesn't support GET_DDL('STAGE',...). Read DESC STAGE rows
        # and synthesize a minimal CREATE OR REPLACE STAGE — see _stage_ddl.py
        # for why credentials are deliberately omitted.
        from dcmexporter.objects._stage_ddl import synthesize_stage_ddl

        cursor.execute(f"DESC STAGE {fqn}")
        return synthesize_stage_ddl(fqn, cursor.fetchall())
```

- [ ] **Step 4: Run stage tests — expect pass**

Run: `uv run pytest tests/test_objects/test_stage.py -v`
Expected: all PASS.

- [ ] **Step 5: Run full object suite**

Run: `uv run pytest tests/test_objects/ -v`
Expected: all PASS.

- [ ] **Step 6: Run full suite**

Run: `uv run pytest tests/ -q`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add src/dcmexporter/objects/stage.py tests/test_objects/test_stage.py
git commit -m "fix(stage): use DESC STAGE + synthesizer (GET_DDL unsupported)"
```

---

## Task 9: Manual end-to-end verification against real Snowflake

**Files:** none (verification only — no code changes if all goes well)

This is a verification task, not TDD. The goal is to confirm the six bug categories are fixed against a real Snowflake account. If issues surface, capture them and add fix tasks to the bottom of this plan rather than slipping them silently.

- [ ] **Step 1: Confirm CI is green on this branch**

Run: `uv run ruff format --check src/ tests/ && uv run ruff check src/ tests/ && uv run mypy src/ && uv run pytest tests/ -q`
Expected: all four PASS.

- [ ] **Step 2: Run the export against the real EXPERIMENTATION database**

Run: `uv run dcmexporter export --database EXPERIMENTATION --out-folder out --force 2>&1 | tail -50`

Expected (dramatic improvement from the pre-fix run):
- No `Unsupported statement type 'Cannot show objects of type DATABASE in DATABASE'` errors.
- No `EXPERIMENTATION.N.<schema>` mis-indexed FQNs.
- No `Schema 'EXPERIMENTATION.EXPERIMENTATION' does not exist` errors (no INFORMATION_SCHEMA pollution).
- No `result set size exceeded the max number of rows(10000)` for tables.
- No `Invalid object type: 'STAGE'` errors (stages emit DDL, or are skipped with `StageNotExportable` if they lack a storage integration).
- Final summary: `[dcmexporter] exported=N errors=M` where M is small (only legitimate access/permission issues, not the bug classes above).

- [ ] **Step 3: Verify the generated layout looks right**

Run: `find out -type f | head -20 && echo "---" && head -30 out/sources/definitions/stage.sql`
Expected:
- `out/manifest.yml`, `out/Makefile` exist.
- `out/sources/definitions/<type>.sql` exist for each type with at least one exported object.
- `out/sources/macros/<type>.sql` likewise.
- The stage.sql file contains synthesized `CREATE OR REPLACE STAGE …` blocks with `URL = '…'` and `STORAGE_INTEGRATION = …` lines and **no** `AWS_ROLE`, `AWS_KEY_ID`, or `AWS_EXTERNAL_ID` strings.

- [ ] **Step 4: Spot-check stage credential leak**

Run: `grep -E '(AWS_ROLE|AWS_EXTERNAL_ID|AWS_KEY_ID|SNOWFLAKE_IAM_USER)' out/sources/definitions/stage.sql`
Expected: no matches. If any line matches, that's a security regression — stop and investigate before merging.

- [ ] **Step 5: Capture the residual error count and decide**

If `errors=0` or errors are only legitimate (e.g. unrelated permission denials on specific objects): proceed.
If new bug classes appear: don't merge. Add a Task 10+ to this plan describing the new bug, then implement the fix.

- [ ] **Step 6: Clean up the probe script (if it was committed)**

Run: `git ls-files probe_snowflake.py`
If it shows the file is tracked: `git rm probe_snowflake.py && git commit -m "chore: remove one-off probe script"`. Otherwise just `rm probe_snowflake.py`.

- [ ] **Step 7: Final commit (only if any minor cleanup is needed)**

If the verification surfaced no code changes, no commit needed for this task. Push the branch and open the PR.

```bash
rtk proxy git push -u origin fix/real-snowflake-discovery
gh pr create --base main --head fix/real-snowflake-discovery --title "Fix real Snowflake discovery bugs" --body "$(cat <<'EOF'
## Summary

Fixes six bug classes that surfaced when running `dcmexporter export` against a real Snowflake account (see plan: `docs/superpowers/plans/2026-05-23-real-snowflake-discovery-fixes.md`):

1. `SHOW DATABASES IN DATABASE X` → `SHOW DATABASES LIKE '<db>'`
2. Tuple/dict row parsing → DictCursor everywhere; dict-only `_rows_to_fqns`
3. `SHOW TABLES IN DATABASE` 10K-row cap → schema-iteration discovery
4. `GET_DDL('STAGE', …)` unsupported → DESC STAGE + pure synthesizer (URL + STORAGE_INTEGRATION; credentials excluded)
5. INFORMATION_SCHEMA pollution → excluded in base discover
6. `SHOW SCHEMAS IN SCHEMA` invalid → `SHOW SCHEMAS LIKE 'X' IN DATABASE Y`

The previous unit tests fed idealized mock rows; they passed but didn't reflect Snowflake's real shape. Tests have been rewritten with realistic `DictCursor`-shaped fixtures.

## Test plan

- [x] All unit tests pass (ruff/mypy clean)
- [x] End-to-end run against a real database with 80K+ tables produces a valid DCM project layout with no bug-class errors
- [x] No AWS credentials leak into synthesized stage DDL (verified by grep)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-Review

**1. Spec coverage:**
- Bug #1 (Database discover) → Task 4 ✓
- Bug #2 (Tuple vs dict, mis-indexed schema_name) → Tasks 1+2 ✓
- Bug #3 (View row index off by one — same root cause as #2) → Tasks 1+2 ✓
- Bug #4 (Tables 10K cap) → Task 3 ✓
- Bug #5 (Stage GET_DDL unsupported) → Tasks 7+8 ✓
- Bug #6 (`--schema` filter syntax) → Task 5 ✓
- INFORMATION_SCHEMA pollution → Task 3 ✓
- Stage credential safety → Task 7 (synthesizer rejects integration-less stages) ✓
- Verification → Task 9 ✓

**2. Placeholder scan:** No "TBD"s, no "implement later"s, every code step shows the actual code. The probe-script cleanup step (9.6) is conditional but the action is concrete.

**3. Type consistency:**
- `synthesize_stage_ddl(fqn, desc_rows)` — same signature in test and impl ✓
- `StageNotExportable` — same class name ✓
- `_target_schemas` — defined in Task 3, used by Task 3's discover only ✓
- `_DictCursorConnection` — defined and used only in Task 1 ✓
- Test plugin name `_MinimalPlugin` — defined once in test_base_helpers.py and reused across Tasks 2 and 3 ✓

Plan saved.
