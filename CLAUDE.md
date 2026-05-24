# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

`dcmassist` is a CLI that exports Snowflake object definitions (tables, views, schemas, stages, …) into the on-disk layout expected by a Snowflake DCM (Declarative Change Management) project: `manifest.yml`, `Makefile`, `sources/definitions/<type>.sql`, and optionally `sources/macros/<type>.sql`.

The exported DDL is committed to a DCM project (i.e. git). Stage DDL is synthesized from `DESC STAGE` and **must never include AWS credentials** — credentials belong to the storage integration, not the stage.

## Commands

The project uses `uv` for everything; do not invoke `pip` or `python` directly.

| Task | Command |
|------|---------|
| Run the CLI | `uv run dcmassist export --database <DB> [--force]` |
| Run all tests | `uv run pytest` |
| Run one file | `uv run pytest tests/test_orchestrator.py -v` |
| Run one test | `uv run pytest tests/test_orchestrator.py::test_export_writes_full_layout -v` |
| Lint | `uv run ruff check src tests` |
| Format check | `uv run ruff format --check src tests` |
| Auto-fix | `uv run ruff check --fix src tests && uv run ruff format src tests` |
| Type check | `uv run mypy src` |

User-facing CLI flags (`--use-macros/--no-use-macros` (default on), `--include`, `--schema`, `--target`, `--configuration`, `--templating-default`, `--out-folder`, `--force`) are documented in `README.md` § "Quick examples" and defined in `cli.py`. Run `uv run dcmassist export --help` for the full list.

A pre-commit hook runs `ruff format`, `ruff` (with `--fix`), and `mypy src` across the whole tree on every commit. **Never bypass it with `--no-verify`** — if a hook fails, fix the underlying issue. If a refactor breaks a different file's call site, that's a sign two changes need to land in one commit (this has happened before with the orchestrator/render and orchestrator/status pairs).

The hook does NOT run pytest — run it manually before committing.

## Architecture

### Pipeline (orchestrator-driven)

`cli.py` builds a frozen `Config`, then `orchestrator.export(cfg)` runs the entire pipeline:

1. `resolve_objects_per_file()` — read `DCMASSIST_EXPORT_OBJECTS_PER_FILE` BEFORE touching the output folder (a bad value must not blow away the user's directory).
2. `prepare_out_folder()` — refuse non-empty unless `--force`; clear and recreate.
3. Open `RunLog` at `<out>/dcmassist-export.log` and dump every Config field so users see (and discover) available options.
4. Inside a `StatusDashboard` (Rich `Live` panel), connect to Snowflake and iterate `filter_types(cfg)`.
5. For each type, dispatch to its plugin: `discover()` → per-FQN `get_ddl()` → `to_define_and_invocation()`.
6. Chunk per-type blocks via `chunk_blocks()` into `dict[filename, body]` keyed by FULL filename (`table.sql`, `table2.sql`, …). The first chunk keeps the unsuffixed name so small exports look identical to before chunking existed.
7. `write_outputs()` writes the dict to disk. It is mechanical — naming logic lives in the orchestrator; macros are still keyed by slug.

Definitions chunk into `<slug>.sql`, `<slug>2.sql`, … past the threshold; macros stay one-per-type at `<slug>.sql`. Chunking exists for diff readability of large DDL files; macro files are short by construction and don't need it.

Exit codes: `0` ok, `4` exported nothing but had errors, `5` config/setup error (bad env var or non-empty out folder).

### Plugin system (`src/dcmassist/objects/`)

Plugins are auto-discovered: `objects/__init__.py:build_registry()` imports every non-underscore module and calls `registry.register(module.plugin)`. `_unimplemented.py` is a special case that registers a list of stub plugins for types DCM supports but dcmassist doesn't yet handle.

To add a new v1 type: create `objects/<type>.py`, subclass `V1ObjectPlugin` from `_base.py`, set `type_name`, `file_slug`, `SHOW_FORM`, `GET_DDL_TYPE`, `MACRO_BODY`, instantiate as module-level `plugin`. Add the canonical name to `V1_TYPES` in `types.py`.

`V1ObjectPlugin` (`objects/_base.py`) implements the standard recipe: schema-iterated `SHOW` discovery, `GET_DDL(<TYPE>, <quoted_fqn>, TRUE)`, and a rewrite chain (`create_to_define` → `inject_comment_if_missing` → `parameterise_database`). Override only what's special. `Schema` and `Stage` synthesize their DDL directly from `SHOW`/`DESC STAGE` rows (see `_schema_ddl.py`, `_stage_ddl.py`) because `GET_DDL` either hangs (recursive Schema) or is unsupported (Stage).

### Snowflake quirks worth knowing

- `SHOW … IN DATABASE` is capped at 10K rows. Use `paginated_show()` from `objects/_show_paging.py`, which appends `LIMIT N FROM '<last_name>'`.
- The cursor is forced to `DictCursor` in `connection.py`; `_rows_to_fqns` rejects non-dict rows defensively.
- Identifiers must be quoted in `GET_DDL`/`DESC STAGE` (see `FQN.quoted` in `types.py`) — leading-digit and lowercase names break otherwise.
- `GET_DDL(..., TRUE)` returns fully-qualified names; `parameterise_database` then rewrites the literal database to `{{ database }}` so the same export can be run against multiple environments.
- The error string `002003 / "does not exist or not authorized"` is treated as a non-fatal `skipped_missing` count — common in shared databases where the role lacks privileges on a few objects.
- `Database` is intentionally NOT in `V1_TYPES` — DCM rejects `DEFINE DATABASE` for the project's parent database. The Makefile prints an analogous warning for the parent schema (which the exporter can't auto-detect).

