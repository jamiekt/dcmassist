"""View plugin (covers regular and secure views).

The macro covers the header — SECURE / RECURSIVE / column list / COPY GRANTS /
COMMENT — and the body is written outside the macro call so it can be wrapped
in `{% raw %}{% endraw %}` markers. That keeps any literal `{{ }}` characters
in the SELECT body inert during DCM's single Jinja pass while still allowing
the database name to be substituted (segments referencing the runtime
database are emitted *between* raw blocks, not inside them).

Per-column masking/projection policies, tag clauses, and ROW ACCESS /
AGGREGATION policies are not supported in v1 — the parser raises
`ViewParseError` so the orchestrator surfaces it as an export error rather
than silently dropping the clause.
"""

from __future__ import annotations

import re
from typing import Any

from dcmassist.objects._base import V1ObjectPlugin
from dcmassist.rewrite import (
    JinjaExpr,
    create_to_define,
    render_macro_invocation,
)


class ViewParseError(ValueError):
    """Raised when a DEFINE VIEW block contains a clause we can't model."""


_HEADER_RE = re.compile(
    r"^\s*DEFINE\s+(?P<secure>SECURE\s+)?(?P<recursive>RECURSIVE\s+)?VIEW\s+"
    r"(?P<fqn>(?:\"(?:[^\"]|\"\")+\"|[A-Za-z0-9_$]+|\{\{\s*\w+\s*\}\})"
    r"(?:\.(?:\"(?:[^\"]|\"\")+\"|[A-Za-z0-9_$]+|\{\{\s*\w+\s*\}\}))*)\s*",
    re.IGNORECASE,
)

_FQN_PART_RE = re.compile(
    r"\"(?P<quoted>(?:[^\"]|\"\")+)\"|(?P<bare>[A-Za-z_][A-Za-z0-9_$]*|\{\{\s*\w+\s*\}\})"
)

_COPY_GRANTS_RE = re.compile(r"\s*COPY\s+GRANTS\b", re.IGNORECASE)
_COMMENT_RE = re.compile(r"\s*COMMENT\s*=\s*'(?P<v>(?:[^']|'')*)'", re.IGNORECASE)
_AS_RE = re.compile(r"\s*AS\b", re.IGNORECASE)
_UNSUPPORTED_RE = re.compile(
    r"\s*(MASKING\s+POLICY|PROJECTION\s+POLICY|ROW\s+ACCESS\s+POLICY|"
    r"AGGREGATION\s+POLICY|WITH\s+TAG|TAG\s*\()",
    re.IGNORECASE,
)


def parse_view_ddl(ddl: str) -> dict[str, Any]:
    """Extract structured kwargs from a DEFINE VIEW block.

    Returns: `schema`, `name`, `body`, optional `secure`, `recursive`,
    `column_list`, `copy_grants`, `comment`. Database is supplied by the
    plugin as a JinjaExpr.

    Raises ViewParseError on per-column policies / tag clauses / row access /
    aggregation policies — these are not modelled in v1.
    """
    text = ddl.strip().rstrip(";").rstrip()

    header = _HEADER_RE.match(text)
    if header is None:
        raise ViewParseError(f"could not parse DEFINE VIEW header: {ddl!r}")
    schema, name = _split_schema_and_name(header.group("fqn"), ddl)

    kwargs: dict[str, Any] = {"schema": schema, "name": name}
    if header.group("secure"):
        kwargs["secure"] = True
    if header.group("recursive"):
        kwargs["recursive"] = True

    pos = header.end()

    if pos < len(text) and text[pos] == "(":
        column_list, pos = _read_balanced(text, pos, ddl)
        if _UNSUPPORTED_RE.search(column_list):
            raise ViewParseError(
                f"per-column policy/tag clauses are not supported in v1: {ddl!r}"
            )
        kwargs["column_list"] = column_list

    while pos < len(text):
        if _UNSUPPORTED_RE.match(text, pos) is not None:
            raise ViewParseError(
                f"unsupported clause (policy/tag) in DEFINE VIEW: {ddl!r}"
            )
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
        m = _AS_RE.match(text, pos)
        if m is not None:
            body = text[m.end() :].strip()
            if not body:
                raise ViewParseError(f"empty AS body in DEFINE VIEW: {ddl!r}")
            kwargs["body"] = body
            return kwargs
        if text[pos:].strip() == "":
            break
        raise ViewParseError(
            f"unrecognised content in DEFINE VIEW at position {pos}: "
            f"{text[pos:]!r} (full DDL: {ddl!r})"
        )

    raise ViewParseError(f"DEFINE VIEW missing AS body: {ddl!r}")


