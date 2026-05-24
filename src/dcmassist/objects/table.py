"""Table plugin."""

from __future__ import annotations

from dcmassist.objects._base import V1ObjectPlugin


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
