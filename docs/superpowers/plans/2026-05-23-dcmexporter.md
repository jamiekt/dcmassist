# dcmexporter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python CLI `dcmexporter` that exports Snowflake object definitions into a complete DCM project layout (`manifest.yml`, `Makefile`, per-type `DEFINE` files, per-type Jinja macros), publishable to PyPI.

**Architecture:** Five-layer Click CLI — CLI → Connection → Object Plugins → Rewriter → Renderers — with a thin orchestrator. Plugins auto-discovered from `src/dcmexporter/objects/`. AST-driven rewriting via sqlglot. All tests are offline against a mocked `snowflake-connector-python` cursor.

**Tech Stack:** Python ≥3.10, uv, click, snowflake-connector-python, pyyaml, sqlglot, jinja2, pytest, ruff, mypy. CI via GitHub Actions matrix (Linux/macOS/Windows × Python 3.10–3.14).

**Spec:** `docs/superpowers/specs/2026-05-23-dcmexporter-design.md`

---

## File Structure

```
src/dcmexporter/
  __init__.py
  __main__.py             # entrypoint for `dcmexporter` script
  cli.py                  # Click command + arg validation
  config.py               # frozen Config dataclass + validation helpers
  types.py                # SUPPORTED_TYPES canonical list, FQN dataclass
  connection.py           # snowflake-connector-python wrapper
  plugin.py               # ObjectPlugin ABC + PluginRegistry
  rewrite.py              # sqlglot-AST rewriter helpers
  manifest.py             # manifest.yml renderer
  makefile.py             # Makefile renderer
  render.py               # output-folder writer (top-level)
  orchestrator.py         # ties layers together
  objects/
    __init__.py           # auto-discovery
    database.py
    schema.py
    table.py
    view.py
    sequence.py
    stage.py
    file_format.py
    tag.py
    warehouse.py
    _unimplemented.py     # plugins for deferred types (raise NotImplementedError)
tests/
  conftest.py
  fixtures/ddl/*.sql
  test_cli.py
  test_config.py
  test_connection.py
  test_manifest.py
  test_makefile.py
  test_rewrite.py
  test_render.py
  test_plugin.py
  test_objects/test_<type>.py
  test_orchestrator.py
  golden/out/...          # full expected output for the orchestrator end-to-end test
.github/workflows/ci.yml
.pre-commit-config.yaml
pyproject.toml
README.md (already exists)
```

---

## Task 1: Project scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `.pre-commit-config.yaml`
- Create: `.python-version`
- Create: `src/dcmexporter/__init__.py`
- Create: `src/dcmexporter/__main__.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Modify: `.gitignore` (already exists; verify uv/.venv/dist coverage)

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[project]
name = "dcmexporter"
version = "0.1"
description = "Export Snowflake object definitions for use in a DCM project"
readme = "README.md"
requires-python = ">=3.10"
license = "MIT"
classifiers = [
    "Development Status :: 3 - Alpha",
    "Environment :: Console",
    "Intended Audience :: Developers",
    "Intended Audience :: System Administrators",
    "Operating System :: OS Independent",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.10",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Programming Language :: Python :: 3.13",
    "Programming Language :: Python :: 3.14",
    "Topic :: Database",
    "Topic :: System :: Systems Administration",
]
dependencies = [
    "click>=8.1",
    "snowflake-connector-python>=3.7",
    "pyyaml>=6.0",
    "sqlglot>=25.0",
    "jinja2>=3.1",
]

[project.urls]
Homepage = "https://github.com/jamiekt/dcmexporter"
Repository = "https://github.com/jamiekt/dcmexporter"
Issues = "https://github.com/jamiekt/dcmexporter/issues"

[project.scripts]
dcmexporter = "dcmexporter.__main__:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.mypy]
python_version = "3.12"

[[tool.mypy.overrides]]
module = ["snowflake.*", "yaml", "sqlglot.*", "jinja2.*"]
ignore_missing_imports = true

[dependency-groups]
dev = [
    "mypy>=1.11",
    "pre-commit>=4.0",
    "pytest>=8.0",
    "ruff>=0.8",
]
```

- [ ] **Step 2: Create `.pre-commit-config.yaml`**

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.15.11
    hooks:
      - id: ruff-format
        args: [src/, tests/]
      - id: ruff
        args: [--fix, src/, tests/]

  - repo: local
    hooks:
      - id: mypy
        name: mypy
        entry: uv run mypy src/
        language: system
        types: [python]
        pass_filenames: false
```

- [ ] **Step 3: Create `.python-version`**

```
3.12
```

- [ ] **Step 4: Create `src/dcmexporter/__init__.py`**

```python
"""dcmexporter — export Snowflake object definitions for DCM projects."""

__version__ = "0.1"
```

- [ ] **Step 5: Create `src/dcmexporter/__main__.py`**

```python
"""Entry point for the dcmexporter CLI."""

from __future__ import annotations

from dcmexporter.cli import cli


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Create `tests/__init__.py`** (empty file)

- [ ] **Step 7: Create `tests/conftest.py`**

```python
"""Shared pytest fixtures for dcmexporter tests."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def mock_cursor() -> MagicMock:
    """A MagicMock standing in for a snowflake-connector cursor."""
    return MagicMock()


@pytest.fixture
def tmp_out_folder(tmp_path: Path) -> Path:
    """A fresh empty directory to use as --out-folder."""
    out = tmp_path / "out"
    out.mkdir()
    return out
```

- [ ] **Step 8: Run `uv sync` and verify env**

Run: `uv sync --all-extras`
Expected: creates `.venv/`, writes `uv.lock`, no errors.

- [ ] **Step 9: Smoke-test the entry point**

Add a temporary `cli.py` stub so the import resolves:

```python
# src/dcmexporter/cli.py
"""CLI entrypoint (stub — replaced in Task 4)."""
from __future__ import annotations

import click


@click.group()
def cli() -> None:
    """dcmexporter."""
```

Run: `uv run dcmexporter --help`
Expected: Click usage banner printed, exit 0.

- [ ] **Step 10: Commit**

```bash
git add pyproject.toml .pre-commit-config.yaml .python-version uv.lock src/ tests/
git commit -m "feat: project scaffolding (pyproject, pre-commit, entry point stub)"
```

---

## Task 2: SUPPORTED_TYPES + FQN

**Files:**
- Create: `src/dcmexporter/types.py`
- Create: `tests/test_types.py`

- [ ] **Step 1: Write the failing test**

`tests/test_types.py`:

```python
"""Tests for SUPPORTED_TYPES canonical list and FQN dataclass."""

from __future__ import annotations

from dcmexporter.types import (
    DCM_TYPES,
    UNIMPLEMENTED_TYPES,
    V1_TYPES,
    FQN,
    normalise_type,
)


def test_dcm_types_includes_v1_and_unimplemented() -> None:
    assert set(V1_TYPES) | set(UNIMPLEMENTED_TYPES) == set(DCM_TYPES)


def test_v1_and_unimplemented_are_disjoint() -> None:
    assert set(V1_TYPES).isdisjoint(set(UNIMPLEMENTED_TYPES))


def test_v1_types_match_spec() -> None:
    assert V1_TYPES == (
        "Database",
        "Schema",
        "Table",
        "View",
        "Sequence",
        "Stage",
        "File format",
        "Tag",
        "Warehouse",
    )


def test_normalise_type_case_insensitive() -> None:
    assert normalise_type("table") == "Table"
    assert normalise_type("FILE FORMAT") == "File format"
    assert normalise_type("File format") == "File format"


def test_normalise_type_unknown_raises() -> None:
    import pytest

    with pytest.raises(ValueError, match="Banana"):
        normalise_type("Banana")


def test_fqn_str_dotted() -> None:
    fqn = FQN(database="MYDB", schema="PUBLIC", name="FOO")
    assert str(fqn) == "MYDB.PUBLIC.FOO"


def test_fqn_str_no_schema() -> None:
    fqn = FQN(database="MYDB", schema=None, name="MYDB")
    assert str(fqn) == "MYDB"
```

- [ ] **Step 2: Run the test, expect failure**

Run: `uv run pytest tests/test_types.py -v`
Expected: ImportError — `dcmexporter.types` does not exist.

- [ ] **Step 3: Implement `src/dcmexporter/types.py`**

```python
"""Canonical Snowflake DCM object types and FQN helper.

The DCM_TYPES tuple mirrors the supported-entities list at:
https://docs.snowflake.com/en/user-guide/dcm-projects/dcm-projects-supported-entities
"""

from __future__ import annotations

from dataclasses import dataclass

V1_TYPES: tuple[str, ...] = (
    "Database",
    "Schema",
    "Table",
    "View",
    "Sequence",
    "Stage",
    "File format",
    "Tag",
    "Warehouse",
)

UNIMPLEMENTED_TYPES: tuple[str, ...] = (
    "Dynamic table",
    "Task",
    "Alert",
    "SQL function",
    "Data metric function",
    "SQL procedure",
    "Role",
    "Database role",
    "Grant",
    "Authentication policy",
)

DCM_TYPES: tuple[str, ...] = V1_TYPES + UNIMPLEMENTED_TYPES


def normalise_type(value: str) -> str:
    """Map a user-supplied type string to its canonical form (case-insensitive)."""
    lower = value.strip().lower()
    for canonical in DCM_TYPES:
        if canonical.lower() == lower:
            return canonical
    raise ValueError(f"Unknown DCM object type: {value!r}")


@dataclass(frozen=True)
class FQN:
    database: str
    schema: str | None
    name: str

    def __str__(self) -> str:
        if self.schema is None:
            return self.name
        return f"{self.database}.{self.schema}.{self.name}"
```

- [ ] **Step 4: Run the tests, expect pass**

Run: `uv run pytest tests/test_types.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add src/dcmexporter/types.py tests/test_types.py
git commit -m "feat(types): SUPPORTED_TYPES list and FQN dataclass"
```

---

## Task 3: Config dataclass + validation

**Files:**
- Create: `src/dcmexporter/config.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_config.py`:

```python
"""Tests for the Config dataclass and parsing helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from dcmexporter.config import (
    Config,
    parse_templating_default,
    resolve_default_target,
    validate_config,
)


def test_parse_templating_default_string() -> None:
    assert parse_templating_default("alliance=unspecified") == ("alliance", "unspecified")


def test_parse_templating_default_json_object() -> None:
    key, value = parse_templating_default('tags={"team":"data"}')
    assert key == "tags"
    assert value == {"team": "data"}


def test_parse_templating_default_json_number() -> None:
    assert parse_templating_default("retention=7") == ("retention", 7)


def test_parse_templating_default_missing_equals_raises() -> None:
    with pytest.raises(ValueError, match="key=value"):
        parse_templating_default("nope")


def test_parse_templating_default_empty_key_raises() -> None:
    with pytest.raises(ValueError, match="empty"):
        parse_templating_default("=foo")


def test_resolve_default_target_no_targets() -> None:
    assert resolve_default_target([]) == ("start", ("start",))


def test_resolve_default_target_with_targets() -> None:
    assert resolve_default_target(["staging", "live"]) == (
        "staging",
        ("staging", "live"),
    )


def _base_config(**overrides) -> Config:
    base = dict(
        database="MYDB",
        schemas=(),
        connection=None,
        targets=("start",),
        default_target="start",
        templating_defaults=(),
        configurations=(),
        templating_configuration_keys=(),
        includes=(),
        excludes=(),
        comment=None,
        use_macros=True,
        out_folder=Path("out"),
        force=False,
    )
    base.update(overrides)
    return Config(**base)


def test_validate_config_rejects_database_in_templating_default() -> None:
    cfg = _base_config(templating_defaults=(("database", "MYDB"),))
    with pytest.raises(ValueError, match="reserved"):
        validate_config(cfg)


def test_validate_config_rejects_database_in_templating_configuration_key() -> None:
    cfg = _base_config(
        configurations=("STAGING",),
        templating_configuration_keys=("database",),
    )
    with pytest.raises(ValueError, match="reserved"):
        validate_config(cfg)


def test_validate_config_rejects_keys_without_configurations() -> None:
    cfg = _base_config(templating_configuration_keys=("environment",))
    with pytest.raises(ValueError, match="--configuration"):
        validate_config(cfg)


def test_validate_config_rejects_unknown_include() -> None:
    cfg = _base_config(includes=("Banana",))
    with pytest.raises(ValueError, match="Banana"):
        validate_config(cfg)


def test_validate_config_rejects_unimplemented_include() -> None:
    cfg = _base_config(includes=("Task",))
    with pytest.raises(ValueError, match="not yet supported"):
        validate_config(cfg)


def test_validate_config_normalises_includes() -> None:
    cfg = _base_config(includes=("table", "VIEW"))
    validated = validate_config(cfg)
    assert validated.includes == ("Table", "View")


def test_validate_config_normalises_excludes() -> None:
    cfg = _base_config(excludes=("warehouse",))
    validated = validate_config(cfg)
    assert validated.excludes == ("Warehouse",)
```

