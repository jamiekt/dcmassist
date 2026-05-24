"""Sequence plugin.

The macro takes structured kwargs (database, schema, name, start, increment,
order, comment) rather than a `raw` DDL blob. `parse_sequence_ddl` walks the
DEFINE block produced by the rewrite chain and extracts each clause; anything
unrecognised raises so the orchestrator surfaces it as an export error.
"""

from __future__ import annotations

import re
from typing import Any

from dcmassist.objects._base import V1ObjectPlugin
from dcmassist.rewrite import JinjaExpr


class SequenceParseError(ValueError):
    """Raised when a DEFINE SEQUENCE block contains a clause we can't model."""


_HEADER_RE = re.compile(
    r"^\s*DEFINE\s+SEQUENCE\s+(?P<fqn>(?:\"(?:[^\"]|\"\")+\"|[A-Za-z0-9_$]+|\{\{\s*\w+\s*\}\})(?:\.(?:\"(?:[^\"]|\"\")+\"|[A-Za-z0-9_$]+|\{\{\s*\w+\s*\}\}))*)\s*",
    re.IGNORECASE,
)

_FQN_PART_RE = re.compile(
    r"\"(?P<quoted>(?:[^\"]|\"\")+)\"|(?P<bare>[A-Za-z_][A-Za-z0-9_$]*|\{\{\s*\w+\s*\}\})"
)

# Each pattern matches one whole clause from leading whitespace to the next
# clause boundary. Order in CLAUSE_PATTERNS doesn't matter — we scan
# left-to-right and try each at the current position.
_WITH_RE = re.compile(r"\s*WITH\b", re.IGNORECASE)
_START_RE = re.compile(r"\s*START\s+(?:WITH\s+)?(?:=\s*)?(?P<v>-?\d+)", re.IGNORECASE)
_INCREMENT_RE = re.compile(
    r"\s*INCREMENT\s+(?:BY\s+)?(?:=\s*)?(?P<v>-?\d+)", re.IGNORECASE
)
_ORDER_RE = re.compile(r"\s*(?P<v>NOORDER|ORDER)\b", re.IGNORECASE)
_COMMENT_RE = re.compile(r"\s*COMMENT\s*=\s*'(?P<v>(?:[^']|'')*)'", re.IGNORECASE)


def parse_sequence_ddl(ddl: str) -> dict[str, Any]:
    """Extract structured kwargs from a DEFINE SEQUENCE block.

    Returns a dict with `schema`, `name`, and any of `start`, `increment`,
    `order`, `comment` that were present. The `database` kwarg is supplied by
    the plugin (not the parser) because it must arrive as a JinjaExpr.

    Raises `SequenceParseError` for any clause not in Snowflake's documented
    `CREATE SEQUENCE` grammar so unsupported syntax surfaces to the user
    instead of being silently dropped.
    """
    text = ddl.strip().rstrip(";").strip()

    header = _HEADER_RE.match(text)
    if header is None:
        raise SequenceParseError(f"could not parse DEFINE SEQUENCE header: {ddl!r}")
    schema, name = _split_schema_and_name(header.group("fqn"), ddl)

    kwargs: dict[str, Any] = {"schema": schema, "name": name}

    pos = header.end()
    while pos < len(text):
        # Each turn either consumes a clause or fails. Trailing whitespace is
        # absorbed by the per-clause patterns; bare whitespace ends the loop.
        if (m := _WITH_RE.match(text, pos)) is not None:
            pos = m.end()
            continue
        if (m := _START_RE.match(text, pos)) is not None:
            kwargs["start"] = int(m.group("v"))
            pos = m.end()
            continue
        if (m := _INCREMENT_RE.match(text, pos)) is not None:
            kwargs["increment"] = int(m.group("v"))
            pos = m.end()
            continue
        if (m := _ORDER_RE.match(text, pos)) is not None:
            kwargs["order"] = m.group("v").upper() == "ORDER"
            pos = m.end()
            continue
        if (m := _COMMENT_RE.match(text, pos)) is not None:
            kwargs["comment"] = m.group("v").replace("''", "'")
            pos = m.end()
            continue
        if text[pos:].strip() == "":
            break
        raise SequenceParseError(
            f"unrecognised content in DEFINE SEQUENCE at position {pos}: "
            f"{text[pos:]!r} (full DDL: {ddl!r})"
        )

    return kwargs


def _split_schema_and_name(fqn_text: str, original_ddl: str) -> tuple[str, str]:
    """Pull schema and name out of a 2- or 3-part FQN. The database part
    (literal or `{{ database }}` template) is ignored because the macro
    receives `database` as a separate JinjaExpr kwarg."""
    parts = [
        m.group("quoted").replace('""', '"') if m.group("quoted") else m.group("bare")
        for m in _FQN_PART_RE.finditer(fqn_text)
    ]
    if len(parts) == 3:
        return parts[1], parts[2]
    if len(parts) == 2:
        return parts[0], parts[1]
    raise SequenceParseError(
        f"could not parse FQN {fqn_text!r} from DEFINE SEQUENCE: {original_ddl!r}"
    )


class SequencePlugin(V1ObjectPlugin):
    type_name = "Sequence"
    file_slug = "sequence"
    SHOW_FORM = "SHOW SEQUENCES"
    GET_DDL_TYPE = "SEQUENCE"
    SUPPORTS_COMMENT = True
    MACRO_BODY = (
        "{% macro define_sequence(\n"
        "    database,\n"
        "    schema,\n"
        "    name,\n"
        "    start=None,\n"
        "    increment=None,\n"
        "    order=None,\n"
        "    comment=None\n"
        ") %}\n"
        "DEFINE SEQUENCE {{ database }}.{{ schema }}.{{ name }}"
        "{% if start is not none %} START = {{ start }}{% endif %}"
        "{% if increment is not none %} INCREMENT = {{ increment }}{% endif %}"
        "{% if order is not none %} {% if order %}ORDER{% else %}NOORDER{% endif %}{% endif %}"
        "{% if comment is not none %} COMMENT='{{ comment }}'{% endif %}"
        ";\n"
        "{% endmacro %}\n"
    )

    def _macro_kwargs_from_ddl(
        self, define_ddl: str, *, database: str
    ) -> dict[str, Any]:
        kwargs = parse_sequence_ddl(define_ddl)
        kwargs["database"] = JinjaExpr("database")
        return kwargs


plugin = SequencePlugin()
