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

from dcmexporter.plugin import ObjectPlugin, ProgressCallback
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
        self,
        cursor: Any,
        database: str,
        schemas: tuple[str, ...] | None,
        progress: ProgressCallback | None = None,
    ) -> list[FQN]:
        if not self.SHOW_FORM:
            raise NotImplementedError(self.type_name)

        target_schemas = sorted(self._target_schemas(cursor, database, schemas))
        total = len(target_schemas)

        rows: list[FQN] = []
        for index, schema in enumerate(target_schemas, start=1):
            if progress is not None:
                count = f" {index}/{total}" if total > 1 else ""
                progress(f"discovering {self.type_name}s in{count} {database}.{schema}")
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

    def get_ddl(self, cursor: Any, fqn: FQN) -> str:
        cursor.execute(f"SELECT GET_DDL('{self.GET_DDL_TYPE}', '{fqn}')")
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
        invocation = render_macro_invocation(f"define_{self.file_slug}", kwargs=kwargs)
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