- [ ] **Step 2: Run, expect failure**

Run: `uv run pytest tests/test_config.py -v`
Expected: ImportError — `dcmexporter.config` does not exist.

- [ ] **Step 3: Implement `src/dcmexporter/config.py`**

```python
"""Frozen Config dataclass + CLI value parsing/validation helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from dcmexporter.types import UNIMPLEMENTED_TYPES, V1_TYPES, normalise_type


@dataclass(frozen=True)
class Config:
    database: str
    schemas: tuple[str, ...]
    connection: str | None
    targets: tuple[str, ...]
    default_target: str
    templating_defaults: tuple[tuple[str, Any], ...]
    configurations: tuple[str, ...]
    templating_configuration_keys: tuple[str, ...]
    includes: tuple[str, ...]
    excludes: tuple[str, ...]
    comment: str | None
    use_macros: bool
    out_folder: Path
    force: bool


def parse_templating_default(raw: str) -> tuple[str, Any]:
    """Parse a `key=value` string. value is JSON-parsed if valid, else kept as a string."""
    if "=" not in raw:
        raise ValueError(f"--templating-default must be in key=value form, got: {raw!r}")
    key, _, value = raw.partition("=")
    if not key:
        raise ValueError(f"--templating-default key is empty in: {raw!r}")
    try:
        parsed: Any = json.loads(value)
    except json.JSONDecodeError:
        parsed = value
    return key, parsed


def resolve_default_target(
    user_targets: list[str] | tuple[str, ...],
) -> tuple[str, tuple[str, ...]]:
    """Return (default_target, targets_tuple) given the user-supplied --target list."""
    if not user_targets:
        return "start", ("start",)
    return user_targets[0], tuple(user_targets)


def validate_config(cfg: Config) -> Config:
    """Apply cross-field validation; return a normalised Config or raise ValueError."""
    for key, _ in cfg.templating_defaults:
        if key == "database":
            raise ValueError("'database' is a reserved key for --templating-default")
    for key in cfg.templating_configuration_keys:
        if key == "database":
            raise ValueError(
                "'database' is a reserved key for --templating-configuration-key"
            )
    if cfg.templating_configuration_keys and not cfg.configurations:
        raise ValueError(
            "--templating-configuration-key requires at least one --configuration"
        )

    def _normalise(values: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(normalise_type(v) for v in values)

    includes = _normalise(cfg.includes)
    excludes = _normalise(cfg.excludes)

    for value in includes:
        if value in UNIMPLEMENTED_TYPES:
            raise ValueError(
                f"Type {value!r} is in DCM's supported set but not yet supported "
                "by dcmexporter"
            )

    return replace(cfg, includes=includes, excludes=excludes)


def filter_types(cfg: Config) -> tuple[str, ...]:
    """Resolve the final list of v1 types to export, after include/exclude."""
    if cfg.includes:
        return cfg.includes
    return tuple(t for t in V1_TYPES if t not in cfg.excludes)
```

- [ ] **Step 4: Run, expect pass**

Run: `uv run pytest tests/test_config.py -v`
Expected: 13 passed.

- [ ] **Step 5: Commit**

```bash
git add src/dcmexporter/config.py tests/test_config.py
git commit -m "feat(config): Config dataclass and validation helpers"
```

---

## Task 4: Click CLI wiring

**Files:**
- Modify: `src/dcmexporter/cli.py` (replace Task 1 stub)
- Create: `tests/test_cli.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_cli.py`:

```python
"""Tests for Click CLI argument parsing and validation."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from click.testing import CliRunner

from dcmexporter.cli import cli


def _invoke(args: list[str]) -> tuple[int, str]:
    """Run the CLI with `--database` plumbed through. Patches the orchestrator."""
    runner = CliRunner()
    with patch("dcmexporter.cli.run_export") as run:
        run.return_value = 0
        result = runner.invoke(cli, args, catch_exceptions=False)
    return result.exit_code, result.output


def test_export_requires_database() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["export"], catch_exceptions=False)
    assert result.exit_code == 2
    assert "--database" in result.output


def test_export_minimal_invocation() -> None:
    code, _ = _invoke(["export", "--database", "MYDB"])
    assert code == 0


def test_export_invalid_include() -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli, ["export", "--database", "MYDB", "--include", "Banana"],
        catch_exceptions=False,
    )
    assert result.exit_code == 2
    assert "Banana" in result.output


def test_export_unimplemented_include() -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli, ["export", "--database", "MYDB", "--include", "Task"],
        catch_exceptions=False,
    )
    assert result.exit_code == 2
    assert "not yet supported" in result.output


def test_export_reserved_database_in_templating_default() -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["export", "--database", "MYDB", "--templating-default", "database=MYDB"],
        catch_exceptions=False,
    )
    assert result.exit_code == 2
    assert "reserved" in result.output


def test_export_reserved_database_in_templating_configuration_key() -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "export", "--database", "MYDB",
            "--configuration", "STAGING",
            "--templating-configuration-key", "database",
        ],
        catch_exceptions=False,
    )
    assert result.exit_code == 2
    assert "reserved" in result.output


def test_export_templating_configuration_key_without_configuration() -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "export", "--database", "MYDB",
            "--templating-configuration-key", "environment",
        ],
        catch_exceptions=False,
    )
    assert result.exit_code == 2
    assert "--configuration" in result.output


def test_export_malformed_templating_default() -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["export", "--database", "MYDB", "--templating-default", "no-equals"],
        catch_exceptions=False,
    )
    assert result.exit_code == 2
    assert "key=value" in result.output


def test_export_passes_normalised_config_to_runner() -> None:
    runner = CliRunner()
    with patch("dcmexporter.cli.run_export") as run:
        run.return_value = 0
        result = runner.invoke(
            cli,
            [
                "export", "--database", "MYDB",
                "--include", "table",
                "--target", "staging",
                "--target", "live",
            ],
            catch_exceptions=False,
        )
    assert result.exit_code == 0
    cfg = run.call_args.args[0]
    assert cfg.database == "MYDB"
    assert cfg.includes == ("Table",)
    assert cfg.targets == ("staging", "live")
    assert cfg.default_target == "staging"


def test_export_default_target_when_none_given() -> None:
    runner = CliRunner()
    with patch("dcmexporter.cli.run_export") as run:
        run.return_value = 0
        runner.invoke(cli, ["export", "--database", "MYDB"], catch_exceptions=False)
    cfg = run.call_args.args[0]
    assert cfg.targets == ("start",)
    assert cfg.default_target == "start"


def test_export_use_macros_default_true() -> None:
    runner = CliRunner()
    with patch("dcmexporter.cli.run_export") as run:
        run.return_value = 0
        runner.invoke(cli, ["export", "--database", "MYDB"], catch_exceptions=False)
    cfg = run.call_args.args[0]
    assert cfg.use_macros is True


def test_export_no_use_macros() -> None:
    runner = CliRunner()
    with patch("dcmexporter.cli.run_export") as run:
        run.return_value = 0
        runner.invoke(
            cli, ["export", "--database", "MYDB", "--no-use-macros"],
            catch_exceptions=False,
        )
    cfg = run.call_args.args[0]
    assert cfg.use_macros is False


def test_export_empty_comment_kept_as_empty_string() -> None:
    runner = CliRunner()
    with patch("dcmexporter.cli.run_export") as run:
        run.return_value = 0
        runner.invoke(
            cli, ["export", "--database", "MYDB", "--comment", ""],
            catch_exceptions=False,
        )
    cfg = run.call_args.args[0]
    assert cfg.comment == ""


def test_export_default_comment_includes_url_and_date() -> None:
    runner = CliRunner()
    with patch("dcmexporter.cli.run_export") as run:
        run.return_value = 0
        runner.invoke(cli, ["export", "--database", "MYDB"], catch_exceptions=False)
    cfg = run.call_args.args[0]
    assert cfg.comment is not None
    assert "github.com/jamiekt/dcmexporter" in cfg.comment


def test_export_templating_default_json_value_parsed() -> None:
    runner = CliRunner()
    with patch("dcmexporter.cli.run_export") as run:
        run.return_value = 0
        runner.invoke(
            cli,
            [
                "export", "--database", "MYDB",
                "--templating-default", 'tags={"team":"data"}',
            ],
            catch_exceptions=False,
        )
    cfg = run.call_args.args[0]
    assert cfg.templating_defaults == (("tags", {"team": "data"}),)
```

- [ ] **Step 2: Run, expect failure**

Run: `uv run pytest tests/test_cli.py -v`
Expected: tests fail because `cli.py` is still the Task 1 stub.

- [ ] **Step 3: Implement `src/dcmexporter/cli.py`**

```python
"""dcmexporter CLI."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import click

from dcmexporter.config import (
    Config,
    parse_templating_default,
    resolve_default_target,
    validate_config,
)


def run_export(cfg: Config) -> int:
    """Run the export. Replaced in tests; wired to orchestrator in Task 13."""
    from dcmexporter.orchestrator import export

    return export(cfg)


def _default_comment() -> str:
    return (
        "Definition exported by https://github.com/jamiekt/dcmexporter on "
        f"{date.today().isoformat()}"
    )


@click.group()
@click.version_option()
def cli() -> None:
    """dcmexporter — export Snowflake object definitions for DCM projects."""


@cli.command()
@click.option("--database", required=True, help="Snowflake database to export from.")
@click.option(
    "--schema", "schemas", multiple=True, help="Restrict to specific schemas."
)
@click.option(
    "--connection",
    default=None,
    help="Named snow CLI connection (overrides the default).",
)
@click.option(
    "--target",
    "user_targets",
    multiple=True,
    help="Each value becomes a target in manifest.yml. If omitted, 'start' is used.",
)
@click.option(
    "--templating-default",
    "templating_defaults_raw",
    multiple=True,
    help="key=value entries for templating.defaults. value may be JSON.",
)
@click.option(
    "--configuration",
    "configurations",
    multiple=True,
    help="Each value becomes a key under templating.configurations.",
)
@click.option(
    "--templating-configuration-key",
    "templating_configuration_keys",
    multiple=True,
    help="Each becomes a key inside every configuration (value left blank).",
)
@click.option(
    "--include",
    "includes",
    multiple=True,
    help="Restrict export to specific DCM object types.",
)
@click.option(
    "--exclude",
    "excludes",
    multiple=True,
    help="Skip specific DCM object types.",
)
@click.option(
    "--comment",
    default=None,
    help=(
        "COMMENT to inject when DDL has none. "
        "Defaults to a generated 'exported by …' string. "
        "May be empty."
    ),
)
@click.option(
    "--use-macros/--no-use-macros",
    default=True,
    help="Generate per-type Jinja macros and rewrite definitions to invoke them.",
)
@click.option(
    "--out-folder",
    "out_folder",
    type=click.Path(file_okay=False, path_type=Path),
    default=Path("out"),
    help="Destination directory for generated files.",
)
@click.option("--force", is_flag=True, help="Overwrite a non-empty --out-folder.")
def export(
    database: str,
    schemas: tuple[str, ...],
    connection: str | None,
    user_targets: tuple[str, ...],
    templating_defaults_raw: tuple[str, ...],
    configurations: tuple[str, ...],
    templating_configuration_keys: tuple[str, ...],
    includes: tuple[str, ...],
    excludes: tuple[str, ...],
    comment: str | None,
    use_macros: bool,
    out_folder: Path,
    force: bool,
) -> None:
    """Export Snowflake object definitions to a DCM project layout."""
    try:
        templating_defaults = tuple(
            parse_templating_default(raw) for raw in templating_defaults_raw
        )
    except ValueError as exc:
        raise click.BadParameter(str(exc), param_hint="--templating-default") from exc

    default_target, targets = resolve_default_target(list(user_targets))

    if comment is None:
        comment = _default_comment()

    cfg = Config(
        database=database,
        schemas=tuple(schemas),
        connection=connection,
        targets=targets,
        default_target=default_target,
        templating_defaults=templating_defaults,
        configurations=tuple(configurations),
        templating_configuration_keys=tuple(templating_configuration_keys),
        includes=tuple(includes),
        excludes=tuple(excludes),
        comment=comment,
        use_macros=use_macros,
        out_folder=out_folder,
        force=force,
    )

    try:
        cfg = validate_config(cfg)
    except ValueError as exc:
        raise click.BadParameter(str(exc)) from exc

    code = run_export(cfg)
    if code != 0:
        raise SystemExit(code)
```

