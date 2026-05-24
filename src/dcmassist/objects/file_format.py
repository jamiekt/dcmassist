"""File format plugin.

Snowflake's `CREATE FILE FORMAT` grammar has different option sets per TYPE
(CSV/JSON/AVRO/ORC/PARQUET/XML), and the per-type options are large and
periodically extended. Rather than enumerating each clause as its own kwarg,
the macro takes one `options` dict that round-trips every documented option:
the parser walks the DEFINE block and extracts each `KEY = value` pair.
Anything unrecognised raises so the orchestrator surfaces it as an export
error.
"""

from __future__ import annotations

import re
from typing import Any

from dcmassist.objects._base import V1ObjectPlugin
from dcmassist.rewrite import JinjaExpr


class FileFormatParseError(ValueError):
    """Raised when a DEFINE FILE FORMAT block contains a clause we can't model."""


_HEADER_RE = re.compile(
    r"^\s*DEFINE\s+FILE\s+FORMAT\s+"
    r"(?P<fqn>(?:\"(?:[^\"]|\"\")+\"|[A-Za-z0-9_$]+|\{\{\s*\w+\s*\}\})"
    r"(?:\.(?:\"(?:[^\"]|\"\")+\"|[A-Za-z0-9_$]+|\{\{\s*\w+\s*\}\}))*)\s*",
    re.IGNORECASE,
)

_FQN_PART_RE = re.compile(
    r"\"(?P<quoted>(?:[^\"]|\"\")+)\"|(?P<bare>[A-Za-z_][A-Za-z0-9_$]*|\{\{\s*\w+\s*\}\})"
)

_OPTION_KEY_RE = re.compile(r"\s*(?P<key>[A-Za-z][A-Za-z0-9_]*)\s*=\s*", re.IGNORECASE)
_COMMENT_RE = re.compile(r"\s*COMMENT\s*=\s*'(?P<v>(?:[^']|'')*)'", re.IGNORECASE)


def parse_file_format_ddl(ddl: str) -> dict[str, Any]:
    """Extract structured kwargs from a DEFINE FILE FORMAT block.

    Returns: `schema`, `name`, optional `options` (ordered dict of every
    `KEY = value` pair before COMMENT), and optional `comment`. Database is
    supplied by the plugin as a JinjaExpr.
    """
    text = ddl.strip().rstrip(";").strip()

    header = _HEADER_RE.match(text)
    if header is None:
        raise FileFormatParseError(
            f"could not parse DEFINE FILE FORMAT header: {ddl!r}"
        )
    schema, name = _split_schema_and_name(header.group("fqn"), ddl)

    kwargs: dict[str, Any] = {"schema": schema, "name": name}
    options: dict[str, str] = {}

    pos = header.end()
    while pos < len(text):
        m = _COMMENT_RE.match(text, pos)
        if m is not None:
            kwargs["comment"] = m.group("v").replace("''", "'")
            pos = m.end()
            continue

        m = _OPTION_KEY_RE.match(text, pos)
        if m is None:
            if text[pos:].strip() == "":
                break
            raise FileFormatParseError(
                f"unrecognised content in DEFINE FILE FORMAT at position {pos}: "
                f"{text[pos:]!r} (full DDL: {ddl!r})"
            )
        key = m.group("key").upper()
        value, value_end = _read_option_value(text, m.end(), ddl)
        options[key] = value
        pos = value_end

    if options:
        kwargs["options"] = options
    return kwargs


def _read_option_value(text: str, pos: int, original_ddl: str) -> tuple[str, int]:
    """Read one option's value starting at `pos`. Supports: single-quoted
    string, parenthesised list (e.g. `('a', 'b')`), bare identifier/number
    (true/false, integers, identifiers like CSV/AUTO/NONE)."""
    if pos >= len(text):
        raise FileFormatParseError(
            f"missing value for option in DEFINE FILE FORMAT: {original_ddl!r}"
        )

    ch = text[pos]
    if ch == "'":
        end = pos + 1
        while end < len(text):
            if text[end] == "'" and end + 1 < len(text) and text[end + 1] == "'":
                end += 2
                continue
            if text[end] == "'":
                end += 1
                break
            end += 1
        else:
            raise FileFormatParseError(
                f"unterminated string literal in option value: {original_ddl!r}"
            )
        return text[pos:end], end

    if ch == "(":
        depth = 0
        end = pos
        while end < len(text):
            if text[end] == "(":
                depth += 1
            elif text[end] == ")":
                depth -= 1
                if depth == 0:
                    end += 1
                    break
            end += 1
        else:
            raise FileFormatParseError(
                f"unterminated parenthesised value: {original_ddl!r}"
            )
        return text[pos:end], end

    end = pos
    while end < len(text) and not text[end].isspace():
        end += 1
    return text[pos:end], end


def _split_schema_and_name(fqn_text: str, original_ddl: str) -> tuple[str, str]:
    parts = [
        m.group("quoted").replace('""', '"') if m.group("quoted") else m.group("bare")
        for m in _FQN_PART_RE.finditer(fqn_text)
    ]
    if len(parts) == 3:
        return parts[1], parts[2]
    if len(parts) == 2:
        return parts[0], parts[1]
    raise FileFormatParseError(
        f"could not parse FQN {fqn_text!r} from DEFINE FILE FORMAT: {original_ddl!r}"
    )


class FileFormatPlugin(V1ObjectPlugin):
    type_name = "File format"
    file_slug = "file_format"
    SHOW_FORM = "SHOW FILE FORMATS"
    GET_DDL_TYPE = "FILE_FORMAT"
    SUPPORTS_COMMENT = True
    MACRO_BODY = (
        "{% macro define_file_format(\n"
        "    database,\n"
        "    schema,\n"
        "    name,\n"
        "    options=None,\n"
        "    comment=None\n"
        ") %}\n"
        "DEFINE FILE FORMAT {{ database }}.{{ schema }}.{{ name }}"
        "{% if options %}{% for k, v in options.items() %} {{ k }} = {{ v }}"
        "{% endfor %}{% endif %}"
        "{% if comment is not none %} COMMENT='{{ comment }}'{% endif %}"
        ";\n"
        "{% endmacro %}\n"
    )

    def _macro_kwargs_from_ddl(
        self, define_ddl: str, *, database: str
    ) -> dict[str, Any]:
        kwargs = parse_file_format_ddl(define_ddl)
        kwargs["database"] = JinjaExpr("database")
        return kwargs


plugin = FileFormatPlugin()