### Status & logging split

- `StatusDashboard` (`status.py`) — Rich `Live` panel on stderr, transient (disappears at end). Silent on non-TTY, `NO_COLOR=1`, or `DCMASSIST_NO_STATUS=1`. `.log()` writes above the panel; falls back to plain stderr when disabled so warnings still surface in CI.
- `RunLog` (`log.py`) — per-run timestamped log file at `<out-folder>/dcmassist-export.log`. Truncated on each run. This is what users tail when something goes wrong.

The dashboard answers "what's happening right now"; the log answers "what happened to which object and why".

### Testing patterns

- Orchestrator-level tests mock the Snowflake cursor end-to-end via the `_cfg()` / `execute_side_effect` pattern in `tests/test_orchestrator.py` — reuse it rather than reinventing.
- Plugin tests (`tests/test_objects/test_*.py`) exercise discovery and rewrite chains in isolation, with no cursor where avoidable.
- `tmp_path` is fine for output-folder fixtures. New env vars should have a test that sets them via `monkeypatch.setenv` covering both the success path and an invalid value.

### Repo housekeeping

- `out/` at the repo root is gitignored scratch space from local runs — ignore stray artifacts there.

## Conventions

- Default to no comments. Add one only when the **why** is non-obvious (a Snowflake quirk, a hidden invariant, a workaround for a specific error). Don't comment what well-named code already shows.
- Module docstrings should explain why the module exists, not list its contents.
- Don't add backwards-compatibility shims, dead defensive code, or feature flags for hypothetical futures. The codebase is pre-1.0 and prefers clean breaks over migration scaffolding.
- Plans and specs live under `docs/superpowers/plans/` and `docs/superpowers/specs/` and are written via the `superpowers:writing-plans` and `superpowers:brainstorming` skills.
- The tool was renamed from `dcmexporter` → `dcmassist`. Older plans/specs under `docs/superpowers/` still use the old name (they're snapshots) — don't update them retroactively.
- Whenever the version in `pyproject.toml` is bumped, update the pinned `uvx dcmassist@X.Y.Z` example in `README.md` to match the most recently published version. CI stamps the published version as `<pyproject-version>.<run_number>`, so the README pin should be refreshed after the resulting workflow_dispatch publishes.