- [ ] **Step 4: Run, expect pass**

Run: `uv run pytest tests/test_cli.py -v`
Expected: 14 passed.

- [ ] **Step 5: Commit**

```bash
git add src/dcmexporter/cli.py tests/test_cli.py
git commit -m "feat(cli): Click CLI with full --export flag surface"
```

---

## Task 5: ObjectPlugin ABC + PluginRegistry

**Files:**
- Create: `src/dcmexporter/plugin.py`
- Create: `tests/test_plugin.py`

- [ ] **Step 1: Write the failing test**

`tests/test_plugin.py`:

```python
"""Tests for the ObjectPlugin ABC and PluginRegistry."""

from __future__ import annotations

import pytest

from dcmexporter.plugin import ObjectPlugin, PluginRegistry
from dcmexporter.types import FQN


class _FakePlugin(ObjectPlugin):
    type_name = "Table"
    file_slug = "table"

    def discover(self, cursor, database, schemas):
        return []

    def get_ddl(self, cursor, fqn):
        return ""

    def to_define_and_invocation(self, ddl, *, comment, use_macros, database):
        return ""

    def macro_definition(self) -> str:
        return ""


def test_registry_register_and_get() -> None:
    reg = PluginRegistry()
    plugin = _FakePlugin()
    reg.register(plugin)
    assert reg.get("Table") is plugin


def test_registry_double_register_raises() -> None:
    reg = PluginRegistry()
    reg.register(_FakePlugin())
    with pytest.raises(ValueError, match="already registered"):
        reg.register(_FakePlugin())


def test_registry_get_unknown_raises() -> None:
    reg = PluginRegistry()
    with pytest.raises(KeyError):
        reg.get("Banana")


def test_registry_iteration_order_matches_v1_types() -> None:
    from dcmexporter.types import V1_TYPES

    class _P(ObjectPlugin):
        def __init__(self, name: str) -> None:
            self.type_name = name
            self.file_slug = name.lower().replace(" ", "_")

        def discover(self, cursor, database, schemas):
            return []

        def get_ddl(self, cursor, fqn):
            return ""

        def to_define_and_invocation(self, ddl, *, comment, use_macros, database):
            return ""

        def macro_definition(self) -> str:
            return ""

    reg = PluginRegistry()
    # Register in reverse order to confirm canonical ordering wins.
    for name in reversed(V1_TYPES):
        reg.register(_P(name))

    assert tuple(p.type_name for p in reg.in_canonical_order()) == V1_TYPES
```

- [ ] **Step 2: Run, expect failure**

Run: `uv run pytest tests/test_plugin.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `src/dcmexporter/plugin.py`**

```python
"""ObjectPlugin ABC + registry."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Iterator

from dcmexporter.types import DCM_TYPES, FQN


class ObjectPlugin(ABC):
    type_name: str
    file_slug: str

    @abstractmethod
    def discover(
        self, cursor: Any, database: str, schemas: tuple[str, ...] | None
    ) -> list[FQN]: ...

    @abstractmethod
    def get_ddl(self, cursor: Any, fqn: FQN) -> str: ...

    @abstractmethod
    def to_define_and_invocation(
        self,
        ddl: str,
        *,
        comment: str | None,
        use_macros: bool,
        database: str,
    ) -> str: ...

    @abstractmethod
    def macro_definition(self) -> str: ...


class PluginRegistry:
    def __init__(self) -> None:
        self._plugins: dict[str, ObjectPlugin] = {}

    def register(self, plugin: ObjectPlugin) -> None:
        if plugin.type_name in self._plugins:
            raise ValueError(f"Plugin for {plugin.type_name!r} already registered")
        self._plugins[plugin.type_name] = plugin

    def get(self, type_name: str) -> ObjectPlugin:
        return self._plugins[type_name]

    def has(self, type_name: str) -> bool:
        return type_name in self._plugins

    def in_canonical_order(self) -> Iterator[ObjectPlugin]:
        for type_name in DCM_TYPES:
            if type_name in self._plugins:
                yield self._plugins[type_name]
```

- [ ] **Step 4: Run, expect pass**

Run: `uv run pytest tests/test_plugin.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/dcmexporter/plugin.py tests/test_plugin.py
git commit -m "feat(plugin): ObjectPlugin ABC and PluginRegistry"
```

---

## Task 6: Connection wrapper

**Files:**
- Create: `src/dcmexporter/connection.py`
- Create: `tests/test_connection.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_connection.py`:

```python
"""Tests for the snow-CLI-style connection resolver."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from dcmexporter.connection import (
    SnowflakeConnectionError,
    open_connection,
    resolve_account_identifier,
)


def test_open_connection_uses_named_connection() -> None:
    with patch("dcmexporter.connection.snowflake_connect") as connect:
        connect.return_value = MagicMock()
        open_connection(connection_name="MYCONN")
    connect.assert_called_once_with(connection_name="MYCONN")


def test_open_connection_default_uses_env_var(monkeypatch) -> None:
    monkeypatch.setenv("SNOWFLAKE_DEFAULT_CONNECTION_NAME", "envconn")
    with patch("dcmexporter.connection.snowflake_connect") as connect:
        connect.return_value = MagicMock()
        open_connection(connection_name=None)
    connect.assert_called_once_with(connection_name="envconn")


def test_open_connection_no_name_no_env_uses_default(monkeypatch) -> None:
    monkeypatch.delenv("SNOWFLAKE_DEFAULT_CONNECTION_NAME", raising=False)
    with patch("dcmexporter.connection.snowflake_connect") as connect:
        connect.return_value = MagicMock()
        open_connection(connection_name=None)
    connect.assert_called_once_with()


def test_open_connection_failure_wraps() -> None:
    with patch("dcmexporter.connection.snowflake_connect") as connect:
        connect.side_effect = RuntimeError("boom")
        with pytest.raises(SnowflakeConnectionError, match="boom"):
            open_connection(connection_name="bad")


def test_resolve_account_identifier_returns_attribute() -> None:
    conn = MagicMock()
    conn.account = "AB12345"
    assert resolve_account_identifier(conn) == "AB12345"


def test_resolve_account_identifier_returns_empty_when_missing() -> None:
    conn = MagicMock(spec=[])  # no `account` attribute
    assert resolve_account_identifier(conn) == ""
```

- [ ] **Step 2: Run, expect failure**

Run: `uv run pytest tests/test_connection.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `src/dcmexporter/connection.py`**

```python
"""Wrapper around snowflake.connector that mirrors snow CLI's connection model."""

from __future__ import annotations

import os
from typing import Any

try:
    from snowflake.connector import connect as snowflake_connect
except ImportError:  # pragma: no cover - exercised when the connector is unavailable
    def snowflake_connect(*_args: Any, **_kwargs: Any) -> Any:  # type: ignore[misc]
        raise RuntimeError("snowflake-connector-python is not installed")


class SnowflakeConnectionError(RuntimeError):
    """Raised when the Snowflake connection cannot be established."""


def open_connection(connection_name: str | None) -> Any:
    """Open a Snowflake connection following snow CLI's resolution rules.

    Order of precedence:
    1. Explicit `connection_name` argument.
    2. SNOWFLAKE_DEFAULT_CONNECTION_NAME env var.
    3. snowflake-connector's own default behaviour (reads `~/.snowflake/connections.toml`).
    """
    name = connection_name or os.environ.get("SNOWFLAKE_DEFAULT_CONNECTION_NAME")
    try:
        if name:
            return snowflake_connect(connection_name=name)
        return snowflake_connect()
    except Exception as exc:  # noqa: BLE001 — we re-raise as a domain error
        raise SnowflakeConnectionError(
            f"Failed to open Snowflake connection (name={name!r}): {exc}"
        ) from exc


def resolve_account_identifier(conn: Any) -> str:
    """Return the account identifier from a connection, or '' if unavailable."""
    return str(getattr(conn, "account", "") or "")
```

- [ ] **Step 4: Run, expect pass**

Run: `uv run pytest tests/test_connection.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add src/dcmexporter/connection.py tests/test_connection.py
git commit -m "feat(connection): snow-CLI-style connection wrapper"
```

---

## Task 7: Rewriter — create→define + comment injection

**Files:**
- Create: `src/dcmexporter/rewrite.py`
- Create: `tests/test_rewrite.py`

This task implements the AST helpers that don't depend on per-type knowledge: rewriting `CREATE` → `DEFINE`, and injecting `COMMENT` when missing. `parameterise_database`, `extract_kwargs_for_macro`, and `to_macro_invocation` come in Task 8.

- [ ] **Step 1: Write the failing tests**

`tests/test_rewrite.py`:

```python
"""Tests for the AST rewriter helpers."""

from __future__ import annotations

import pytest

from dcmexporter.rewrite import create_to_define, inject_comment_if_missing


def test_create_to_define_table() -> None:
    out = create_to_define("CREATE OR REPLACE TABLE FOO (X INT)")
    assert out.upper().startswith("DEFINE TABLE FOO")
    assert "CREATE" not in out.upper()


def test_create_to_define_secure_view() -> None:
    out = create_to_define(
        "CREATE OR REPLACE SECURE VIEW V AS SELECT 1"
    )
    assert out.upper().startswith("DEFINE SECURE VIEW V")


def test_create_to_define_idempotent() -> None:
    once = create_to_define("CREATE OR REPLACE TABLE FOO (X INT)")
    twice = create_to_define(once)
    assert once == twice


def test_inject_comment_when_missing() -> None:
    out = inject_comment_if_missing(
        "DEFINE TABLE FOO (X INT)", comment="hello"
    )
    assert "COMMENT='hello'" in out


def test_inject_comment_preserves_existing() -> None:
    src = "DEFINE TABLE FOO (X INT) COMMENT='keep me'"
    out = inject_comment_if_missing(src, comment="overwrite")
    assert "COMMENT='keep me'" in out
    assert "overwrite" not in out


def test_inject_comment_empty_string_when_missing() -> None:
    out = inject_comment_if_missing(
        "DEFINE TABLE FOO (X INT)", comment=""
    )
    assert "COMMENT=''" in out


def test_inject_comment_escapes_single_quotes() -> None:
    out = inject_comment_if_missing(
        "DEFINE TABLE FOO (X INT)", comment="it's fine"
    )
    assert "it''s fine" in out


def test_inject_comment_unsupported_type_is_noop() -> None:
    out = inject_comment_if_missing(
        "DEFINE TABLE FOO (X INT)",
        comment="hi",
        supports_comment=False,
    )
    assert "COMMENT" not in out
```

- [ ] **Step 2: Run, expect failure**

Run: `uv run pytest tests/test_rewrite.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `src/dcmexporter/rewrite.py`**

```python
"""AST-level rewriting helpers powered by sqlglot.

All helpers operate on Snowflake-dialect SQL strings. Each helper is independently
callable; plugins compose them in their `to_define_and_invocation` implementations.
"""

from __future__ import annotations

import re

import sqlglot
from sqlglot import exp

_DIALECT = "snowflake"