def _read_balanced(text: str, pos: int, original_ddl: str) -> tuple[str, int]:
    """Read a balanced parenthesised expression starting at `pos`."""
    depth = 0
    end = pos
    while end < len(text):
        if text[end] == "(":
            depth += 1
        elif text[end] == ")":
            depth -= 1
            if depth == 0:
                end += 1
                return text[pos:end], end
        end += 1
    raise ViewParseError(f"unterminated parenthesised expression: {original_ddl!r}")


def _split_schema_and_name(fqn_text: str, original_ddl: str) -> tuple[str, str]:
    parts = [
        m.group("quoted").replace('""', '"') if m.group("quoted") else m.group("bare")
        for m in _FQN_PART_RE.finditer(fqn_text)
    ]
    if len(parts) == 3:
        return parts[1], parts[2]
    if len(parts) == 2:
        return parts[0], parts[1]
    raise ViewParseError(
        f"could not parse FQN {fqn_text!r} from DEFINE VIEW: {original_ddl!r}"
    )


def _wrap_body_with_raw_blocks(body: str, *, database: str) -> str:
    """Emit the SELECT body wrapped in `{% raw %}{% endraw %}` blocks, with
    references to `database` swapped for `{{ database }}` outside the raw
    blocks so DCM's Jinja pass substitutes the runtime database while
    leaving any literal `{{ }}` in the body intact."""
    pattern = re.compile(
        rf"(?<![A-Za-z0-9_$]){re.escape(database)}(?![A-Za-z0-9_$])",
        re.IGNORECASE,
    )
    parts: list[str] = []
    last = 0
    for match in pattern.finditer(body):
        if match.start() > last:
            parts.append("{% raw %}" + body[last : match.start()] + "{% endraw %}")
        parts.append("{{ database }}")
        last = match.end()
    if last < len(body):
        parts.append("{% raw %}" + body[last:] + "{% endraw %}")
    if not parts:
        return ""
    return "".join(parts)


class ViewPlugin(V1ObjectPlugin):
    type_name = "View"
    file_slug = "view"
    SHOW_FORM = "SHOW VIEWS"
    GET_DDL_TYPE = "VIEW"
    SUPPORTS_COMMENT = True
    MACRO_BODY = (
        "{% macro define_view(\n"
        "    database,\n"
        "    schema,\n"
        "    name,\n"
        "    secure=False,\n"
        "    recursive=False,\n"
        "    column_list=None,\n"
        "    copy_grants=False,\n"
        "    comment=None\n"
        ") %}\n"
        "DEFINE {% if secure %}SECURE {% endif %}"
        "{% if recursive %}RECURSIVE {% endif %}VIEW "
        "{{ database }}.{{ schema }}.{{ name }}"
        "{% if column_list %} {{ column_list }}{% endif %}"
        "{% if copy_grants %} COPY GRANTS{% endif %}"
        "{% if comment is not none %} COMMENT='{{ comment }}'{% endif %}"
        " AS\n"
        "{% endmacro %}\n"
    )

    def to_define_and_invocation(
        self,
        ddl: str,
        *,
        comment: str | None,
        use_macros: bool,
        database: str,
    ) -> str:
        # Views don't fit the `_macro_kwargs_from_ddl` shape because the body
        # has to live outside the macro invocation (so its `{% raw %}` markers
        # work during DCM's Jinja pass). When use_macros=False we fall back to
        # the inherited behaviour.
        if not use_macros:
            return super().to_define_and_invocation(
                ddl, comment=comment, use_macros=use_macros, database=database
            )

        # Don't use the base class's inject_comment_if_missing: for views it
        # appends COMMENT to the end, which is *after* the AS body and would
        # then be parsed as part of the body. Inject after parsing instead.
        define = create_to_define(ddl)
        kwargs = parse_view_ddl(define)
        body = kwargs.pop("body")
        if comment is not None and "comment" not in kwargs:
            kwargs["comment"] = comment
        kwargs["database"] = JinjaExpr("database")

        invocation = render_macro_invocation("define_view", kwargs=kwargs)
        wrapped_body = _wrap_body_with_raw_blocks(body, database=database)
        return f"{invocation}{wrapped_body}\n;\n"


plugin = ViewPlugin()
