"""Table plugin.

The macro takes one structured kwarg per Snowflake `CREATE TABLE` clause —
no `raw=` escape hatch. Column definitions are passed as a list of strings
(each entry is a verbatim column definition, including inline constraints,
defaults, COLLATE, and identity clauses) so the macro can render them inside
the column list while the table-level clauses (CLUSTER BY, retention,
change-tracking, COPY GRANTS, COMMENT, etc.) remain individually addressable.

Per-column masking/projection policies, inline tag clauses, and table-level
ROW ACCESS / AGGREGATION / JOIN policies and WITH TAG clauses are not
modelled in v1: parsing them safely requires resolving cross-object
references and structuring nested expressions. The parser raises
`TableParseError` so the orchestrator surfaces these as export errors rather
than silently dropping them.
"""

from __future__ import annotations

import re
from typing import Any

from dcmassist.objects._base import V1ObjectPlugin
from dcmassist.rewrite import JinjaExpr


class TableParseError(ValueError):
    """Raised when a DEFINE TABLE block contains a clause we can't model."""


_HEADER_RE = re.compile(
    r"^\s*DEFINE\s+(?P<transient>TRANSIENT\s+)?(?P<volatile>VOLATILE\s+)?TABLE\s+"
    r"(?P<fqn>(?:\"(?:[^\"]|\"\")+\"|[A-Za-z0-9_$]+|\{\{\s*\w+\s*\}\})"
    r"(?:\.(?:\"(?:[^\"]|\"\")+\"|[A-Za-z0-9_$]+|\{\{\s*\w+\s*\}\}))*)\s*",
    re.IGNORECASE,
)

_FQN_PART_RE = re.compile(
    r"\"(?P<quoted>(?:[^\"]|\"\")+)\"|(?P<bare>[A-Za-z_][A-Za-z0-9_$]*|\{\{\s*\w+\s*\}\})"
)

_CLUSTER_BY_RE = re.compile(r"\s*CLUSTER\s+BY\s*", re.IGNORECASE)
_DATA_RETENTION_RE = re.compile(
    r"\s*DATA_RETENTION_TIME_IN_DAYS\s*=\s*(?P<v>\d+)", re.IGNORECASE
)
_MAX_EXTENSION_RE = re.compile(
    r"\s*MAX_DATA_EXTENSION_TIME_IN_DAYS\s*=\s*(?P<v>\d+)", re.IGNORECASE
)
_CHANGE_TRACKING_RE = re.compile(
    r"\s*CHANGE_TRACKING\s*=\s*(?P<v>TRUE|FALSE)\b", re.IGNORECASE
)
_ENABLE_SCHEMA_EVOLUTION_RE = re.compile(
    r"\s*ENABLE_SCHEMA_EVOLUTION\s*=\s*(?P<v>TRUE|FALSE)\b", re.IGNORECASE
)
_DEFAULT_DDL_COLLATION_RE = re.compile(
    r"\s*DEFAULT_DDL_COLLATION\s*=\s*'(?P<v>(?:[^']|'')*)'", re.IGNORECASE
)
_COPY_GRANTS_RE = re.compile(r"\s*COPY\s+GRANTS\b", re.IGNORECASE)
_COMMENT_RE = re.compile(r"\s*COMMENT\s*=\s*'(?P<v>(?:[^']|'')*)'", re.IGNORECASE)
_UNSUPPORTED_RE = re.compile(
    r"\s*(MASKING\s+POLICY|PROJECTION\s+POLICY|ROW\s+ACCESS\s+POLICY|"
    r"AGGREGATION\s+POLICY|JOIN\s+POLICY|WITH\s+TAG|TAG\s*\(|"
    r"WITH\s+ROW\s+ACCESS\s+POLICY|WITH\s+AGGREGATION\s+POLICY)",
    re.IGNORECASE,
)


