"""DDL rewriting helpers for the GET_DDL → DEFINE pipeline.

Helpers are regex-based so they tolerate Snowflake-specific syntax that sqlglot
can't parse. Each helper is independently callable; plugins compose them in their
`to_define_and_invocation` implementations.
"""

from __future__ import annotations

import re
from typing import NamedTuple

import sqlglot
from sqlglot import exp

_DIALECT = "snowflake"


class JinjaExpr(NamedTuple):
    """Marker for a Jinja expression that should appear unquoted in a macro
    invocation. Used so `database=database` (an identifier reference) survives
    `render_macro_invocation` instead of being turned into the string
    `'database'`."""

    source: str


def _parse(ddl: str) -> exp.Expr:
    return sqlglot.parse_one(ddl, dialect=_DIALECT)


def _render(node: exp.Expr) -> str:
    return node.sql(dialect=_DIALECT)


def create_to_define(ddl: str) -> str:
    """Rewrite the leading `CREATE [OR REPLACE]` to `DEFINE`.

    Idempotent: a string that already starts with DEFINE is returned unchanged.
    A regex rewrite is used (rather than sqlglot) so that GET_DDL output containing
    Snowflake-specific syntax sqlglot can't parse still rewrites cleanly.
    """
    stripped = ddl.lstrip()
    if re.match(r"DEFINE\b", stripped, flags=re.IGNORECASE):
        return ddl

    pattern = re.compile(r"^(\s*)CREATE\s+(OR\s+REPLACE\s+)?", re.IGNORECASE)
    match = pattern.match(ddl)
    if match is None:
        return ddl
    return pattern.sub(rf"{match.group(1)}DEFINE ", ddl, count=1)


_COMMENT_RE = re.compile(r"\bCOMMENT\s*=\s*", re.IGNORECASE)


def inject_comment_if_missing(
    ddl: str,
    *,
    comment: str | None,
    supports_comment: bool = True,
) -> str:
    """Append `COMMENT='<comment>'` to the DEFINE statement when no COMMENT exists.

    - If the type does not support COMMENT (`supports_comment=False`), returns `ddl`.
    - If the existing DDL already has a COMMENT clause, returns `ddl`.
    - If `comment is None`, returns `ddl`.
    - Single quotes inside the comment are doubled (Snowflake string escape).
    """
    if not supports_comment or comment is None:
        return ddl
    if _COMMENT_RE.search(ddl):
        return ddl

    escaped = comment.replace("'", "''")
    body = ddl.rstrip()
    if body.endswith(";"):
        body = body[:-1].rstrip()
        suffix = ";"
    else:
        suffix = ""
    return f"{body} COMMENT='{escaped}'{suffix}"


def parameterise_database(ddl: str, *, database: str) -> str:
    """Replace whole-identifier occurrences of `database` (case-insensitive) with
    the literal string `{{ database }}`.

    Whole-identifier means: bounded on both sides by characters that do not form part
    of a Snowflake identifier (letters, digits, `_`, `$`). Substring occurrences inside
    longer identifiers are preserved.
    """
    pattern = re.compile(
        rf"(?<![A-Za-z0-9_$]){re.escape(database)}(?![A-Za-z0-9_$])",
        re.IGNORECASE,
    )
    return pattern.sub("{{ database }}", ddl)


def _jinja_str_literal(value: str) -> str:
    escaped = value.replace("'", "\\'")
    return f"'{escaped}'"


def _format_value(value: object) -> str:
    if isinstance(value, JinjaExpr):
        return value.source
    if isinstance(value, str):
        return _jinja_str_literal(value)
    return repr(value)


def render_macro_invocation(macro_name: str, *, kwargs: dict[str, object]) -> str:
    """Render a Jinja `{{ macro_name(...) }}` invocation with keyword args.

    None values are omitted. String values are single-quoted (single quotes within
    are backslash-escaped, matching Jinja's expression syntax). `JinjaExpr`
    values are emitted verbatim — use them for identifier references and
    expressions that must be evaluated at render time.
    """
    parts = [
        f"{key}={_format_value(value)}"
        for key, value in kwargs.items()
        if value is not None
    ]
    return f"{{{{ {macro_name}({', '.join(parts)}) }}}}"