def _parse(ddl: str) -> exp.Expression:
    return sqlglot.parse_one(ddl, dialect=_DIALECT)


def _render(node: exp.Expression) -> str:
    return node.sql(dialect=_DIALECT)


def create_to_define(ddl: str) -> str:
    """Rewrite the leading `CREATE [OR REPLACE]` to `DEFINE`.

    Idempotent: a string that already starts with DEFINE is returned unchanged.
    Falls back to a regex rewrite if sqlglot can't parse the input.
    """
    stripped = ddl.lstrip()
    if re.match(r"DEFINE\b", stripped, flags=re.IGNORECASE):
        return ddl

    pattern = re.compile(
        r"^(\s*)CREATE\s+(OR\s+REPLACE\s+)?", re.IGNORECASE
    )
    match = pattern.match(ddl)
    if match is None:
        return ddl
    return pattern.sub(rf"{match.group(1)}DEFINE ", ddl, count=1)


_COMMENT_RE = re.compile(r"\bCOMMENT\s*=\s*", re.IGNORECASE)


def inject_comment_if_missing(
    ddl: str,
    *,
    comment: str | None,
    supports_comment: bool = True,
) -> str:
    """Append `COMMENT='<comment>'` to the DEFINE statement when no COMMENT exists.

    - If the type does not support COMMENT (`supports_comment=False`), returns `ddl`.
    - If the existing DDL already has a COMMENT clause, returns `ddl`.
    - If `comment is None`, returns `ddl`.
    - Single quotes inside the comment are doubled (Snowflake string escape).
    """
    if not supports_comment or comment is None:
        return ddl
    if _COMMENT_RE.search(ddl):
        return ddl

    escaped = comment.replace("'", "''")
    body = ddl.rstrip()
    if body.endswith(";"):
        body = body[:-1].rstrip()
        suffix = ";"
    else:
        suffix = ""
    return f"{body} COMMENT='{escaped}'{suffix}"
```

- [ ] **Step 4: Run, expect pass**

Run: `uv run pytest tests/test_rewrite.py -v`
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add src/dcmexporter/rewrite.py tests/test_rewrite.py
git commit -m "feat(rewrite): create_to_define + inject_comment_if_missing"
```

---

## Task 8: Rewriter — `parameterise_database` + macro-invocation helpers

**Files:**
- Modify: `src/dcmexporter/rewrite.py`
- Modify: `tests/test_rewrite.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_rewrite.py`:

```python
from dcmexporter.rewrite import (
    parameterise_database,
    render_macro_invocation,
)


def test_parameterise_database_replaces_fqn() -> None:
    out = parameterise_database(
        "DEFINE TABLE MYDB.PUBLIC.FOO (X INT)", database="MYDB"
    )
    assert "{{ database }}.PUBLIC.FOO" in out
    assert "MYDB" not in out.replace("{{ database }}", "")


def test_parameterise_database_skips_substring_in_other_identifier() -> None:
    out = parameterise_database(
        "DEFINE TABLE MYDB.PUBLIC.MYDB_AUDIT (X INT)", database="MYDB"
    )
    assert "{{ database }}.PUBLIC.MYDB_AUDIT" in out


def test_parameterise_database_replaces_inside_body() -> None:
    out = parameterise_database(
        "DEFINE STAGE MYDB.PUBLIC.S URL='s3://bucket' STORAGE_INTEGRATION = MYDB_INT",
        database="MYDB",
    )
    assert "{{ database }}.PUBLIC.S" in out
    assert "MYDB_INT" in out


def test_parameterise_database_case_insensitive_match() -> None:
    out = parameterise_database(
        "DEFINE TABLE mydb.public.foo (x INT)", database="MYDB"
    )
    assert "{{ database }}" in out


def test_parameterise_database_no_change_when_absent() -> None:
    src = "DEFINE WAREHOUSE WH WAREHOUSE_SIZE='X-Small'"
    assert parameterise_database(src, database="MYDB") == src


def test_render_macro_invocation_quotes_strings() -> None:
    out = render_macro_invocation(
        "define_table",
        kwargs={
            "database": "{{ database }}",
            "schema": "PUBLIC",
            "name": "FOO",
            "columns": [{"name": "X", "type": "INT"}],
        },
    )
    assert out.startswith("{{ define_table(")
    assert "database='{{ database }}'" in out
    assert "schema='PUBLIC'" in out
    assert "name='FOO'" in out
    assert "columns=[{'name': 'X', 'type': 'INT'}]" in out
    assert out.endswith(") }}")


def test_render_macro_invocation_omits_none_values() -> None:
    out = render_macro_invocation(
        "define_table",
        kwargs={"name": "FOO", "comment": None},
    )
    assert "comment=" not in out
    assert "name='FOO'" in out
```

- [ ] **Step 2: Run, expect failure**

Run: `uv run pytest tests/test_rewrite.py -v`
Expected: collection errors / NameError on the new symbols.

- [ ] **Step 3: Implement the new functions in `src/dcmexporter/rewrite.py`**

Append:

```python
def parameterise_database(ddl: str, *, database: str) -> str:
    """Replace whole-identifier occurrences of `database` (case-insensitive) with
    the literal string `{{ database }}`.

    Whole-identifier means: bounded on both sides by characters that do not form part
    of a Snowflake identifier (letters, digits, `_`, `$`). Substring occurrences inside
    longer identifiers are preserved.
    """
    pattern = re.compile(
        rf"(?<![A-Za-z0-9_$]){re.escape(database)}(?![A-Za-z0-9_$])",
        re.IGNORECASE,
    )
    return pattern.sub("{{ database }}", ddl)


def _format_value(value: object) -> str:
    if isinstance(value, str):
        escaped = value.replace("'", "\\'")
        return f"'{escaped}'"
    return repr(value)


def render_macro_invocation(macro_name: str, *, kwargs: dict[str, object]) -> str:
    """Render a Jinja `{{ macro_name(...) }}` invocation with keyword args.

    None values are omitted. String values are single-quoted (single quotes within
    are backslash-escaped, matching Jinja's expression syntax).
    """
    parts = [
        f"{key}={_format_value(value)}"
        for key, value in kwargs.items()
        if value is not None
    ]
    return f"{{{{ {macro_name}({', '.join(parts)}) }}}}"
```

- [ ] **Step 4: Run, expect pass**

Run: `uv run pytest tests/test_rewrite.py -v`
Expected: 15 passed.

- [ ] **Step 5: Commit**

```bash
git add src/dcmexporter/rewrite.py tests/test_rewrite.py
git commit -m "feat(rewrite): parameterise_database + render_macro_invocation"
```

---

## Task 9: Manifest renderer

**Files:**
- Create: `src/dcmexporter/manifest.py`
- Create: `tests/test_manifest.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_manifest.py`:

```python
"""Tests for manifest.yml rendering."""

from __future__ import annotations

from pathlib import Path

from dcmexporter.config import Config
from dcmexporter.manifest import render_manifest


def _cfg(**overrides) -> Config:
    base = dict(
        database="MYDB",
        schemas=(),
        connection=None,
        targets=("start",),
        default_target="start",
        templating_defaults=(),
        configurations=(),
        templating_configuration_keys=(),
        includes=(),
        excludes=(),
        comment=None,
        use_macros=True,
        out_folder=Path("out"),
        force=False,
    )
    base.update(overrides)
    return Config(**base)


def test_manifest_default_start_target_no_configurations() -> None:
    out = render_manifest(_cfg(), account_identifier="AB12345")
    assert "manifest_version: 2" in out
    assert "type: DCM_PROJECT" in out
    assert "  start:" in out
    assert "    account_identifier: AB12345" in out
    assert "    project_name: MYDB.PUBLIC.MAIN" in out
    assert '    project_owner: ""' in out
    assert "templating_config:" not in out
    # database lives under templating.defaults when no --configuration
    assert "  defaults:" in out
    assert "    # Probably change this" in out
    assert "    database: MYDB" in out


def test_manifest_multiple_targets_no_start() -> None:
    cfg = _cfg(targets=("staging", "live"), default_target="staging")
    out = render_manifest(cfg, account_identifier="AB12345")
    assert "  staging:" in out
    assert "  live:" in out
    assert "  start:" not in out


def test_manifest_with_configurations_includes_templating_config_per_target() -> None:
    cfg = _cfg(
        configurations=("STAGING", "LIVE"),
        targets=("staging", "live"),
        default_target="staging",
    )
    out = render_manifest(cfg, account_identifier="AB12345")
    assert "    templating_config: staging" in out
    assert "    templating_config: live" in out


def test_manifest_with_configurations_database_in_each_block() -> None:
    cfg = _cfg(
        configurations=("STAGING", "LIVE"),
        templating_configuration_keys=("environment",),
    )
    out = render_manifest(cfg, account_identifier="AB12345")
    # database appears under each configuration, with the leading comment
    assert out.count("# Probably change this") == 2
    assert out.count("database: MYDB") == 2
    # configurations block contains environment: ""
    assert "environment: ''" in out or 'environment: ""' in out


def test_manifest_templating_defaults_string_value() -> None:
    cfg = _cfg(templating_defaults=(("alliance", "unspecified"),))
    out = render_manifest(cfg, account_identifier="AB12345")
    assert "alliance: unspecified" in out


def test_manifest_templating_defaults_json_object_value() -> None:
    cfg = _cfg(templating_defaults=(("tags", {"team": "data"}),))
    out = render_manifest(cfg, account_identifier="AB12345")
    assert "tags:" in out
    assert "team: data" in out


def test_manifest_account_identifier_blank_when_missing() -> None:
    out = render_manifest(_cfg(), account_identifier="")
    assert 'account_identifier: ""' in out


def test_manifest_top_level_key_order() -> None:
    out = render_manifest(_cfg(), account_identifier="AB12345")
    lines = [line for line in out.splitlines() if line and not line.startswith(" ")]
    # header comments may appear; filter to top-level YAML keys
    keys = [line.split(":", 1)[0] for line in lines if ":" in line and not line.startswith("#")]
    # Expect manifest_version, type, targets, templating in this order
    assert keys[:4] == ["manifest_version", "type", "targets", "templating"]
```

- [ ] **Step 2: Run, expect failure**

Run: `uv run pytest tests/test_manifest.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `src/dcmexporter/manifest.py`**

```python
"""manifest.yml renderer.

We render YAML by hand (rather than via PyYAML's `yaml.dump`) because we need
explicit control over key ordering AND a "Probably change this" comment placed
immediately above the `database:` line. PyYAML cannot interleave comments.
For each templating-default value we still delegate to `yaml.safe_dump` to get
correct YAML for arbitrary structures (mappings, lists, numbers, bools, null).
"""

from __future__ import annotations

from datetime import date
from io import StringIO
from typing import Any

import yaml

from dcmexporter.config import Config


_HEADER = (
    f"# Generated by dcmexporter on {date.today().isoformat()}.\n"
    "# Review the project_owner field below — it is left blank intentionally.\n"
)


def _yaml_scalar(value: Any) -> str:
    """Dump a single value to YAML, returning the trimmed result."""
    text = yaml.safe_dump(value, default_flow_style=False, sort_keys=False).rstrip()
    return text


def _emit_value_inline(buf: StringIO, indent: str, key: str, value: Any) -> None:
    """Emit `<indent><key>: <value>` for scalars, or a nested block for collections."""
    if isinstance(value, (dict, list)):
        rendered = yaml.safe_dump(
            {key: value}, default_flow_style=False, sort_keys=False
        ).rstrip()
        for line in rendered.splitlines():
            buf.write(f"{indent}{line}\n")
        return

    if isinstance(value, str):
        # Quote empty strings and strings that look like YAML keywords.
        if value == "":
            buf.write(f'{indent}{key}: ""\n')
            return
    buf.write(f"{indent}{key}: {_yaml_scalar(value)}\n")