def parse_table_ddl(ddl: str) -> dict[str, Any]:
    """Extract structured kwargs from a DEFINE TABLE block.

    Returns: `schema`, `name`, `columns` (list of verbatim column-definition
    strings), and any of `transient`, `cluster_by`, `data_retention_time_in_days`,
    `max_data_extension_time_in_days`, `change_tracking`,
    `enable_schema_evolution`, `default_ddl_collation`, `copy_grants`,
    `comment`. Database is supplied by the plugin as a JinjaExpr.
    """
    text = ddl.strip().rstrip(";").rstrip()

    header = _HEADER_RE.match(text)
    if header is None:
        raise TableParseError(f"could not parse DEFINE TABLE header: {ddl!r}")
    schema, name = _split_schema_and_name(header.group("fqn"), ddl)

    kwargs: dict[str, Any] = {"schema": schema, "name": name}
    if header.group("transient"):
        kwargs["transient"] = True
    if header.group("volatile"):
        kwargs["volatile"] = True

    pos = header.end()

    if pos >= len(text) or text[pos] != "(":
        raise TableParseError(f"DEFINE TABLE missing column list: {ddl!r}")
    column_list_text, pos = _read_balanced(text, pos, ddl)
    columns = _split_columns(column_list_text[1:-1].strip(), ddl)
    for column in columns:
        if _UNSUPPORTED_RE.search(column):
            raise TableParseError(
                f"per-column policy/tag clauses are not supported in v1: {ddl!r}"
            )
    kwargs["columns"] = columns

    while pos < len(text):
        if _UNSUPPORTED_RE.match(text, pos) is not None:
            raise TableParseError(
                f"unsupported clause (policy/tag) in DEFINE TABLE: {ddl!r}"
            )
        m = _CLUSTER_BY_RE.match(text, pos)
        if m is not None:
            cluster_pos = m.end()
            if cluster_pos >= len(text) or text[cluster_pos] != "(":
                raise TableParseError(f"CLUSTER BY missing parens: {ddl!r}")
            cluster_text, pos = _read_balanced(text, cluster_pos, ddl)
            kwargs["cluster_by"] = _split_top_level_commas(
                cluster_text[1:-1].strip(), ddl
            )
            continue
        m = _DATA_RETENTION_RE.match(text, pos)
        if m is not None:
            kwargs["data_retention_time_in_days"] = int(m.group("v"))
            pos = m.end()
            continue
        m = _MAX_EXTENSION_RE.match(text, pos)
        if m is not None:
            kwargs["max_data_extension_time_in_days"] = int(m.group("v"))
            pos = m.end()
            continue
        m = _CHANGE_TRACKING_RE.match(text, pos)
        if m is not None:
            kwargs["change_tracking"] = m.group("v").upper() == "TRUE"
            pos = m.end()
            continue
        m = _ENABLE_SCHEMA_EVOLUTION_RE.match(text, pos)
        if m is not None:
            kwargs["enable_schema_evolution"] = m.group("v").upper() == "TRUE"
            pos = m.end()
            continue
        m = _DEFAULT_DDL_COLLATION_RE.match(text, pos)
        if m is not None:
            kwargs["default_ddl_collation"] = m.group("v").replace("''", "'")
            pos = m.end()
            continue
        m = _COPY_GRANTS_RE.match(text, pos)
        if m is not None:
            kwargs["copy_grants"] = True
            pos = m.end()
            continue
        m = _COMMENT_RE.match(text, pos)
        if m is not None:
            kwargs["comment"] = m.group("v").replace("''", "'")
            pos = m.end()
            continue
        if text[pos:].strip() == "":
            break
        raise TableParseError(
            f"unrecognised content in DEFINE TABLE at position {pos}: "
            f"{text[pos:]!r} (full DDL: {ddl!r})"
        )

    return kwargs


def _read_balanced(text: str, pos: int, original_ddl: str) -> tuple[str, int]:
    """Read a balanced parenthesised expression (with quoted-string awareness)
    starting at `pos`. Returns `(slice_including_parens, end_index)`."""
    depth = 0
    end = pos
    in_str = False
    while end < len(text):
        ch = text[end]
        if in_str:
            if ch == "'":
                if end + 1 < len(text) and text[end + 1] == "'":
                    end += 2
                    continue
                in_str = False
        else:
            if ch == "'":
                in_str = True
            elif ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    end += 1
                    return text[pos:end], end
        end += 1
    raise TableParseError(f"unterminated parenthesised expression: {original_ddl!r}")


