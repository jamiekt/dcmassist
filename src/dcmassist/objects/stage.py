"""Stage plugin (covers internal and external stages).

Stage DDL is synthesized in `_stage_ddl.py` (Snowflake doesn't support
`GET_DDL('STAGE', ...)`). The macro takes structured kwargs covering the
clauses the synthesizer emits — URL and STORAGE_INTEGRATION — plus optional
COMMENT. Credentials are deliberately never exported (committed DDL must not
contain secrets), so the macro has no kwarg for them.
"""

from __future__ import annotations

import re
from typing import Any

from dcmassist.objects._base import V1ObjectPlugin
from dcmassist.objects._stage_ddl import synthesize_stage_ddl
from dcmassist.rewrite import JinjaExpr
from dcmassist.types import FQN


class StageParseError(ValueError):
    """Raised when a DEFINE STAGE block contains a clause we can't model."""


_HEADER_RE = re.compile(
    r"^\s*DEFINE\s+STAGE\s+"
    r"(?P<fqn>(?:\"(?:[^\"]|\"\")+\"|[A-Za-z0-9_$]+|\{\{\s*\w+\s*\}\})"
    r"(?:\.(?:\"(?:[^\"]|\"\")+\"|[A-Za-z0-9_$]+|\{\{\s*\w+\s*\}\}))*)\s*",
    re.IGNORECASE,
)

_FQN_PART_RE = re.compile(
    r"\"(?P<quoted>(?:[^\"]|\"\")+)\"|(?P<bare>[A-Za-z_][A-Za-z0-9_$]*|\{\{\s*\w+\s*\}\})"
)

_URL_RE = re.compile(r"\s*URL\s*=\s*'(?P<v>(?:[^']|'')*)'", re.IGNORECASE)
_STORAGE_INTEGRATION_RE = re.compile(
    r"\s*STORAGE_INTEGRATION\s*=\s*(?P<v>[A-Za-z_][A-Za-z0-9_$]*)", re.IGNORECASE
)
_COMMENT_RE = re.compile(r"\s*COMMENT\s*=\s*'(?P<v>(?:[^']|'')*)'", re.IGNORECASE)


def parse_stage_ddl(ddl: str) -> dict[str, Any]:
    """Extract structured kwargs from a DEFINE STAGE block.

    The synthesizer emits only URL, STORAGE_INTEGRATION, and optional
    COMMENT. Anything else raises so unexpected synthesizer output surfaces
    as an export error rather than being silently dropped.
    """
    text = ddl.strip().rstrip(";").strip()

    header = _HEADER_RE.match(text)
    if header is None:
        raise StageParseError(f"could not parse DEFINE STAGE header: {ddl!r}")
    schema, name = _split_schema_and_name(header.group("fqn"), ddl)

    kwargs: dict[str, Any] = {"schema": schema, "name": name}
    pos = header.end()
    while pos < len(text):
        m = _URL_RE.match(text, pos)
        if m is not None:
            kwargs["url"] = m.group("v").replace("''", "'")
            pos = m.end()
            continue
        m = _STORAGE_INTEGRATION_RE.match(text, pos)
        if m is not None:
            kwargs["storage_integration"] = m.group("v")
            pos = m.end()
            continue
        m = _COMMENT_RE.match(text, pos)
        if m is not None:
            kwargs["comment"] = m.group("v").replace("''", "'")
            pos = m.end()
            continue
        if text[pos:].strip() == "":
            break
        raise StageParseError(
            f"unrecognised content in DEFINE STAGE at position {pos}: "
            f"{text[pos:]!r} (full DDL: {ddl!r})"
        )

    return kwargs


def _split_schema_and_name(fqn_text: str, original_ddl: str) -> tuple[str, str]:
    parts = [
        m.group("quoted").replace('""', '"') if m.group("quoted") else m.group("bare")
        for m in _FQN_PART_RE.finditer(fqn_text)
    ]
    if len(parts) == 3:
        return parts[1], parts[2]
    if len(parts) == 2:
        return parts[0], parts[1]
    raise StageParseError(
        f"could not parse FQN {fqn_text!r} from DEFINE STAGE: {original_ddl!r}"
    )


class StagePlugin(V1ObjectPlugin):
    type_name = "Stage"
    file_slug = "stage"
    SHOW_FORM = "SHOW STAGES"
    # GET_DDL_TYPE retained for symmetry with siblings, but unused: Snowflake does
    # not support GET_DDL('STAGE', ...). See get_ddl override + _stage_ddl.py.
    GET_DDL_TYPE = "STAGE"
    SUPPORTS_COMMENT = True
    MACRO_BODY = (
        "{% macro define_stage(database, schema, name, "
        "url=None, storage_integration=None, comment=None) %}\n"
        "DEFINE STAGE {{ database }}.{{ schema }}.{{ name }}"
        "{% if url is not none %} URL = '{{ url }}'{% endif %}"
        "{% if storage_integration is not none %}"
        " STORAGE_INTEGRATION = {{ storage_integration }}{% endif %}"
        "{% if comment is not none %} COMMENT='{{ comment }}'{% endif %}"
        ";\n"
        "{% endmacro %}\n"
    )

    def get_ddl(self, cursor: Any, fqn: FQN) -> str:
        # Snowflake doesn't support GET_DDL('STAGE',...). Read DESC STAGE rows
        # and synthesize a minimal CREATE OR REPLACE STAGE — see _stage_ddl.py
        # for why credentials are deliberately omitted. Use the quoted FQN so
        # non-standard identifiers resolve.
        cursor.execute(f"DESC STAGE {fqn.quoted}")
        return synthesize_stage_ddl(fqn, cursor.fetchall())

    def _macro_kwargs_from_ddl(
        self, define_ddl: str, *, database: str
    ) -> dict[str, Any]:
        kwargs = parse_stage_ddl(define_ddl)
        kwargs["database"] = JinjaExpr("database")
        return kwargs


plugin = StagePlugin()