def render_manifest(cfg: Config, *, account_identifier: str) -> str:
    """Render manifest.yml for a Config + resolved account identifier."""
    buf = StringIO()
    buf.write("manifest_version: 2\n")
    buf.write("type: DCM_PROJECT\n")
    buf.write("\n")
    buf.write(_HEADER)
    buf.write("\n")

    buf.write("targets:\n")
    for target in cfg.targets:
        buf.write(f"  {target}:\n")
        if account_identifier:
            buf.write(f"    account_identifier: {account_identifier}\n")
        else:
            buf.write('    account_identifier: ""\n')
        buf.write(f"    project_name: {cfg.database}.PUBLIC.MAIN\n")
        buf.write('    project_owner: ""\n')
        if cfg.configurations:
            buf.write(f"    templating_config: {target}\n")

    buf.write("\n")
    buf.write("templating:\n")
    buf.write("  defaults:\n")

    if not cfg.configurations:
        buf.write(
            "    # Probably change this — generated from the exported-from database\n"
        )
        buf.write(f"    database: {cfg.database}\n")

    for key, value in cfg.templating_defaults:
        _emit_value_inline(buf, "    ", key, value)

    if cfg.configurations:
        buf.write("  configurations:\n")
        for name in cfg.configurations:
            buf.write(f"    {name}:\n")
            buf.write(
                "      # Probably change this — "
                "generated from the exported-from database\n"
            )
            buf.write(f"      database: {cfg.database}\n")
            for key in cfg.templating_configuration_keys:
                buf.write(f'      {key}: ""\n')

    return buf.getvalue()
```

- [ ] **Step 4: Run, expect pass**

Run: `uv run pytest tests/test_manifest.py -v`
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add src/dcmexporter/manifest.py tests/test_manifest.py
git commit -m "feat(manifest): YAML renderer with database-comment placement"
```

---

## Task 10: Makefile renderer

**Files:**
- Create: `src/dcmexporter/makefile.py`
- Create: `tests/test_makefile.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_makefile.py`:

```python
"""Tests for Makefile rendering."""

from __future__ import annotations

from pathlib import Path

from dcmexporter.config import Config
from dcmexporter.makefile import render_makefile


def _cfg(**overrides) -> Config:
    base = dict(
        database="MYDB",
        schemas=(),
        connection=None,
        targets=("start",),
        default_target="start",
        templating_defaults=(),
        configurations=(),
        templating_configuration_keys=(),
        includes=(),
        excludes=(),
        comment=None,
        use_macros=True,
        out_folder=Path("out"),
        force=False,
    )
    base.update(overrides)
    return Config(**base)


def test_makefile_uses_default_target() -> None:
    out = render_makefile(_cfg(default_target="start"))
    assert "TARGET ?= start" in out


def test_makefile_uses_first_user_target() -> None:
    out = render_makefile(_cfg(targets=("staging", "live"), default_target="staging"))
    assert "TARGET ?= staging" in out


def test_makefile_has_plan_and_apply() -> None:
    out = render_makefile(_cfg())
    assert "plan:" in out
    assert "apply:" in out
    assert "snow dcm plan --from . --target $(TARGET)" in out
    assert "snow dcm execute --from . --target $(TARGET)" in out


def test_makefile_uses_real_tabs_for_recipes() -> None:
    out = render_makefile(_cfg())
    plan_recipe_lines = [
        line for line in out.splitlines() if "snow dcm plan" in line
    ]
    assert plan_recipe_lines[0].startswith("\t")
```

- [ ] **Step 2: Run, expect failure**

Run: `uv run pytest tests/test_makefile.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `src/dcmexporter/makefile.py`**

```python
"""Makefile renderer."""

from __future__ import annotations

from dcmexporter.config import Config


def render_makefile(cfg: Config) -> str:
    return (
        ".PHONY: plan apply\n"
        "\n"
        f"TARGET ?= {cfg.default_target}\n"
        "\n"
        "plan:\n"
        "\tsnow dcm plan --from . --target $(TARGET)\n"
        "\n"
        "apply:\n"
        "\tsnow dcm execute --from . --target $(TARGET)\n"
    )
```

- [ ] **Step 4: Run, expect pass**

Run: `uv run pytest tests/test_makefile.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/dcmexporter/makefile.py tests/test_makefile.py
git commit -m "feat(makefile): Makefile renderer with plan + apply targets"
```

---

## Task 11: Render layer (output writer)

**Files:**
- Create: `src/dcmexporter/render.py`
- Create: `tests/test_render.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_render.py`:

```python
"""Tests for the output-folder writer."""

from __future__ import annotations

from pathlib import Path

import pytest

from dcmexporter.render import OutFolderError, write_outputs


def test_write_outputs_creates_layout(tmp_path: Path) -> None:
    out = tmp_path / "out"
    write_outputs(
        out_folder=out,
        manifest="manifest_version: 2\n",
        makefile=".PHONY: plan\n",
        definitions={"table": "DEFINE TABLE foo;\n"},
        macros={"table": "{% macro define_table() %}{% endmacro %}\n"},
        force=False,
    )
    assert (out / "manifest.yml").read_text() == "manifest_version: 2\n"
    assert (out / "Makefile").read_text() == ".PHONY: plan\n"
    assert (out / "sources" / "definitions" / "table.sql").read_text() == "DEFINE TABLE foo;\n"
    assert (out / "sources" / "macros" / "table.sql").exists()


def test_write_outputs_skips_macros_when_none(tmp_path: Path) -> None:
    out = tmp_path / "out"
    write_outputs(
        out_folder=out,
        manifest="m",
        makefile="M",
        definitions={"table": "x"},
        macros=None,
        force=False,
    )
    assert not (out / "sources" / "macros").exists()


def test_write_outputs_refuses_existing_nonempty(tmp_path: Path) -> None:
    out = tmp_path / "out"
    out.mkdir()
    (out / "stale.txt").write_text("hello")
    with pytest.raises(OutFolderError):
        write_outputs(
            out_folder=out,
            manifest="m",
            makefile="M",
            definitions={"table": "x"},
            macros=None,
            force=False,
        )


def test_write_outputs_force_overwrites(tmp_path: Path) -> None:
    out = tmp_path / "out"
    out.mkdir()
    (out / "stale.txt").write_text("hello")
    write_outputs(
        out_folder=out,
        manifest="m",
        makefile="M",
        definitions={"table": "x"},
        macros=None,
        force=True,
    )
    assert (out / "manifest.yml").read_text() == "m"
    assert not (out / "stale.txt").exists()


def test_write_outputs_skips_empty_definition_files(tmp_path: Path) -> None:
    out = tmp_path / "out"
    write_outputs(
        out_folder=out,
        manifest="m",
        makefile="M",
        definitions={"table": "x", "view": ""},
        macros=None,
        force=False,
    )
    assert (out / "sources" / "definitions" / "table.sql").exists()
    assert not (out / "sources" / "definitions" / "view.sql").exists()
```

- [ ] **Step 2: Run, expect failure**

Run: `uv run pytest tests/test_render.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `src/dcmexporter/render.py`**

```python
"""Write generated artefacts into the output folder."""

from __future__ import annotations

import shutil
from pathlib import Path


class OutFolderError(RuntimeError):
    """Raised when --out-folder is unsafe to write to."""


def _is_nonempty_dir(path: Path) -> bool:
    return path.exists() and path.is_dir() and any(path.iterdir())


def write_outputs(
    *,
    out_folder: Path,
    manifest: str,
    makefile: str,
    definitions: dict[str, str],
    macros: dict[str, str] | None,
    force: bool,
) -> None:
    """Write all generated files into out_folder, creating it if needed.

    Refuses to write into a non-empty existing folder unless `force=True`.
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
    (out_folder / "manifest.yml").write_text(manifest)
    (out_folder / "Makefile").write_text(makefile)

    definitions_dir = out_folder / "sources" / "definitions"
    definitions_dir.mkdir(parents=True, exist_ok=True)
    for slug, body in definitions.items():
        if not body:
            continue
        (definitions_dir / f"{slug}.sql").write_text(body)

    if macros:
        macros_dir = out_folder / "sources" / "macros"
        macros_dir.mkdir(parents=True, exist_ok=True)
        for slug, body in macros.items():
            (macros_dir / f"{slug}.sql").write_text(body)
```

- [ ] **Step 4: Run, expect pass**

Run: `uv run pytest tests/test_render.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/dcmexporter/render.py tests/test_render.py
git commit -m "feat(render): write_outputs with --force semantics"
```

---

## Task 12: Object plugins for v1 types

This task creates **all nine** v1 plugins together. They share the same shape; we walk through `table.py` in detail and apply the same pattern to the rest. After all plugins exist, we write a single per-plugin test that exercises the shape.

**Files:**
- Create: `src/dcmexporter/objects/__init__.py`
- Create: `src/dcmexporter/objects/database.py`
- Create: `src/dcmexporter/objects/schema.py`
- Create: `src/dcmexporter/objects/table.py`
- Create: `src/dcmexporter/objects/view.py`
- Create: `src/dcmexporter/objects/sequence.py`
- Create: `src/dcmexporter/objects/stage.py`
- Create: `src/dcmexporter/objects/file_format.py`
- Create: `src/dcmexporter/objects/tag.py`
- Create: `src/dcmexporter/objects/warehouse.py`
- Create: `src/dcmexporter/objects/_unimplemented.py`
- Create: `src/dcmexporter/objects/_base.py` (shared helper for v1 plugins)
- Create: `tests/test_objects/__init__.py`
- Create: `tests/test_objects/test_table.py`
- Create: `tests/test_objects/test_database.py`
- Create: `tests/test_objects/test_schema.py`
- Create: `tests/test_objects/test_view.py`
- Create: `tests/test_objects/test_sequence.py`
- Create: `tests/test_objects/test_stage.py`
- Create: `tests/test_objects/test_file_format.py`
- Create: `tests/test_objects/test_tag.py`
- Create: `tests/test_objects/test_warehouse.py`

- [ ] **Step 1: Write the auto-discovery test**

`tests/test_objects/__init__.py` — empty file.

`tests/test_objects/test_registry.py`:

```python
"""Registry-level test that exercises plugin auto-discovery."""

from __future__ import annotations

from dcmexporter.objects import build_registry
from dcmexporter.types import V1_TYPES


def test_registry_has_all_v1_plugins() -> None:
    reg = build_registry()
    found = [p.type_name for p in reg.in_canonical_order()]
    assert set(V1_TYPES).issubset(set(found))


def test_unimplemented_plugins_present_too() -> None:
    from dcmexporter.types import UNIMPLEMENTED_TYPES

    reg = build_registry()
    found = {p.type_name for p in reg.in_canonical_order()}
    assert set(UNIMPLEMENTED_TYPES).issubset(found)
```

- [ ] **Step 2: Run, expect failure**

Run: `uv run pytest tests/test_objects/ -v`
Expected: ImportError on `dcmexporter.objects`.

- [ ] **Step 3: Implement the shared base helper**

`src/dcmexporter/objects/_base.py`:

