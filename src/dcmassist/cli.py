"""dcmassist CLI."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import click

from dcmassist.config import (
    Config,
    parse_templating_default,
    resolve_default_target,
    validate_config,
)


def run_export(cfg: Config) -> int:
    """Run the export. Replaced in tests; wired to orchestrator in Task 13."""
    from dcmassist.orchestrator import export  # type: ignore[import-untyped]

    return export(cfg)


def _default_comment() -> str:
    return (
        "Definition exported by https://github.com/jamiekt/dcmassist on "
        f"{date.today().isoformat()}"
    )


@click.group()
@click.version_option()
def cli() -> None:
    """dcmassist — export Snowflake object definitions for DCM projects."""


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
    default=False,
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
