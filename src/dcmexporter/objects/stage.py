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