```python
"""Shared helpers for v1 object plugins.

Each v1 plugin follows the same recipe:
1. discover -> SHOW <TYPE> IN DATABASE [filtered by schemas]
2. get_ddl   -> SELECT GET_DDL('<TYPE>', '<fqn>')
3. to_define_and_invocation -> create_to_define + inject_comment_if_missing +
                                parameterise_database, optionally rewritten
                                to a macro invocation.
4. macro_definition -> a static Jinja macro string.

Subclasses customise behaviour by overriding `discover` (the SHOW form differs
per type), `_macro_kwargs_from_ast` (extracts kwargs for the macro invocation),
and `MACRO_BODY` (the `{% macro %}` template).
"""

from __future__ import annotations

from typing import Any

from dcmexporter.plugin import ObjectPlugin
from dcmexporter.rewrite import (
    create_to_define,
    inject_comment_if_missing,
    parameterise_database,
    render_macro_invocation,
)
from dcmexporter.types import FQN


class V1ObjectPlugin(ObjectPlugin):
    """Convenience base for v1 plugins.

    Override at least: type_name, file_slug, SHOW_FORM, GET_DDL_TYPE, SUPPORTS_COMMENT,
    MACRO_BODY, and (often) `_macro_kwargs_from_ddl`.
    """

    SHOW_FORM: str = ""
    GET_DDL_TYPE: str = ""
    SUPPORTS_COMMENT: bool = True
    MACRO_BODY: str = ""

    def discover(
        self, cursor: Any, database: str, schemas: tuple[str, ...] | None
    ) -> list[FQN]:
        if not self.SHOW_FORM:
            raise NotImplementedError(self.type_name)
        rows: list[FQN] = []
        if schemas:
            for schema in schemas:
                cursor.execute(
                    f"{self.SHOW_FORM} IN SCHEMA {database}.{schema}"
                )
                rows.extend(self._rows_to_fqns(cursor.fetchall(), database))
        else:
            cursor.execute(f"{self.SHOW_FORM} IN DATABASE {database}")
            rows.extend(self._rows_to_fqns(cursor.fetchall(), database))
        return sorted(rows, key=lambda f: (f.schema or "", f.name))

    def _rows_to_fqns(
        self, rows: list[tuple[Any, ...]], database: str
    ) -> list[FQN]:
        """SHOW returns (created_on, name, database, schema, …) by default for most types."""
        out: list[FQN] = []
        for row in rows:
            # Snowflake's SHOW returns dict-like rows when configured; we accept both.
            if isinstance(row, dict):
                schema = row.get("schema_name") or row.get("schema") or None
                name = row["name"]
            else:
                # Tuple form: position 1 is name, position 2 is database, position 3 is schema.
                name = row[1]
                schema = row[3] if len(row) > 3 else None
            out.append(FQN(database=database, schema=schema, name=name))
        return out

    def get_ddl(self, cursor: Any, fqn: FQN) -> str:
        cursor.execute(
            f"SELECT GET_DDL('{self.GET_DDL_TYPE}', '{fqn}')"
        )
        row = cursor.fetchone()
        if isinstance(row, dict):
            return next(iter(row.values()))
        return row[0]

    def to_define_and_invocation(
        self,
        ddl: str,
        *,
        comment: str | None,
        use_macros: bool,
        database: str,
    ) -> str:
        define = create_to_define(ddl)
        define = inject_comment_if_missing(
            define, comment=comment, supports_comment=self.SUPPORTS_COMMENT
        )
        define = parameterise_database(define, database=database)

        if not use_macros:
            return define + ("\n" if not define.endswith("\n") else "")

        kwargs = self._macro_kwargs_from_ddl(define, database=database)
        invocation = render_macro_invocation(
            f"define_{self.file_slug}", kwargs=kwargs
        )
        return invocation + "\n"

    def _macro_kwargs_from_ddl(
        self, define_ddl: str, *, database: str
    ) -> dict[str, Any]:
        """Default: pass the whole DDL through a `raw` kwarg.

        Subclasses override this to extract structured kwargs from the AST.
        The default lets every v1 plugin function correctly while subclasses
        can incrementally add richer macro signatures.
        """
        return {"database": "{{ database }}", "raw": define_ddl}

    def macro_definition(self) -> str:
        if not self.MACRO_BODY:
            raise NotImplementedError(self.type_name)
        return self.MACRO_BODY
```

- [ ] **Step 4: Implement the nine v1 plugins (using the base)**

`src/dcmexporter/objects/database.py`:

```python
"""Database plugin."""

from __future__ import annotations

from dcmexporter.objects._base import V1ObjectPlugin


class DatabasePlugin(V1ObjectPlugin):
    type_name = "Database"
    file_slug = "database"
    SHOW_FORM = "SHOW DATABASES"
    GET_DDL_TYPE = "DATABASE"
    SUPPORTS_COMMENT = True
    MACRO_BODY = (
        "{% macro define_database(database, raw=None, comment=None, "
        "data_retention_time_in_days=None) %}\n"
        "{%- if raw %}{{ raw }}{%- else %}\n"
        "DEFINE DATABASE {{ database }}\n"
        "{%- if data_retention_time_in_days is not none %}\n"
        "  DATA_RETENTION_TIME_IN_DAYS = {{ data_retention_time_in_days }}\n"
        "{%- endif %}\n"
        "{%- if comment is not none %}\n"
        "  COMMENT='{{ comment }}'\n"
        "{%- endif %}\n"
        ";\n"
        "{%- endif %}\n"
        "{% endmacro %}\n"
    )


plugin = DatabasePlugin()
```

`src/dcmexporter/objects/schema.py`:

```python
"""Schema plugin."""

from __future__ import annotations

from dcmexporter.objects._base import V1ObjectPlugin


class SchemaPlugin(V1ObjectPlugin):
    type_name = "Schema"
    file_slug = "schema"
    SHOW_FORM = "SHOW SCHEMAS"
    GET_DDL_TYPE = "SCHEMA"
    SUPPORTS_COMMENT = True
    MACRO_BODY = (
        "{% macro define_schema(database, schema=None, raw=None, comment=None) %}\n"
        "{%- if raw %}{{ raw }}{%- else %}\n"
        "DEFINE SCHEMA {{ database }}.{{ schema }}\n"
        "{%- if comment is not none %}\n"
        "  COMMENT='{{ comment }}'\n"
        "{%- endif %}\n"
        ";\n"
        "{%- endif %}\n"
        "{% endmacro %}\n"
    )


plugin = SchemaPlugin()
```

`src/dcmexporter/objects/table.py`:

```python
"""Table plugin."""

from __future__ import annotations

from dcmexporter.objects._base import V1ObjectPlugin


class TablePlugin(V1ObjectPlugin):
    type_name = "Table"
    file_slug = "table"
    SHOW_FORM = "SHOW TABLES"
    GET_DDL_TYPE = "TABLE"
    SUPPORTS_COMMENT = True
    MACRO_BODY = (
        "{% macro define_table(database, schema=None, name=None, raw=None, "
        "columns=None, cluster_by=None, data_retention_time_in_days=None, "
        "comment=None, tags=None) %}\n"
        "{%- if raw %}{{ raw }}{%- else %}\n"
        "DEFINE TABLE {{ database }}.{{ schema }}.{{ name }} (\n"
        "{%- for column in columns %}\n"
        "  {{ column.name }} {{ column.type }}{% if not loop.last %},{% endif %}\n"
        "{%- endfor %}\n"
        ")\n"
        "{%- if cluster_by %}\n"
        "  CLUSTER BY ({{ cluster_by | join(', ') }})\n"
        "{%- endif %}\n"
        "{%- if data_retention_time_in_days is not none %}\n"
        "  DATA_RETENTION_TIME_IN_DAYS = {{ data_retention_time_in_days }}\n"
        "{%- endif %}\n"
        "{%- if comment is not none %}\n"
        "  COMMENT='{{ comment }}'\n"
        "{%- endif %}\n"
        ";\n"
        "{%- endif %}\n"
        "{% endmacro %}\n"
    )


plugin = TablePlugin()
```

`src/dcmexporter/objects/view.py`:

```python
"""View plugin (covers regular and secure views)."""

from __future__ import annotations

from dcmexporter.objects._base import V1ObjectPlugin


class ViewPlugin(V1ObjectPlugin):
    type_name = "View"
    file_slug = "view"
    SHOW_FORM = "SHOW VIEWS"
    GET_DDL_TYPE = "VIEW"
    SUPPORTS_COMMENT = True
    MACRO_BODY = (
        "{% macro define_view(database, schema=None, name=None, raw=None, "
        "secure=False, body=None, comment=None) %}\n"
        "{%- if raw %}{{ raw }}{%- else %}\n"
        "DEFINE {% if secure %}SECURE {% endif %}VIEW "
        "{{ database }}.{{ schema }}.{{ name }} AS\n"
        "  {{ body }}\n"
        "{%- if comment is not none %}\n"
        "  COMMENT='{{ comment }}'\n"
        "{%- endif %}\n"
        ";\n"
        "{%- endif %}\n"
        "{% endmacro %}\n"
    )


plugin = ViewPlugin()
```

`src/dcmexporter/objects/sequence.py`:

```python
"""Sequence plugin."""

from __future__ import annotations

from dcmexporter.objects._base import V1ObjectPlugin


class SequencePlugin(V1ObjectPlugin):
    type_name = "Sequence"
    file_slug = "sequence"
    SHOW_FORM = "SHOW SEQUENCES"
    GET_DDL_TYPE = "SEQUENCE"
    SUPPORTS_COMMENT = True
    MACRO_BODY = (
        "{% macro define_sequence(database, schema=None, name=None, raw=None, "
        "start=None, increment=None, comment=None) %}\n"
        "{%- if raw %}{{ raw }}{%- else %}\n"
        "DEFINE SEQUENCE {{ database }}.{{ schema }}.{{ name }}\n"
        "{%- if start is not none %} START = {{ start }}{%- endif %}\n"
        "{%- if increment is not none %} INCREMENT = {{ increment }}{%- endif %}\n"
        "{%- if comment is not none %}\n"
        "  COMMENT='{{ comment }}'\n"
        "{%- endif %}\n"
        ";\n"
        "{%- endif %}\n"
        "{% endmacro %}\n"
    )


plugin = SequencePlugin()
```

`src/dcmexporter/objects/stage.py`:

```python
"""Stage plugin (covers internal and external stages)."""

from __future__ import annotations

from dcmexporter.objects._base import V1ObjectPlugin


class StagePlugin(V1ObjectPlugin):
    type_name = "Stage"
    file_slug = "stage"
    SHOW_FORM = "SHOW STAGES"
    GET_DDL_TYPE = "STAGE"
    SUPPORTS_COMMENT = True
    MACRO_BODY = (
        "{% macro define_stage(database, schema=None, name=None, raw=None, "
        "url=None, storage_integration=None, file_format=None, comment=None) %}\n"
        "{%- if raw %}{{ raw }}{%- else %}\n"
        "DEFINE STAGE {{ database }}.{{ schema }}.{{ name }}\n"
        "{%- if url %} URL='{{ url }}'{%- endif %}\n"
        "{%- if storage_integration %} STORAGE_INTEGRATION = {{ storage_integration }}{%- endif %}\n"
        "{%- if file_format %} FILE_FORMAT = ( {{ file_format }} ){%- endif %}\n"
        "{%- if comment is not none %}\n"
        "  COMMENT='{{ comment }}'\n"
        "{%- endif %}\n"
        ";\n"
        "{%- endif %}\n"
        "{% endmacro %}\n"
    )


plugin = StagePlugin()
```

`src/dcmexporter/objects/file_format.py`:

```python
"""File format plugin."""

from __future__ import annotations

from dcmexporter.objects._base import V1ObjectPlugin


class FileFormatPlugin(V1ObjectPlugin):
    type_name = "File format"
    file_slug = "file_format"
    SHOW_FORM = "SHOW FILE FORMATS"
    GET_DDL_TYPE = "FILE_FORMAT"
    SUPPORTS_COMMENT = True
    MACRO_BODY = (
        "{% macro define_file_format(database, schema=None, name=None, raw=None, "
        "type=None, options=None, comment=None) %}\n"
        "{%- if raw %}{{ raw }}{%- else %}\n"
        "DEFINE FILE FORMAT {{ database }}.{{ schema }}.{{ name }}\n"
        "{%- if type %} TYPE = {{ type }}{%- endif %}\n"
        "{%- if options %}\n"
        "  {%- for k, v in options.items() %}  {{ k }} = {{ v }}{% endfor %}\n"
        "{%- endif %}\n"
        "{%- if comment is not none %}\n"
        "  COMMENT='{{ comment }}'\n"
        "{%- endif %}\n"
        ";\n"
        "{%- endif %}\n"
        "{% endmacro %}\n"
    )


plugin = FileFormatPlugin()
```

`src/dcmexporter/objects/tag.py`:

```python
"""Tag plugin."""

from __future__ import annotations

from dcmexporter.objects._base import V1ObjectPlugin


class TagPlugin(V1ObjectPlugin):
    type_name = "Tag"
    file_slug = "tag"
    SHOW_FORM = "SHOW TAGS"
    GET_DDL_TYPE = "TAG"
    SUPPORTS_COMMENT = True
    MACRO_BODY = (
        "{% macro define_tag(database, schema=None, name=None, raw=None, "
        "allowed_values=None, comment=None) %}\n"
        "{%- if raw %}{{ raw }}{%- else %}\n"
        "DEFINE TAG {{ database }}.{{ schema }}.{{ name }}\n"
        "{%- if allowed_values %}\n"
        "  ALLOWED_VALUES {% for v in allowed_values %}'{{ v }}'"
        "{% if not loop.last %}, {% endif %}{% endfor %}\n"
        "{%- endif %}\n"
        "{%- if comment is not none %}\n"
        "  COMMENT='{{ comment }}'\n"
        "{%- endif %}\n"
        ";\n"
        "{%- endif %}\n"
        "{% endmacro %}\n"
    )


plugin = TagPlugin()
```

