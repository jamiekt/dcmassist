"""Tag plugin."""

from __future__ import annotations

from dcmexporter.objects._base import V1ObjectPlugin


class TagPlugin(V1ObjectPlugin):
    type_name = "Tag"
    file_slug = "tag"
    SHOW_FORM = "SHOW TAGS"
    GET_DDL_TYPE = "TAG"
    SUPPORTS_COMMENT = True
    MACRO_BODY = (
        "{% macro define_tag(database, schema=None, name=None, raw=None, "
        "allowed_values=None, comment=None) %}\n"
        "{%- if raw %}{{ raw }}{%- else %}\n"
        "DEFINE TAG {{ database }}.{{ schema }}.{{ name }}\n"
        "{%- if allowed_values %}\n"
        "  ALLOWED_VALUES {% for v in allowed_values %}'{{ v }}'"
        "{% if not loop.last %}, {% endif %}{% endfor %}\n"
        "{%- endif %}\n"
        "{%- if comment is not none %}\n"
        "  COMMENT='{{ comment }}'\n"
        "{%- endif %}\n"
        ";\n"
        "{%- endif %}\n"
        "{% endmacro %}\n"
    )


plugin = TagPlugin()
