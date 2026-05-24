"""Stage plugin (covers internal and external stages)."""

from __future__ import annotations

from typing import Any

from dcmassist.objects._base import V1ObjectPlugin
from dcmassist.objects._stage_ddl import synthesize_stage_ddl
from dcmassist.types import FQN


class StagePlugin(V1ObjectPlugin):
    type_name = "Stage"
    file_slug = "stage"
    SHOW_FORM = "SHOW STAGES"
    # GET_DDL_TYPE retained for symmetry with siblings, but unused: Snowflake does
    # not support GET_DDL('STAGE', ...). See get_ddl override + _stage_ddl.py.
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

    def get_ddl(self, cursor: Any, fqn: FQN) -> str:
        # Snowflake doesn't support GET_DDL('STAGE',...). Read DESC STAGE rows
        # and synthesize a minimal CREATE OR REPLACE STAGE — see _stage_ddl.py
        # for why credentials are deliberately omitted. Use the quoted FQN so
        # non-standard identifiers resolve.
        cursor.execute(f"DESC STAGE {fqn.quoted}")
        return synthesize_stage_ddl(fqn, cursor.fetchall())


plugin = StagePlugin()