`src/dcmexporter/objects/warehouse.py`:

```python
"""Warehouse plugin."""

from __future__ import annotations

from dcmexporter.objects._base import V1ObjectPlugin


class WarehousePlugin(V1ObjectPlugin):
    type_name = "Warehouse"
    file_slug = "warehouse"
    SHOW_FORM = "SHOW WAREHOUSES"
    GET_DDL_TYPE = "WAREHOUSE"
    SUPPORTS_COMMENT = True
    MACRO_BODY = (
        "{% macro define_warehouse(database=None, name=None, raw=None, "
        "warehouse_size=None, auto_suspend=None, auto_resume=None, comment=None) %}\n"
        "{%- if raw %}{{ raw }}{%- else %}\n"
        "DEFINE WAREHOUSE {{ name }}\n"
        "{%- if warehouse_size %} WAREHOUSE_SIZE = '{{ warehouse_size }}'{%- endif %}\n"
        "{%- if auto_suspend is not none %} AUTO_SUSPEND = {{ auto_suspend }}{%- endif %}\n"
        "{%- if auto_resume is not none %} AUTO_RESUME = {{ auto_resume }}{%- endif %}\n"
        "{%- if comment is not none %}\n"
        "  COMMENT='{{ comment }}'\n"
        "{%- endif %}\n"
        ";\n"
        "{%- endif %}\n"
        "{% endmacro %}\n"
    )

    def discover(
        self, cursor, database, schemas
    ):  # type: ignore[override]
        # Warehouses are account-level, not database-level.
        cursor.execute("SHOW WAREHOUSES")
        rows = cursor.fetchall()
        from dcmexporter.types import FQN

        out: list[FQN] = []
        for row in rows:
            name = row["name"] if isinstance(row, dict) else row[0]
            out.append(FQN(database=database, schema=None, name=name))
        return sorted(out, key=lambda f: f.name)


plugin = WarehousePlugin()
```

- [ ] **Step 5: Implement the unimplemented plugins**

`src/dcmexporter/objects/_unimplemented.py`:

```python
"""Stub plugins for DCM types that are not yet supported by dcmexporter."""

from __future__ import annotations

from typing import Any

from dcmexporter.plugin import ObjectPlugin
from dcmexporter.types import UNIMPLEMENTED_TYPES, FQN


def _slug(name: str) -> str:
    return name.lower().replace(" ", "_")


class _UnimplementedPlugin(ObjectPlugin):
    def __init__(self, type_name: str) -> None:
        self.type_name = type_name
        self.file_slug = _slug(type_name)

    def discover(
        self, cursor: Any, database: str, schemas: tuple[str, ...] | None
    ) -> list[FQN]:
        raise NotImplementedError(
            f"{self.type_name} is in DCM's supported set but not yet implemented "
            "by dcmexporter"
        )

    def get_ddl(self, cursor: Any, fqn: FQN) -> str:
        raise NotImplementedError(self.type_name)

    def to_define_and_invocation(
        self, ddl: str, *, comment: str | None, use_macros: bool, database: str
    ) -> str:
        raise NotImplementedError(self.type_name)

    def macro_definition(self) -> str:
        raise NotImplementedError(self.type_name)


unimplemented_plugins = [_UnimplementedPlugin(t) for t in UNIMPLEMENTED_TYPES]
```

- [ ] **Step 6: Implement auto-discovery**

`src/dcmexporter/objects/__init__.py`:

```python
"""Auto-discovered Snowflake DCM object plugins."""

from __future__ import annotations

import importlib
import pkgutil

from dcmexporter.plugin import PluginRegistry


def build_registry() -> PluginRegistry:
    registry = PluginRegistry()
    package = importlib.import_module(__name__)
    for _importer, module_name, _ispkg in pkgutil.iter_modules(package.__path__):
        if module_name.startswith("_"):
            # _unimplemented carries a list, _base is just shared code.
            if module_name == "_unimplemented":
                module = importlib.import_module(f"{__name__}.{module_name}")
                for plugin in module.unimplemented_plugins:
                    registry.register(plugin)
            continue
        module = importlib.import_module(f"{__name__}.{module_name}")
        if hasattr(module, "plugin"):
            registry.register(module.plugin)
    return registry
```

- [ ] **Step 7: Write per-plugin tests (one file each)**

Each follows the same template. Example: `tests/test_objects/test_table.py`:

```python
"""Tests for the Table plugin."""

from __future__ import annotations

from unittest.mock import MagicMock

import jinja2

from dcmexporter.objects.table import plugin
from dcmexporter.types import FQN


def test_discover_uses_show_tables_in_database() -> None:
    cursor = MagicMock()
    cursor.fetchall.return_value = [
        {"name": "T1", "schema_name": "PUBLIC"},
        {"name": "T2", "schema_name": "PUBLIC"},
    ]
    out = plugin.discover(cursor, "MYDB", None)
    cursor.execute.assert_called_once_with("SHOW TABLES IN DATABASE MYDB")
    assert [str(f) for f in out] == ["MYDB.PUBLIC.T1", "MYDB.PUBLIC.T2"]


def test_discover_filters_by_schema() -> None:
    cursor = MagicMock()
    cursor.fetchall.return_value = [{"name": "T", "schema_name": "S"}]
    plugin.discover(cursor, "MYDB", ("S",))
    cursor.execute.assert_called_once_with("SHOW TABLES IN SCHEMA MYDB.S")


def test_get_ddl_calls_get_ddl_function() -> None:
    cursor = MagicMock()
    cursor.fetchone.return_value = ["CREATE OR REPLACE TABLE MYDB.PUBLIC.T (X INT)"]
    fqn = FQN("MYDB", "PUBLIC", "T")
    out = plugin.get_ddl(cursor, fqn)
    cursor.execute.assert_called_once_with(
        "SELECT GET_DDL('TABLE', 'MYDB.PUBLIC.T')"
    )
    assert out.startswith("CREATE")


def test_to_define_and_invocation_macro_mode() -> None:
    out = plugin.to_define_and_invocation(
        "CREATE OR REPLACE TABLE MYDB.PUBLIC.T (X INT)",
        comment="hi",
        use_macros=True,
        database="MYDB",
    )
    assert out.startswith("{{ define_table(")
    assert "raw=" in out


def test_to_define_and_invocation_raw_mode() -> None:
    out = plugin.to_define_and_invocation(
        "CREATE OR REPLACE TABLE MYDB.PUBLIC.T (X INT)",
        comment=None,
        use_macros=False,
        database="MYDB",
    )
    assert out.upper().startswith("DEFINE TABLE")
    assert "{{ database }}.PUBLIC.T" in out


def test_macro_definition_is_valid_jinja() -> None:
    env = jinja2.Environment()
    env.parse(plugin.macro_definition())
```

Repeat the same pattern for each remaining plugin (`test_database.py`, `test_schema.py`, `test_view.py`, `test_sequence.py`, `test_stage.py`, `test_file_format.py`, `test_tag.py`, `test_warehouse.py`). For each, adapt:
- the SHOW string asserted in `test_discover_uses_show_<type>_in_database`
- the GET_DDL type literal asserted in `test_get_ddl_calls_get_ddl_function`
- the macro name asserted in `test_to_define_and_invocation_macro_mode`
- the DEFINE keyword asserted in `test_to_define_and_invocation_raw_mode`

For the `warehouse` plugin only: discovery does not include `IN DATABASE`, so the test asserts `cursor.execute.assert_called_once_with("SHOW WAREHOUSES")` and the rows shape uses `name` only. Schemas argument is ignored.

- [ ] **Step 8: Run all object tests, expect pass**

Run: `uv run pytest tests/test_objects/ -v`
Expected: all per-plugin tests pass + registry tests pass.

- [ ] **Step 9: Commit**

```bash
git add src/dcmexporter/objects/ tests/test_objects/
git commit -m "feat(objects): v1 plugins (database/schema/table/view/sequence/stage/file_format/tag/warehouse)"
```

---

## Task 13: Orchestrator + end-to-end golden test

**Files:**
- Create: `src/dcmexporter/orchestrator.py`
- Create: `tests/test_orchestrator.py`
- Create: `tests/golden/out/manifest.yml`
- Create: `tests/golden/out/Makefile`
- Create: `tests/golden/out/sources/definitions/<each>.sql`
- Create: `tests/golden/out/sources/macros/<each>.sql`

- [ ] **Step 1: Write the failing test**

`tests/test_orchestrator.py`:

```python
"""End-to-end orchestrator test against a fully mocked cursor."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from dcmexporter.config import Config
from dcmexporter.orchestrator import export
from dcmexporter.types import V1_TYPES


def _cfg(out_folder: Path) -> Config:
    return Config(
        database="MYDB",
        schemas=(),
        connection=None,
        targets=("staging",),
        default_target="staging",
        templating_defaults=(),
        configurations=("STAGING",),
        templating_configuration_keys=("environment",),
        includes=("Table",),  # narrow surface for golden test
        excludes=(),
        comment="exported by dcmexporter",
        use_macros=True,
        out_folder=out_folder,
        force=True,
    )


def test_export_writes_full_layout(tmp_path: Path) -> None:
    out = tmp_path / "out"

    fake_cursor = MagicMock()
    fake_conn = MagicMock()
    fake_conn.account = "AB12345"
    fake_conn.cursor.return_value = fake_cursor

    def execute_side_effect(sql, *args, **kwargs):
        fake_cursor._last_sql = sql

    def fetchall_side_effect():
        if "SHOW TABLES" in fake_cursor._last_sql:
            return [{"name": "T1", "schema_name": "PUBLIC"}]
        return []

    def fetchone_side_effect():
        if "GET_DDL" in fake_cursor._last_sql:
            return ["CREATE OR REPLACE TABLE MYDB.PUBLIC.T1 (X INT)"]
        return None

    fake_cursor.execute.side_effect = execute_side_effect
    fake_cursor.fetchall.side_effect = fetchall_side_effect
    fake_cursor.fetchone.side_effect = fetchone_side_effect

    with patch("dcmexporter.orchestrator.open_connection") as oc:
        oc.return_value = fake_conn
        code = export(_cfg(out))

    assert code == 0
    assert (out / "manifest.yml").exists()
    assert (out / "Makefile").exists()
    assert (out / "sources" / "definitions" / "table.sql").exists()
    assert (out / "sources" / "macros" / "table.sql").exists()

    table_sql = (out / "sources" / "definitions" / "table.sql").read_text()
    assert "{{ define_table(" in table_sql
    assert "{{ database }}.PUBLIC.T1" in table_sql

    manifest = (out / "manifest.yml").read_text()
    assert "STAGING:" in manifest
    assert "database: MYDB" in manifest
    assert "templating_config: staging" in manifest


def test_export_per_object_get_ddl_failure_continues(tmp_path: Path, capsys) -> None:
    out = tmp_path / "out"
    fake_cursor = MagicMock()
    fake_conn = MagicMock()
    fake_conn.account = "AB12345"
    fake_conn.cursor.return_value = fake_cursor

    def execute_side_effect(sql, *args, **kwargs):
        fake_cursor._last_sql = sql
        if "GET_DDL" in sql and "T_BAD" in sql:
            raise RuntimeError("permission denied")

    def fetchall_side_effect():
        if "SHOW TABLES" in fake_cursor._last_sql:
            return [
                {"name": "T_OK", "schema_name": "PUBLIC"},
                {"name": "T_BAD", "schema_name": "PUBLIC"},
            ]
        return []

    def fetchone_side_effect():
        if "GET_DDL" in fake_cursor._last_sql:
            return ["CREATE OR REPLACE TABLE MYDB.PUBLIC.T_OK (X INT)"]
        return None

    fake_cursor.execute.side_effect = execute_side_effect
    fake_cursor.fetchall.side_effect = fetchall_side_effect
    fake_cursor.fetchone.side_effect = fetchone_side_effect

    with patch("dcmexporter.orchestrator.open_connection") as oc:
        oc.return_value = fake_conn
        code = export(_cfg(out))

    assert code == 0
    err = capsys.readouterr().err
    assert "T_BAD" in err
    body = (out / "sources" / "definitions" / "table.sql").read_text()
    assert "T_OK" in body
    assert "T_BAD" not in body


def test_export_no_objects_returns_4_when_errors(tmp_path: Path) -> None:
    out = tmp_path / "out"
    fake_cursor = MagicMock()
    fake_conn = MagicMock()
    fake_conn.account = "AB12345"
    fake_conn.cursor.return_value = fake_cursor

    def execute_side_effect(sql, *args, **kwargs):
        fake_cursor._last_sql = sql
        if "GET_DDL" in sql:
            raise RuntimeError("denied")

    fake_cursor.execute.side_effect = execute_side_effect
    fake_cursor.fetchall.side_effect = lambda: (
        [{"name": "T", "schema_name": "PUBLIC"}] if "SHOW TABLES" in fake_cursor._last_sql else []
    )
    fake_cursor.fetchone.side_effect = lambda: None

    with patch("dcmexporter.orchestrator.open_connection") as oc:
        oc.return_value = fake_conn
        code = export(_cfg(out))

    assert code == 4
```

