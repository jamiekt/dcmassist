# dcmexporter — design spec

**Date:** 2026-05-23
**Status:** Approved (pending user review of spec doc)

## 1. Purpose

A Python CLI, `dcmexporter`, that connects to a Snowflake database, exports definitions of supported objects in a form suitable for a Snowflake Declarative Change Management (DCM) project, and writes a complete DCM project layout (`manifest.yml`, a `Makefile`, per-type `DEFINE` files, and per-type Jinja macros) to a chosen output folder. Distributed via PyPI. Tooling and CI mirror the [awstui](https://github.com/jamiekt/awstui/) project.

The Snowflake DCM supported-entities list (https://docs.snowflake.com/en/user-guide/dcm-projects/dcm-projects-supported-entities) is the canonical source of truth for the set of types this tool can handle.

## 2. CLI surface

Single command: `dcmexporter export …`.

| Flag | Repeatable | Default | Notes |
|---|---|---|---|
| `--database NAME` | no | required | Snowflake database to export from. |
| `--schema NAME` | yes | none (= all schemas) | Restrict to specific schemas within the database. |
| `--connection NAME` | no | snow CLI default | Named connection from `~/.snowflake/config.toml` / `connections.toml`. Honours `SNOWFLAKE_DEFAULT_CONNECTION_NAME`. |
| `--target NAME` | yes | `start` | Each value becomes a target in `manifest.yml`. If at least one is given, the `start` target is *not* generated. The default target is the first `--target` (or `start` when none). |
| `--templating-default key=value` | yes | none | Each becomes a key under `templating.defaults`. The `value` is `json.loads`-parsed and emitted as YAML if parsing succeeds; otherwise emitted as a string. The key `database` is reserved (rejected with a usage error). |
| `--configuration NAME` | yes | none | Each becomes a key under `templating.configurations`. NAME must be a single word. |
| `--templating-configuration-key KEY` | yes | none | Each becomes a key inside *every* configuration. Values are emitted as empty strings. The CLI prints a banner reminding the caller to fill values in `manifest.yml`. Specifying this flag without any `--configuration` is a usage error. The key `database` is reserved (rejected with a usage error). |
| `--include TYPE` | yes | none (= all supported) | Restrict export to specific DCM object types. Validated against the canonical list. |
| `--exclude TYPE` | yes | none | Skip specific DCM object types. Validated against the canonical list. |
| `--comment STRING` | no | `Definition exported by https://github.com/jamiekt/dcmexporter on YYYY-MM-DD` | Injected as `COMMENT='…'` into the DDL of every object whose type supports comments, *only if* the existing DDL has no `COMMENT` clause. May be empty (`--comment ''`) — an empty literal is still injected when missing. |
| `--use-macros / --no-use-macros` | no | `--use-macros` (true) | When true, emit a per-type macro file under `out/sources/macros/` and rewrite each definition to invoke that macro. When false, emit raw `DEFINE` statements only. |
| `--out-folder PATH` | no | `out` (cwd) | Destination directory. If non-empty, refuse unless `--force` is given. |
| `--force` | no | false | Overwrite a non-empty `--out-folder`. |

Validation rules:

- `--include` / `--exclude` values are normalised case-insensitively and matched against the canonical DCM-supported-types list. Unknown values fail with a `BadParameter` listing the offending value.
- An `--include` value that names a *known but not-yet-implemented* type fails up-front (see §5 v1 scope).
- `--templating-default` must be in `key=value` shape; `key` must be a non-empty identifier-shaped string and must not be `database`.
- `--templating-configuration-key` without any `--configuration` fails up-front. The key must not be `database`.

## 3. Architecture

Five layers, each independently testable:

1. **CLI** (`src/dcmexporter/cli.py`) — Click. Parses args, validates, builds a frozen `Config` dataclass, hands it to the orchestrator. Owns no I/O.
2. **Connection** (`src/dcmexporter/connection.py`) — Thin wrapper around `snowflake-connector-python`. Reads snow-CLI config files, supports `SNOWFLAKE_DEFAULT_CONNECTION_NAME`, returns a connected cursor.
3. **Object plugins** (`src/dcmexporter/objects/`) — One module per supported type, each registering a module-level `plugin: ObjectPlugin`. Auto-discovered by `objects/__init__.py` (mirrors awstui's `services/__init__.py`).
4. **Rewriter** (`src/dcmexporter/rewrite.py`) — Pure-functional helpers operating on sqlglot ASTs: `create_to_define`, `inject_comment_if_missing`, `to_macro_invocation`, `extract_kwargs_for_macro`, `parameterise_database` (replaces every reference to the exported database with `{{ database }}`).
5. **Renderers** — `src/dcmexporter/manifest.py`, `src/dcmexporter/makefile.py`, `src/dcmexporter/render.py`. Take the orchestrator's results plus `Config` and write files into `--out-folder`.

`src/dcmexporter/orchestrator.py` ties the layers together; tested in isolation against a mocked cursor.

### 3.1 Plugin interface

```python
class ObjectPlugin(ABC):
    type_name: str   # e.g. "Table", "File format" — verbatim from DCM docs
    file_slug: str   # e.g. "table", "file_format" — used for filenames

    @abstractmethod
    def discover(self, cursor, database: str, schemas: list[str] | None) -> list[FQN]: ...

    @abstractmethod
    def get_ddl(self, cursor, fqn: FQN) -> str: ...

    @abstractmethod
    def to_define_and_invocation(
        self, ddl: str, *, comment: str | None, use_macros: bool, database: str
    ) -> str:
        """Returns the SQL block to write into definitions/<file_slug>.sql for this object.
        References to `database` are replaced with the {{ database }} Jinja placeholder."""

    @abstractmethod
    def macro_definition(self) -> str:
        """Returns the {% macro define_<file_slug>(...) %}…{% endmacro %} body."""
```

`SUPPORTED_TYPES` (in `src/dcmexporter/types.py`) is the single source of truth for the canonical list. Unimplemented types are present in the list but their plugin module raises `NotImplementedError` from `discover`.

## 4. Output layout

```
<out-folder>/
  manifest.yml
  Makefile
  sources/
    definitions/
      database.sql
      schema.sql
      table.sql
      view.sql
      sequence.sql
      stage.sql
      file_format.sql
      tag.sql
      warehouse.sql
    macros/             # only when --use-macros (default true)
      database.sql
      schema.sql
      …
```

Filenames use `file_slug` (lowercase, spaces replaced with underscores). One file per object type — all objects of the same type are concatenated into a single file in deterministic order (database, schema, name).

### 4.1 `manifest.yml` shape

When at least one `--configuration` is given:

```yaml
manifest_version: 2
type: DCM_PROJECT

# Generated by dcmexporter on YYYY-MM-DD.
# Review the project_owner field below — it is left blank intentionally.

targets:
  <TARGETNAME>:
    account_identifier: <resolved from snow CLI connection>
    project_name: <DATABASE>.PUBLIC.MAIN
    project_owner: ""
    templating_config: <TARGETNAME>

templating:
  defaults:
    <key>: <value>                   # per --templating-default
  configurations:
    <NAME>:
      # Probably change this — generated from the exported-from database
      database: <DATABASE>
      <key>: ""                      # per --templating-configuration-key
```

When no `--configuration` is given:

```yaml
manifest_version: 2
type: DCM_PROJECT

# Generated by dcmexporter on YYYY-MM-DD.
# Review the project_owner field below — it is left blank intentionally.

targets:
  <TARGETNAME>:
    account_identifier: <resolved from snow CLI connection>
    project_name: <DATABASE>.PUBLIC.MAIN
    project_owner: ""

templating:
  defaults:
    # Probably change this — generated from the exported-from database
    database: <DATABASE>
    <key>: <value>                   # per --templating-default
```

Notes:
- `database` is always emitted under either `templating.configurations.<NAME>` (per configuration, when at least one `--configuration` is given) or `templating.defaults` (when no `--configuration` is given). It is never emitted in both places.
- The "Probably change this" comment is rendered literally in the YAML file directly above the `database:` line.
- Values from `--templating-default key=value` are JSON-parsed; if parsing succeeds they are emitted as the resulting YAML structure (mapping/list/number/bool/null), otherwise as a YAML string.
- `targets` keys preserve the order the user supplied them; `start` is used only when no `--target` was given.
- `templating_config: <TARGETNAME>` appears in each target only when at least one `--configuration` was given.
- `account_identifier` is resolved from the snow-CLI connection's `account` field. If unavailable, the field is emitted as `""` and a warning is printed.
- The order of top-level keys is fixed: `manifest_version`, `type`, `targets`, `templating`.

### 4.2 `Makefile` shape

```make
.PHONY: plan apply

TARGET ?= <DEFAULT>

plan:
	snow dcm plan --from . --target $(TARGET)

apply:
	snow dcm execute --from . --target $(TARGET)
```

`<DEFAULT>` is `start` when no `--target` was given; otherwise the first `--target` value. Implementation note: verify the exact `snow dcm` apply subcommand name during implementation (`execute` vs `apply`) and adjust.

### 4.3 Definitions and macros

When `--use-macros` is true (default):

- `out/sources/macros/<file_slug>.sql` contains a single Jinja macro definition, e.g. `{% macro define_table(database, schema, name, columns, cluster_by=None, data_retention_days=None, comment=None, tags=None, …) %}…{% endmacro %}`. Macros are *highly configurable*: every option that the corresponding DCM `DEFINE <TYPE>` form supports is exposed as a named parameter, defaulting to `None`/empty.
- `out/sources/definitions/<file_slug>.sql` contains one `{{ define_<file_slug>(database='{{ database }}', …) }}` invocation per discovered object, with kwargs extracted from the AST.
- The macros + invocations rely on Snowflake DCM's native server-side Jinja templating — no local pre-rendering step is needed.

When `--use-macros` is false:
- `out/sources/macros/` is not created.
- `out/sources/definitions/<file_slug>.sql` contains raw `DEFINE …` statements (the `CREATE` verb in `GET_DDL` output rewritten to `DEFINE`, with `--comment` injected where needed).

### 4.4 Database parameterisation

In *all* generated definitions and macro invocations, every reference to the exported database name (i.e. the value of `--database`) is replaced with the Jinja placeholder `{{ database }}`. This applies to:

- the database qualifier in object FQNs in `DEFINE` statements (e.g. `DEFINE TABLE MYDB.PUBLIC.FOO` → `DEFINE TABLE {{ database }}.PUBLIC.FOO`);
- macro-invocation `database` kwargs (e.g. `database='{{ database }}'`);
- references to the same database elsewhere in the DDL body (e.g. `LIKE <DB>.S.T` in stage definitions, function bodies that reference the database by name).

The substitution is whole-identifier / boundary-aware — it must not replace the database name when it appears as a substring inside an unrelated identifier. Implementation lives in `rewrite.parameterise_database` and runs as the final rewriter step (after comment injection and macro-invocation generation).

The `{{ database }}` value is resolved at `snow dcm plan` time from `templating.configurations.<NAME>.database` (when configurations are defined) or from `templating.defaults.database` (when not).

## 5. v1 scope

Object plugins implemented end-to-end (discovery + DEFINE + macro + invocation) in v1:

- Database
- Schema
- Table
- View (incl. secure views)
- Sequence
- Stage (internal + external)
- File format
- Tag
- Warehouse

Listed in `SUPPORTED_TYPES` for `--include`/`--exclude` validation but not implemented in v1 (raise `NotImplementedError` from their plugin's `discover`):

- Dynamic table
- Task
- Alert
- SQL function, Data metric function
- SQL procedure
- Role, Database role
- Grant
- Authentication policy

Behaviour when an unimplemented type is in scope:
- If the user asked for it via `--include`, fail up-front with a clear "not yet supported" error (exit code 2).
- If the user did not pass `--include` (i.e. "all"), the type is silently skipped with a single stderr note per type.

## 6. Error handling

| Boundary | Behaviour | Exit code |
|---|---|---|
| CLI validation (bad `--include`/`--exclude`, malformed `--templating-default`, `--templating-configuration-key` without `--configuration`, `--templating-default database=…`, `--templating-configuration-key database`, etc.) | Click `BadParameter` / `UsageError` | 2 |
| Connection failure (no snow config, named connection missing, auth failure) | Re-raise as `ConnectionError` with a one-line message naming the connection and config file tried | 3 |
| Per-object `GET_DDL` failure (e.g. permissions on a single object) | Log warning to stderr, continue. Final summary line `N exported, M skipped`. | 0 if anything exported, 4 if zero exported and any errors occurred |
| `--include` names a known-but-unimplemented type | Fail up-front with "not yet supported" message | 2 |
| `--out-folder` exists and is non-empty without `--force` | Refuse with clear message | 5 |
| Renderer / file-write `OSError` | Propagate; Click prints traceback | non-zero |

No retries, no auto-recovery, no partial-state cleanup beyond what the OS provides.

## 7. Testing

All tests are offline; CI requires no Snowflake credentials.

```
tests/
  conftest.py                  # shared fixtures: mock cursor, sample DDL, tmp out folder
  fixtures/
    ddl/
      table_basic.sql
      table_with_cluster_by.sql
      view_secure.sql
      …
  test_cli.py
  test_connection.py
  test_manifest.py
  test_makefile.py
  test_rewrite.py
  test_render.py
  test_objects/
    test_database.py
    test_schema.py
    test_table.py
    test_view.py
    test_sequence.py
    test_stage.py
    test_file_format.py
    test_tag.py
    test_warehouse.py
  test_orchestrator.py         # end-to-end against mocked cursor; golden directory comparison
```

`mock_cursor` fixture wraps `MagicMock`; tests configure `cursor.execute().fetchall()` / `fetchone()` to return canned rows or DDL strings. Each plugin asserts: discovery SQL is correct, `GET_DDL` call shape is correct, produced DEFINE/macro-invocation matches a snapshot, macro definition parses as valid Jinja (`jinja2.Environment().parse(...)`).

CLI tests cover every flag-combination edge case in §2: empty `--comment ''`, multiple `--target`, no `--target`, invalid `--include`, invalid `--exclude`, JSON vs string `--templating-default`, `--templating-configuration-key` without `--configuration`, `--templating-configuration-key` with multiple `--configuration`, `--templating-default database=…` and `--templating-configuration-key database` (both rejected).

`test_manifest.py` covers both manifest shapes from §4.1: with and without configurations, asserting the `database` key lands in the right block with the "Probably change this" comment above it.

`test_rewrite.py` covers `parameterise_database`: simple FQN replacement, occurrences in DDL bodies, and the boundary-awareness case where the database name is a substring of another identifier.

The orchestrator test is the integration-style golden test: a fully mocked cursor + full v1 Config + checked-in golden `out/` directory.

## 8. Tooling, packaging, CI

Mirrors awstui:

- `uv` for env management. `uv.lock` checked in.
- `pyproject.toml` only — no `pytest.ini`, no `ruff.toml`. Hatchling build backend.
- `[project.scripts] dcmexporter = "dcmexporter.__main__:main"`.
- Pre-commit: `ruff format`, `ruff check --fix`, `mypy src/`, all via `uv run`.
- Dependencies: `click`, `snowflake-connector-python`, `pyyaml`, `sqlglot`, `jinja2`.
- Dev dependencies: `mypy`, `pre-commit`, `pytest`, `ruff`.
- Python `>=3.10`.

GitHub Actions (`.github/workflows/ci.yml`) — copied structure from awstui:

- **test** job: matrix `os: [ubuntu-latest, macos-latest, windows-latest]` × `python-version: ["3.10", "3.11", "3.12", "3.13", "3.14"]`. Runs `ruff format --check`, `ruff check`, `pytest tests/ -v`.
- **build** job (depends on test): version-stamps `pyproject.toml` (`MAJOR.MINOR` + `${{ github.run_number }}`), runs `uv build`, uploads `dist/`.
- **publish** job (depends on build, `if: github.event_name == 'workflow_dispatch'`): downloads `dist/`, uses `pypa/gh-action-pypi-publish`. Trusted publishing via `id-token: write`.
- **release** job (depends on build + publish, `if: github.event_name == 'workflow_dispatch'`): creates GitHub release `vX.Y.Z` with the PyPI link, attaches `dist/*`. Optional `release_notes` input prepended to the release body.

## 9. Dependencies / risks

- **`snow dcm` Jinja capability**: The macro+invocation approach assumes Snowflake DCM's server-side templating supports `{% macro %}` definitions in macros files plus `{{ invocation(...) }}` from definitions files, and that `{{ database }}` placeholders in definitions resolve from `templating.configurations.<NAME>.database` / `templating.defaults.database`. Verify against current DCM docs during implementation; if support differs (e.g. macros must live inline in the same file as the invocation), adjust the file layout accordingly. Falls back gracefully to `--no-use-macros` if needed.
- **`GET_DDL` coverage gaps**: Not every supported type has a `GET_DDL('<TYPE>', '<fqn>')` form. For each v1 plugin, verify `GET_DDL` produces a complete, round-trippable CREATE statement; document any gaps in the plugin module.
- **`snow dcm` apply subcommand name**: `execute` vs `apply` — confirm during implementation and adjust the Makefile.
- **AST coverage**: sqlglot's Snowflake dialect must round-trip every CREATE statement v1 emits. Any unparseable DDL is a test fixture worth adding before the corresponding plugin ships.
- **Database parameterisation false positives**: `parameterise_database` must not replace the database name when it appears inside an unrelated identifier. Use sqlglot AST node walking rather than naive string substitution; cover with a dedicated test.
