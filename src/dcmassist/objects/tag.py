"""Tag plugin.

The macro accepts every documented `CREATE TAG` clause as a structured kwarg;
`parse_tag_ddl` walks the DEFINE block from the rewrite chain and extracts
each clause. Unrecognised content raises so the orchestrator surfaces it as
an export error.
"""

from __future__ import annotations

import re
from typing import Any

from dcmassist.objects._base import V1ObjectPlugin
from dcmassist.rewrite import JinjaExpr


class TagParseError(ValueError):
    """Raised when a DEFINE TAG block contains a clause we can't model."""


_HEADER_RE = re.compile(
    r"^\s*DEFINE\s+TAG\s+(?P<fqn>(?:\"(?:[^\"]|\"\")+\"|[A-Za-z0-9_$]+|\{\{\s*\w+\s*\}\})"
    r"(?:\.(?:\"(?:[^\"]|\"\")+\"|[A-Za-z0-9_$]+|\{\{\s*\w+\s*\}\}))*)\s*",
    re.IGNORECASE,
)

_FQN_PART_RE = re.compile(
    r"\"(?P<quoted>(?:[^\"]|\"\")+)\"|(?P<bare>[A-Za-z_][A-Za-z0-9_$]*|\{\{\s*\w+\s*\}\})"
)

_ALLOWED_VALUES_RE = re.compile(r"\s*ALLOWED_VALUES\s*", re.IGNORECASE)
_STRING_LITERAL_RE = re.compile(r"'(?P<v>(?:[^']|'')*)'")
_COMMA_RE = re.compile(r"\s*,\s*")
_COMMENT_RE = re.compile(r"\s*COMMENT\s*=\s*'(?P<v>(?:[^']|'')*)'", re.IGNORECASE)


def parse_tag_ddl(ddl: str) -> dict[str, Any]:
    """Extract structured kwargs from a DEFINE TAG block.

    Returns a dict with `schema`, `name`, and any of `allowed_values`,
    `comment` that were present. Database is supplied by the plugin as a
    JinjaExpr.
    """
    text = ddl.strip().rstrip(";").strip()

    header = _HEADER_RE.match(text)
    if header is None:
        raise TagParseError(f"could not parse DEFINE TAG header: {ddl!r}")
    schema, name = _split_schema_and_name(header.group("fqn"), ddl)

    kwargs: dict[str, Any] = {"schema": schema, "name": name}
    pos = header.end()

    while pos < len(text):
        m = _ALLOWED_VALUES_RE.match(text, pos)
        if m is not None:
            pos = m.end()
            values: list[str] = []
            literal = _STRING_LITERAL_RE.match(text, pos)
            if literal is None:
                raise TagParseError(
                    f"ALLOWED_VALUES requires at least one string literal: {ddl!r}"
                )
            values.append(literal.group("v").replace("''", "'"))
            pos = literal.end()
            while True:
                comma = _COMMA_RE.match(text, pos)
                if comma is None:
                    break
                literal = _STRING_LITERAL_RE.match(text, comma.end())
                if literal is None:
                    raise TagParseError(f"trailing comma in ALLOWED_VALUES: {ddl!r}")
                values.append(literal.group("v").replace("''", "'"))
                pos = literal.end()
            kwargs["allowed_values"] = values
            continue

        m = _COMMENT_RE.match(text, pos)
        if m is not None:
            kwargs["comment"] = m.group("v").replace("''", "'")
            pos = m.end()
            continue

        if text[pos:].strip() == "":
            break
        raise TagParseError(
            f"unrecognised content in DEFINE TAG at position {pos}: "
            f"{text[pos:]!r} (full DDL: {ddl!r})"
        )

    return kwargs


def _split_schema_and_name(fqn_text: str, original_ddl: str) -> tuple[str, str]:
    """Pull schema and name out of a 2- or 3-part FQN. The database part
    is dropped because the plugin passes `database` as a separate JinjaExpr."""
    parts = [
        m.group("quoted").replace('""', '"') if m.group("quoted") else m.group("bare")
        for m in _FQN_PART_RE.finditer(fqn_text)
    ]
    if len(parts) == 3:
        return parts[1], parts[2]
    if len(parts) == 2:
        return parts[0], parts[1]
    raise TagParseError(
        f"could not parse FQN {fqn_text!r} from DEFINE TAG: {original_ddl!r}"
    )


class TagPlugin(V1ObjectPlugin):
    type_name = "Tag"
    file_slug = "tag"
    SHOW_FORM = "SHOW TAGS"
    GET_DDL_TYPE = "TAG"
    SUPPORTS_COMMENT = True
    MACRO_BODY = (
        "{% macro define_tag(\n"
        "    database,\n"
        "    schema,\n"
        "    name,\n"
        "    allowed_values=None,\n"
        "    comment=None\n"
        ") %}\n"
        "DEFINE TAG {{ database }}.{{ schema }}.{{ name }}\n"
        "{%- if allowed_values %}\n"
        "  ALLOWED_VALUES "
        "{% for v in allowed_values %}'{{ v }}'"
        "{% if not loop.last %}, {% endif %}{% endfor %}\n"
        "{%- endif %}\n"
        "{%- if comment is not none %}\n"
        "  COMMENT='{{ comment }}'\n"
        "{%- endif %}\n"
        ";\n"
        "{% endmacro %}\n"
    )

    def _macro_kwargs_from_ddl(
        self, define_ddl: str, *, database: str
    ) -> dict[str, Any]:
        kwargs = parse_tag_ddl(define_ddl)
        kwargs["database"] = JinjaExpr("database")
        return kwargs


plugin = TagPlugin()
