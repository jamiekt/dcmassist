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