def _split_columns(text: str, original_ddl: str) -> list[str]:
    """Split a column-list body on top-level commas and strip surrounding
    whitespace. Empty input returns []."""
    if not text:
        raise TableParseError(f"empty column list in DEFINE TABLE: {original_ddl!r}")
    return _split_top_level_commas(text, original_ddl)


def _split_top_level_commas(text: str, original_ddl: str) -> list[str]:
    """Split on commas that are at paren depth 0 and outside string literals."""
    parts: list[str] = []
    depth = 0
    in_str = False
    start = 0
    i = 0
    while i < len(text):
        ch = text[i]
        if in_str:
            if ch == "'":
                if i + 1 < len(text) and text[i + 1] == "'":
                    i += 2
                    continue
                in_str = False
        else:
            if ch == "'":
                in_str = True
            elif ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            elif ch == "," and depth == 0:
                parts.append(text[start:i].strip())
                start = i + 1
        i += 1
    if in_str or depth != 0:
        raise TableParseError(
            f"unbalanced parens or unterminated string in: {original_ddl!r}"
        )
    parts.append(text[start:].strip())
    return [part for part in parts if part]


def _split_schema_and_name(fqn_text: str, original_ddl: str) -> tuple[str, str]:
    parts = [
        m.group("quoted").replace('""', '"') if m.group("quoted") else m.group("bare")
        for m in _FQN_PART_RE.finditer(fqn_text)
    ]
    if len(parts) == 3:
        return parts[1], parts[2]
    if len(parts) == 2:
        return parts[0], parts[1]
    raise TableParseError(
        f"could not parse FQN {fqn_text!r} from DEFINE TABLE: {original_ddl!r}"
    )


class TablePlugin(V1ObjectPlugin):
    type_name = "Table"
    file_slug = "table"
    SHOW_FORM = "SHOW TABLES"
    GET_DDL_TYPE = "TABLE"
    SUPPORTS_COMMENT = True
    MACRO_BODY = (
        "{% macro define_table(database, schema, name, columns, "
        "transient=False, volatile=False, cluster_by=None, "
        "data_retention_time_in_days=None, max_data_extension_time_in_days=None, "
        "change_tracking=None, enable_schema_evolution=None, "
        "default_ddl_collation=None, copy_grants=False, comment=None) %}\n"
        "DEFINE {% if transient %}TRANSIENT {% endif %}"
        "{% if volatile %}VOLATILE {% endif %}TABLE "
        "{{ database }}.{{ schema }}.{{ name }} (\n"
        "{% for column in columns %}  {{ column }}"
        "{% if not loop.last %},{% endif %}\n"
        "{% endfor %})"
        "{% if cluster_by %} CLUSTER BY ({{ cluster_by | join(', ') }}){% endif %}"
        "{% if data_retention_time_in_days is not none %}"
        " DATA_RETENTION_TIME_IN_DAYS = {{ data_retention_time_in_days }}{% endif %}"
        "{% if max_data_extension_time_in_days is not none %}"
        " MAX_DATA_EXTENSION_TIME_IN_DAYS = {{ max_data_extension_time_in_days }}"
        "{% endif %}"
        "{% if change_tracking is not none %}"
        " CHANGE_TRACKING = {% if change_tracking %}TRUE{% else %}FALSE{% endif %}"
        "{% endif %}"
        "{% if enable_schema_evolution is not none %}"
        " ENABLE_SCHEMA_EVOLUTION = "
        "{% if enable_schema_evolution %}TRUE{% else %}FALSE{% endif %}{% endif %}"
        "{% if default_ddl_collation is not none %}"
        " DEFAULT_DDL_COLLATION = '{{ default_ddl_collation }}'{% endif %}"
        "{% if copy_grants %} COPY GRANTS{% endif %}"
        "{% if comment is not none %} COMMENT='{{ comment }}'{% endif %}"
        ";\n"
        "{% endmacro %}\n"
    )

    def _macro_kwargs_from_ddl(
        self, define_ddl: str, *, database: str
    ) -> dict[str, Any]:
        kwargs = parse_table_ddl(define_ddl)
        kwargs["database"] = JinjaExpr("database")
        return kwargs


plugin = TablePlugin()
