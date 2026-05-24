"""File format plugin."""

from __future__ import annotations

from dcmassist.objects._base import V1ObjectPlugin


class FileFormatPlugin(V1ObjectPlugin):
    type_name = "File format"
    file_slug = "file_format"
    SHOW_FORM = "SHOW FILE FORMATS"
    GET_DDL_TYPE = "FILE_FORMAT"
    SUPPORTS_COMMENT = True
    MACRO_BODY = (
        "{% macro define_file_format(database, schema=None, name=None, raw=None, "
        "type=None, options=None, comment=None) %}\n"
        "{%- if raw %}{{ raw }}{%- else %}\n"
        "DEFINE FILE FORMAT {{ database }}.{{ schema }}.{{ name }}\n"
        "{%- if type %} TYPE = {{ type }}{%- endif %}\n"
        "{%- if options %}\n"
        "  {%- for k, v in options.items() %}  {{ k }} = {{ v }}{% endfor %}\n"
        "{%- endif %}\n"
        "{%- if comment is not none %}\n"
        "  COMMENT='{{ comment }}'\n"
        "{%- endif %}\n"
        ";\n"
        "{%- endif %}\n"
        "{% endmacro %}\n"
    )


plugin = FileFormatPlugin()
