# Contributing to dcmassist

Thanks for your interest in contributing. This document covers everything you need to make a clean, mergeable change.

## Setup

Requires Python ≥ 3.10 and [`uv`](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/jamiekt/dcmassist
cd dcmassist
uv sync                         # installs runtime + dev deps + the package itself, editable
uv run pre-commit install       # wires the pre-commit hook
```

`uv` is the only supported tool — please don't introduce `pip`, `python -m venv`, or `poetry` into the workflow.

## Common commands

| Task | Command |
|------|---------|
| Run the CLI | `uv run dcmassist export --database <DB>` |
| Run all tests | `uv run pytest` |
| Run one file | `uv run pytest tests/test_orchestrator.py -v` |
| Run one test | `uv run pytest tests/test_orchestrator.py::test_export_writes_full_layout -v` |
| Lint | `uv run ruff check src tests` |
| Format check | `uv run ruff format --check src tests` |
| Auto-fix | `uv run ruff check --fix src tests && uv run ruff format src tests` |
| Type check | `uv run mypy src` |

## Pre-commit hook

The pre-commit hook runs `ruff format`, `ruff --fix`, and `mypy src` across the whole tree on every commit.

- **Never bypass it with `--no-verify`.** If the hook fails, fix the underlying issue.
- The hook does **not** run pytest. Run `uv run pytest` manually before pushing.
- If a refactor breaks a different file's call site, that's a sign two changes need to land in one commit.

## Workflow

1. Open an issue describing what you want to change (skip for small fixes).
2. Branch from `main`.
3. TDD where it makes sense — write the test, watch it fail, write the code, watch it pass.
4. Keep commits focused. Frequent small commits beat one giant one.
5. Run the full test suite (`uv run pytest`) before pushing.
6. Open a PR. Reference any related issue.

## Code conventions

These are enforced by review (and partly by tooling):

- **Default to no comments.** Add one only when the *why* is non-obvious — a Snowflake quirk, a hidden invariant, a workaround for a specific error. Don't comment what well-named code already shows.
- **Module docstrings explain why the module exists**, not what it contains.
- **No backwards-compatibility shims, dead defensive code, or feature flags for hypothetical futures.** The codebase is pre-1.0 and prefers clean breaks over migration scaffolding.
- **No mocking the database in tests that exercise the orchestrator end-to-end.** Use the cursor-mocking pattern in `tests/test_orchestrator.py`.
- **Quote Snowflake identifiers** in any DDL you generate — leading-digit and lowercase names break otherwise.
- **Never include credentials in synthesized DDL**, especially stage DDL. Credentials belong on storage integrations.

## Architecture overview

### Pipeline

`cli.py` builds a frozen `Config`, then `orchestrator.export(cfg)` runs the entire pipeline:

1. `resolve_objects_per_file()` — read `DCMASSIST_EXPORT_OBJECTS_PER_FILE` *before* touching the output folder (a bad value must not blow away the user's directory).
2. `prepare_out_folder()` — refuse non-empty unless `--force`; clear and recreate.
3. Open `RunLog` at `<out>/dcmassist.log` and dump every Config field so users see (and discover) available options.
4. Inside a `StatusDashboard` (Rich `Live` panel), connect to Snowflake and iterate `filter_types(cfg)`.
5. For each type, dispatch to its plugin: `discover()` → per-FQN `get_ddl()` → `to_define_and_invocation()`.
6. Chunk per-type blocks via `chunk_blocks()` into `dict[filename, body]` keyed by full filename (`table.sql`, `table2.sql`, …). The first chunk keeps the unsuffixed name so small exports look identical to before chunking existed.
7. `write_outputs()` writes the dict to disk. It is mechanical — naming logic lives in the orchestrator.

Exit codes: `0` ok, `4` exported nothing but had errors, `5` config/setup error.

### Plugin system

Plugins live in `src/dcmassist/objects/` and are auto-discovered: `objects/__init__.py:build_registry()` imports every non-underscore module and calls `registry.register(module.plugin)`.

To add a new v1 type:

1. Create `src/dcmassist/objects/<type>.py`.
2. Subclass `V1ObjectPlugin` from `_base.py`.
3. Set `type_name`, `file_slug`, `SHOW_FORM`, `GET_DDL_TYPE`, `MACRO_BODY`.
4. Instantiate as a module-level `plugin`.
5. Add the canonical name to `V1_TYPES` in `types.py`.
6. Write tests in `tests/test_objects/test_<type>.py`.

`V1ObjectPlugin` implements the standard recipe: schema-iterated `SHOW` discovery, `GET_DDL(<TYPE>, <quoted_fqn>, TRUE)`, and a rewrite chain (`create_to_define` → `inject_comment_if_missing` → `parameterise_database`). Override only what's special.

`Schema` and `Stage` synthesize their DDL directly from `SHOW`/`DESC STAGE` rows because `GET_DDL` either hangs (recursive Schema) or is unsupported (Stage).

### Snowflake quirks

- `SHOW … IN DATABASE` is capped at 10K rows. Use `paginated_show()` from `objects/_show_paging.py`, which appends `LIMIT N FROM '<last_name>'`.
- The cursor is forced to `DictCursor` in `connection.py`; `_rows_to_fqns` rejects non-dict rows defensively.
- Identifiers must be quoted in `GET_DDL`/`DESC STAGE` (see `FQN.quoted` in `types.py`).
- `GET_DDL(..., TRUE)` returns fully-qualified names; `parameterise_database` rewrites the literal database to `{{ database }}`.
- The error string `002003 / "does not exist or not authorized"` is treated as a non-fatal `skipped_missing` — common in shared databases where the role lacks privileges on a few objects.
- `Database` is intentionally NOT in `V1_TYPES` — DCM rejects `DEFINE DATABASE` for the project's parent database.

### Status & logging split

- **`StatusDashboard`** (`status.py`) — Rich `Live` panel on stderr, transient. Silent on non-TTY, `NO_COLOR=1`, or `DCMASSIST_NO_STATUS=1`. `.log()` writes above the panel; falls back to plain stderr when disabled so warnings still surface in CI.
- **`RunLog`** (`log.py`) — per-run timestamped log file at `<out>/dcmassist.log`. Truncated on each run. This is what users tail when something goes wrong.

The dashboard answers "what's happening right now"; the log answers "what happened to which object and why".

## Testing notes

- Tests in `tests/test_orchestrator.py` mock the Snowflake cursor end-to-end via the pattern in `_cfg()` and `execute_side_effect`. Reuse that pattern for new orchestrator-level tests.
- Plugin-level tests (`tests/test_objects/test_*.py`) test discovery and rewrite chains in isolation, with no cursor at all where possible.
- `tmp_path` from pytest is fine for output-folder fixtures.
- If you're adding a new env var, write a test that sets it via `monkeypatch.setenv` and confirm both the success path and an invalid value.

## Plans and specs

Larger features start with a spec in `docs/superpowers/specs/` and a plan in `docs/superpowers/plans/`, written via the [superpowers](https://github.com/anthropics/superpowers) `brainstorming` and `writing-plans` skills. You don't need superpowers to contribute — short PRs can skip the doc — but for anything non-trivial please open an issue or draft PR first so the design can be discussed before code lands.

## Reporting bugs

Open an issue at [github.com/jamiekt/dcmassist/issues](https://github.com/jamiekt/dcmassist/issues) with:

- The command you ran.
- The relevant section of `dcmassist.log`.
- Snowflake account region (if reproducible only on certain regions).
- Whether the same export works against a different database / role.

Don't paste DDL that contains real customer data or credentials.

## License

By contributing, you agree your contributions will be licensed under the project's MIT license.
