"""Glue layer that runs an end-to-end export."""

from __future__ import annotations

import dataclasses
import sys
from typing import Any

from dcmassist.chunking import (
    OBJECTS_PER_FILE_ENV,
    chunk_blocks,
    resolve_objects_per_file,
)
from dcmassist.config import Config, filter_types
from dcmassist.connection import open_connection, resolve_account_identifier
from dcmassist.log import RunLog
from dcmassist.makefile import render_makefile
from dcmassist.manifest import render_manifest
from dcmassist.objects import build_registry
from dcmassist.objects._show_paging import paginated_show
from dcmassist.render import OutFolderError, prepare_out_folder, write_outputs
from dcmassist.status import StatusDashboard
from dcmassist.types import V1_TYPES


def export(cfg: Config) -> int:
    registry = build_registry()
    try:
        objects_per_file = resolve_objects_per_file()
    except ValueError as exc:
        print(f"[dcmassist] {exc}", file=sys.stderr)
        return 5
    account_identifier = ""
    conn: Any | None = None
    log: RunLog | None = None

    try:
        try:
            prepare_out_folder(cfg.out_folder, force=cfg.force)
        except OutFolderError as exc:
            print(f"[dcmassist] {exc}", file=sys.stderr)
            return 5

        log = RunLog(cfg.out_folder / "dcmassist-export.log")
        log.info("export starting")
        for field in dataclasses.fields(cfg):
            log.info(f"  {field.name}={getattr(cfg, field.name)!r}")
        log.info(f"  {OBJECTS_PER_FILE_ENV}={objects_per_file}")

        with StatusDashboard(stream=sys.stderr) as status:
            status.set_database(cfg.database)
            status.set_now("connecting to Snowflake...")
            conn = open_connection(cfg.connection)
            account_identifier = resolve_account_identifier(conn)
            cursor = conn.cursor()
            log.info(f"connected to Snowflake account={account_identifier}")

            known_schemas = _list_schemas(cursor, cfg.database)
            log.info(f"known schemas: {sorted(known_schemas)}")
            known_functions, ambiguous = _list_functions(cursor, cfg.database)
            log.info(f"known unambiguous callables: {len(known_functions)}")
            for name in sorted(ambiguous):
                log.warn(
                    f"callable {name!r} exists in multiple schemas; "
                    "view bodies that reference it bare will not be auto-qualified"
                )

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
                            f"[dcmassist] skipping unsupported type: {type_name}"
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
                    status.log(f"[dcmassist] discover failed for {type_name}: {exc}")
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
                            known_schemas=known_schemas,
                            known_functions=known_functions,
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
                f"[dcmassist] reminder: fill values for keys [{keys}] "
                "under each configuration in manifest.yml",
                file=sys.stderr,
            )

        log.info(
            f"export finished exported={exported} errors={errors} "
            f"skipped_missing={skipped_missing}"
        )
        summary = f"[dcmassist] exported={exported} errors={errors}"
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


def _list_schemas(cursor: Any, database: str) -> frozenset[str]:
    """Return the set of schema names in `database`, used to qualify bare
    2-part references inside view bodies (see view.py). INFORMATION_SCHEMA
    is included — it's a legal target — but the result is consumed only as
    a recognition set, not as enumeration."""
    rows = paginated_show(cursor, f"SHOW SCHEMAS IN DATABASE {database}")
    return frozenset(row["name"] for row in rows)


def _list_functions(
    cursor: Any, database: str
) -> tuple[dict[str, str], frozenset[str]]:
    """Build a name→schema map of unambiguous user functions and procedures
    in `database`, used to qualify bare 1-part function calls in view bodies
    (see view.py). Names that exist in more than one schema are returned
    separately so the orchestrator can warn about them — we can't pick the
    correct schema without resolving the search path the view was created
    under, and a wrong guess would silently produce wrong DDL."""
    schemas_by_name: dict[str, set[str]] = {}
    for show_form in ("SHOW USER FUNCTIONS", "SHOW PROCEDURES"):
        try:
            rows = paginated_show(cursor, f"{show_form} IN DATABASE {database}")
        except Exception:  # noqa: BLE001
            # Some Snowflake editions / role grants reject one of these forms.
            # Missing one is non-fatal; we just won't qualify those callables.
            continue
        for row in rows:
            # SHOW USER FUNCTIONS / SHOW PROCEDURES return `name` (callable
            # name) and `schema_name`. Names are case-sensitive in Snowflake
            # but identifiers are uppercased unless quoted; key the map upper
            # to match the case-insensitive regex match in the rewriter.
            name = str(row["name"]).upper()
            schema = str(row["schema_name"])
            schemas_by_name.setdefault(name, set()).add(schema)

    known: dict[str, str] = {}
    ambiguous: set[str] = set()
    for name, schemas in schemas_by_name.items():
        if len(schemas) == 1:
            known[name] = next(iter(schemas))
        else:
            ambiguous.add(name)
    return known, frozenset(ambiguous)


def _counts_by_schema(fqns: list[Any]) -> list[tuple[str, int]]:
    """Group discovered FQNs by schema name and return (schema, count) sorted by schema.

    Database-level objects (schema is None) bucket under '<database>' so the
    log breakdown still accounts for them.
    """
    counts: dict[str, int] = {}
    for fqn in fqns:
        key = fqn.schema if fqn.schema else f"<{fqn.database}>"
        counts[key] = counts.get(key, 0) + 1
    return sorted(counts.items())


def _is_missing_or_unauthorized(exc: BaseException) -> bool:
    """True for the very common Snowflake error 002003: object missing or
    insufficient privileges. We treat this as a non-fatal skip so a couple of
    inaccessible objects don't tank the whole export."""
    text = str(exc)
    if "002003" in text:
        return True
    return "does not exist or not authorized" in text.lower()
