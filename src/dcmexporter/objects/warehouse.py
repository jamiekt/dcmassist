"""Warehouse plugin."""

from __future__ import annotations

from typing import Any

from dcmexporter.objects._base import V1ObjectPlugin
from dcmexporter.plugin import ProgressCallback
from dcmexporter.types import FQN


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
        self,
        cursor: Any,
        database: str,
        schemas: tuple[str, ...] | None,
        progress: ProgressCallback | None = None,
    ) -> list[FQN]:
        # Warehouses are account-level; the schemas filter is meaningless here.
        cursor.execute("SHOW WAREHOUSES")
        rows = cursor.fetchall()
        out = [FQN(database=database, schema=None, name=row["name"]) for row in rows]
        return sorted(out, key=lambda f: f.name)


plugin = WarehousePlugin()
