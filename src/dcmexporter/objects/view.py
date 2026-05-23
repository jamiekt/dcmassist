"""View plugin (covers regular and secure views)."""

from __future__ import annotations

from dcmexporter.objects._base import V1ObjectPlugin


class ViewPlugin(V1ObjectPlugin):
    type_name = "View"
    file_slug = "view"
    SHOW_FORM = "SHOW VIEWS"
    GET_DDL_TYPE = "VIEW"
    SUPPORTS_COMMENT = True
    MACRO_BODY = (
        "{% macro define_view(database, schema=None, name=None, raw=None, "
        "secure=False, body=None, comment=None) %}\n"
        "{%- if raw %}{{ raw }}{%- else %}\n"
        "DEFINE {% if secure %}SECURE {% endif %}VIEW "
        "{{ database }}.{{ schema }}.{{ name }} AS\n"
        "  {{ body }}\n"
        "{%- if comment is not none %}\n"
        "  COMMENT='{{ comment }}'\n"
        "{%- endif %}\n"
        ";\n"
        "{%- endif %}\n"
        "{% endmacro %}\n"
    )


plugin = ViewPlugin()