- [ ] **Step 2: Run, expect failure**

Run: `uv run pytest tests/test_orchestrator.py -v`
Expected: ImportError on `dcmexporter.orchestrator`.

- [ ] **Step 3: Implement `src/dcmexporter/orchestrator.py`**

```python
"""Glue layer that runs an end-to-end export."""

from __future__ import annotations

import sys
from typing import Any

from dcmexporter.config import Config, filter_types
from dcmexporter.connection import open_connection, resolve_account_identifier
from dcmexporter.makefile import render_makefile
from dcmexporter.manifest import render_manifest
from dcmexporter.objects import build_registry
from dcmexporter.render import OutFolderError, write_outputs
from dcmexporter.types import V1_TYPES


def export(cfg: Config) -> int:
    registry = build_registry()
    account_identifier = ""
    conn: Any | None = None

    try:
        conn = open_connection(cfg.connection)
        account_identifier = resolve_account_identifier(conn)
        cursor = conn.cursor()

        type_names = filter_types(cfg)
        definitions: dict[str, str] = {}
        macros: dict[str, str] | None = {} if cfg.use_macros else None

        exported = 0
        errors = 0
        for type_name in type_names:
            if type_name not in V1_TYPES:
                # known-supported but unimplemented -> skip silently
                if not cfg.includes:
                    print(
                        f"[dcmexporter] skipping unsupported type: {type_name}",
                        file=sys.stderr,
                    )
                continue
            plugin = registry.get(type_name)

            try:
                fqns = plugin.discover(cursor, cfg.database, cfg.schemas or None)
            except Exception as exc:  # noqa: BLE001
                print(
                    f"[dcmexporter] discover failed for {type_name}: {exc}",
                    file=sys.stderr,
                )
                errors += 1
                continue

            blocks: list[str] = []
            for fqn in fqns:
                try:
                    ddl = plugin.get_ddl(cursor, fqn)
                    block = plugin.to_define_and_invocation(
                        ddl,
                        comment=cfg.comment,
                        use_macros=cfg.use_macros,
                        database=cfg.database,
                    )
                except Exception as exc:  # noqa: BLE001
                    print(
                        f"[dcmexporter] type={type_name} fqn={fqn} error={exc}",
                        file=sys.stderr,
                    )
                    errors += 1
                    continue
                blocks.append(block)
                exported += 1

            definitions[plugin.file_slug] = "\n".join(blocks)
            if macros is not None:
                macros[plugin.file_slug] = plugin.macro_definition()

        manifest = render_manifest(cfg, account_identifier=account_identifier)
        makefile = render_makefile(cfg)
        try:
            write_outputs(
                out_folder=cfg.out_folder,
                manifest=manifest,
                makefile=makefile,
                definitions=definitions,
                macros=macros,
                force=cfg.force,
            )
        except OutFolderError as exc:
            print(f"[dcmexporter] {exc}", file=sys.stderr)
            return 5

        if cfg.templating_configuration_keys and cfg.configurations:
            keys = ", ".join(cfg.templating_configuration_keys)
            print(
                f"[dcmexporter] reminder: fill values for keys [{keys}] "
                "under each configuration in manifest.yml",
                file=sys.stderr,
            )

        print(
            f"[dcmexporter] exported={exported} errors={errors}",
            file=sys.stderr,
        )

        if exported == 0 and errors > 0:
            return 4
        return 0
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass
```

- [ ] **Step 4: Run, expect pass**

Run: `uv run pytest tests/test_orchestrator.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/dcmexporter/orchestrator.py tests/test_orchestrator.py
git commit -m "feat(orchestrator): end-to-end export pipeline"
```

---

## Task 14: Full-suite smoke run + lint/type checks

**Files:** none (verification task)

- [ ] **Step 1: Run the whole suite**

Run: `uv run pytest tests/ -v`
Expected: all tests pass.

- [ ] **Step 2: Run ruff format check**

Run: `uv run ruff format --check src/ tests/`
Expected: passes (no diffs). If it fails, run `uv run ruff format src/ tests/` and re-check.

- [ ] **Step 3: Run ruff check**

Run: `uv run ruff check src/ tests/`
Expected: passes. Fix any lint findings inline.

- [ ] **Step 4: Run mypy**

Run: `uv run mypy src/`
Expected: passes. Add explicit annotations where mypy complains; do NOT add `# type: ignore` unless absolutely needed.

- [ ] **Step 5: Install pre-commit hooks locally**

Run: `uv run pre-commit install`
Expected: pre-commit hook installed in `.git/hooks/pre-commit`.

- [ ] **Step 6: Commit any formatting/lint fixups (if any)**

```bash
git add -u
git commit -m "chore: full-suite lint/type fixup" || echo "no changes"
```

---

## Task 15: GitHub Actions CI

**Files:**
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: Create the workflow**

`.github/workflows/ci.yml`:

```yaml
name: CI

on:
  push:
    branches: [main]
  workflow_dispatch:
    inputs:
      release_notes:
        description: "Text to prepend to the GitHub release notes"
        required: false
        default: ""

jobs:
  test:
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, macos-latest, windows-latest]
        python-version: ["3.10", "3.11", "3.12", "3.13", "3.14"]
    runs-on: ${{ matrix.os }}

    steps:
      - uses: actions/checkout@v6

      - name: Install uv
        uses: astral-sh/setup-uv@v8.1.0
        with:
          enable-cache: true

      - name: Set up Python
        run: uv python install ${{ matrix.python-version }}

      - name: Install dependencies
        run: uv sync --all-extras --python ${{ matrix.python-version }}

      - name: Ruff format
        run: uv run --python ${{ matrix.python-version }} ruff format --check src/ tests/

      - name: Ruff check
        run: uv run --python ${{ matrix.python-version }} ruff check src/ tests/

      - name: Run tests
        run: uv run --python ${{ matrix.python-version }} pytest tests/ -v

  build:
    needs: test
    runs-on: ubuntu-latest
    outputs:
      version: ${{ steps.stamp.outputs.version }}

    steps:
      - uses: actions/checkout@v6

      - name: Install uv
        uses: astral-sh/setup-uv@v8.1.0
        with:
          enable-cache: true

      - name: Set up Python
        run: uv python install 3.12

      - name: Install dependencies
        run: uv sync --all-extras

      - name: Stamp version
        id: stamp
        env:
          RUN_NUMBER: ${{ github.run_number }}
        run: |
          python - <<'PY'
          import os, re, pathlib
          path = pathlib.Path("pyproject.toml")
          text = path.read_text()
          match = re.search(r'^version = "(\d+\.\d+)"', text, re.MULTILINE)
          if not match:
              raise SystemExit("pyproject.toml must contain 'version = \"MAJOR.MINOR\"'")
          base = match.group(1)
          full = f'{base}.{os.environ["RUN_NUMBER"]}'
          path.write_text(
              re.sub(
                  r'^version = "\d+\.\d+"',
                  f'version = "{full}"',
                  text,
                  count=1,
                  flags=re.MULTILINE,
              )
          )
          print(f"Stamped version: {full}")
          with open(os.environ["GITHUB_OUTPUT"], "a") as fh:
              fh.write(f"version={full}\n")
          PY

      - name: Build sdist and wheel
        run: uv build

      - name: Upload build artifacts
        uses: actions/upload-artifact@v7
        with:
          name: dist
          path: dist/
          if-no-files-found: error

  publish:
    needs: build
    if: github.event_name == 'workflow_dispatch'
    runs-on: ubuntu-latest
    environment: pypi
    permissions:
      id-token: write

    steps:
      - name: Download build artifacts
        uses: actions/download-artifact@v8
        with:
          name: dist
          path: dist/

      - name: Publish to PyPI
        uses: pypa/gh-action-pypi-publish@release/v1

  release:
    needs: [build, publish]
    if: github.event_name == 'workflow_dispatch'
    runs-on: ubuntu-latest
    permissions:
      contents: write

    steps:
      - uses: actions/checkout@v6

      - name: Download build artifacts
        uses: actions/download-artifact@v8
        with:
          name: dist
          path: dist/

      - name: Create GitHub release
        env:
          GH_TOKEN: ${{ github.token }}
          VERSION: ${{ needs.build.outputs.version }}
          RELEASE_NOTES: ${{ inputs.release_notes }}
        run: |
          pypi_line="Published to PyPI: https://pypi.org/project/dcmexporter/${VERSION}/"
          if [ -n "${RELEASE_NOTES}" ]; then
            notes="${RELEASE_NOTES}"$'\n\n'"${pypi_line}"
          else
            notes="${pypi_line}"
          fi
          gh release create "v${VERSION}" \
            --target "${GITHUB_SHA}" \
            --title "v${VERSION}" \
            --notes "${notes}" \
            dist/*
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: GitHub Actions matrix + PyPI publish on workflow_dispatch"
```

---

## Self-Review

- **Spec coverage:**
  - §2 CLI surface: covered by Task 4. Every flag has a test.
  - §3 architecture: every layer has its own task (1 scaffolding, 5 plugin ABC, 6 connection, 7+8 rewriter, 9 manifest, 10 makefile, 11 render, 12 plugins, 13 orchestrator).
  - §4.1 manifest shape (with/without configurations): Task 9.
  - §4.2 Makefile shape: Task 10.
  - §4.3 macros vs raw mode: Task 12 (per plugin) + Task 13 (end-to-end golden test).
  - §4.4 database parameterisation: Task 8.
  - §5 v1 scope + unimplemented stubs: Task 12.
  - §6 error handling: CLI errors in Task 4, OutFolderError in Task 11, per-object continuation + exit code 4 in Task 13.
  - §7 testing: every task pairs implementation with tests; orchestrator end-to-end in Task 13.
  - §8 packaging + CI: Tasks 1 + 15.
- **Placeholder scan:** every step contains the actual code or command needed. No "TODO" or "similar to Task N".
- **Type consistency:** `Config` field names match across Tasks 3, 4, 9, 10, 13. `ObjectPlugin` signature in Task 5 matches its use in Tasks 12 and 13. `FQN` from Task 2 used identically in plugin code. `parameterise_database` / `render_macro_invocation` from Task 8 imported by Task 12. `OutFolderError` from Task 11 caught in Task 13.
- **Notes carried forward to implementation:**
  - Task 12's per-plugin tests cover all nine v1 plugins. Use the `test_table.py` template; only the SHOW string, GET_DDL type literal, macro name, and DEFINE keyword change between files. The warehouse test additionally drops the `IN DATABASE` assertion.
  - Real `snow dcm` apply subcommand name (`execute` vs `apply`) is currently `execute` in Task 10. Confirm against current Snowflake docs before merging Task 10; flip the Makefile string if needed.
