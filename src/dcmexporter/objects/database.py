"""Database plugin."""

from __future__ import annotations

from typing import Any

from dcmexporter.objects._base import V1ObjectPlugin
from dcmexporter.plugin import ProgressCallback
from dcmexporter.types import FQN


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

    def discover(
        self,
        cursor: Any,
        database: str,
        schemas: tuple[str, ...] | None,
        progress: ProgressCallback | None = None,
    ) -> list[FQN]:
        # Database is account-level: SHOW DATABASES has no IN DATABASE clause.
        # The --schema filter is meaningless here.
        cursor.execute(f"SHOW DATABASES LIKE '{database}'")
        return [
            FQN(database=database, schema=None, name=row["name"])
            for row in cursor.fetchall()
        ]


plugin = DatabasePlugin()
