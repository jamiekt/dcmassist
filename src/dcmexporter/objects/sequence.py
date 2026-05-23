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
