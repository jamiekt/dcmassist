"""Schema plugin."""

from __future__ import annotations

from typing import Any

from dcmexporter.objects._base import V1ObjectPlugin
from dcmexporter.objects._schema_ddl import (
    SchemaNotExportable,
    synthesize_schema_ddl,
)
from dcmexporter.plugin import ProgressCallback
from dcmexporter.types import FQN


class SchemaPlugin(V1ObjectPlugin):
    type_name = "Schema"
    file_slug = "schema"
    SHOW_FORM = "SHOW SCHEMAS"
    # GET_DDL_TYPE retained for symmetry; unused. GET_DDL('SCHEMA', ...) is
    # recursive and unworkable on busy schemas — see _schema_ddl.py.
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

    def discover(
        self,
        cursor: Any,
        database: str,
        schemas: tuple[str, ...] | None,
        progress: ProgressCallback | None = None,
    ) -> list[FQN]:
        # SHOW SCHEMAS returns `name` (schema) and `database_name`; there is no
        # `schema_name`. The schema's FQN is db.schema.schema since the schema's
        # name is its own schema component.
        rows: list[dict[str, Any]] = []
        if schemas:
            # Snowflake LIKE doesn't accept arbitrary lists; enumerate explicitly.
            total = len(schemas)
            for index, name in enumerate(schemas, start=1):
                if progress is not None:
                    count = f" {index}/{total}" if total > 1 else ""
                    progress(f"discovering Schema{count} {database}.{name}")
                cursor.execute(f"SHOW SCHEMAS LIKE '{name}' IN DATABASE {database}")
                rows.extend(cursor.fetchall())
        else:
            cursor.execute(f"SHOW SCHEMAS IN DATABASE {database}")
            rows.extend(
                row for row in cursor.fetchall() if row["name"] != "INFORMATION_SCHEMA"
            )

        out = [
            FQN(database=database, schema=row["name"], name=row["name"]) for row in rows
        ]
        return sorted(out, key=lambda f: f.name)

    def get_ddl(self, cursor: Any, fqn: FQN) -> str:
        # Synthesize from SHOW rather than GET_DDL: GET_DDL('SCHEMA', ...) is
        # recursive over every contained object. See _schema_ddl.py.
        cursor.execute(f"SHOW SCHEMAS LIKE '{fqn.name}' IN DATABASE {fqn.database}")
        rows = cursor.fetchall()
        if not rows:
            raise SchemaNotExportable(
                f"schema {fqn}: SHOW SCHEMAS LIKE returned no rows"
            )
        return synthesize_schema_ddl(fqn, rows[0])


plugin = SchemaPlugin()
