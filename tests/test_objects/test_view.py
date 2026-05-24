"""Tests for the View plugin."""

from __future__ import annotations

from unittest.mock import MagicMock

import jinja2
import pytest

from dcmassist.objects.view import ViewParseError, parse_view_ddl, plugin
from dcmassist.types import FQN


def test_discover_lists_schemas_then_iterates() -> None:
    cursor = MagicMock()
    sql_log: list[str] = []
    cursor.execute.side_effect = lambda sql: sql_log.append(sql)
    fetch_responses = iter(
        [
            [{"name": "PUBLIC", "database_name": "MYDB"}],
            [
                {"name": "V1", "schema_name": "PUBLIC", "database_name": "MYDB"},
                {"name": "V2", "schema_name": "PUBLIC", "database_name": "MYDB"},
            ],
        ]
    )
    cursor.fetchall.side_effect = lambda: next(fetch_responses)

    out = plugin.discover(cursor, "MYDB", None)
    assert sql_log == [
        "SHOW SCHEMAS IN DATABASE MYDB LIMIT 10000",
        "SHOW VIEWS IN SCHEMA MYDB.PUBLIC LIMIT 10000",
    ]
    assert [str(f) for f in out] == ["MYDB.PUBLIC.V1", "MYDB.PUBLIC.V2"]


def test_discover_filters_by_schema() -> None:
    cursor = MagicMock()
    sql_log: list[str] = []
    cursor.execute.side_effect = lambda sql: sql_log.append(sql)
    cursor.fetchall.return_value = [
        {"name": "V", "schema_name": "S", "database_name": "MYDB"}
    ]
    out = plugin.discover(cursor, "MYDB", ("S",))
    assert sql_log == ["SHOW VIEWS IN SCHEMA MYDB.S LIMIT 10000"]
    assert [str(f) for f in out] == ["MYDB.S.V"]


def test_get_ddl_calls_get_ddl_function() -> None:
    cursor = MagicMock()
    cursor.fetchone.return_value = ["CREATE OR REPLACE VIEW MYDB.PUBLIC.V AS SELECT 1"]
    fqn = FQN("MYDB", "PUBLIC", "V")
    out = plugin.get_ddl(cursor, fqn)
    cursor.execute.assert_called_once_with(
        'SELECT GET_DDL(\'VIEW\', \'"MYDB"."PUBLIC"."V"\', TRUE)'
    )
    assert out.startswith("CREATE")


def test_to_define_and_invocation_macro_mode() -> None:
    out = plugin.to_define_and_invocation(
        "CREATE OR REPLACE VIEW MYDB.PUBLIC.V AS SELECT 1",
        comment="hi",
        use_macros=True,
        database="MYDB",
    )
    assert out.startswith("{{ define_view(")
    assert "raw=" not in out
    assert "database=database" in out
    assert "schema='PUBLIC'" in out
    assert "name='V'" in out
    # Body lives outside the macro call, wrapped in raw markers.
    assert "{% raw %}" in out
    assert "{% endraw %}" in out


def test_macro_round_trip_renders_full_ddl() -> None:
    """Render the macro+invocation through Jinja to confirm it produces valid
    DDL. Note: `{% raw %}` markers in the invocation are CONSUMED by this
    render pass — DCM runs the same single pass on the file we write, which
    is what the markers protect against. We check the rendered output below
    is the post-DCM-pass result."""
    out = plugin.to_define_and_invocation(
        "CREATE OR REPLACE SECURE VIEW MYDB.PUBLIC.V AS SELECT 1 AS X "
        "FROM MYDB.PUBLIC.T",
        comment="hi",
        use_macros=True,
        database="MYDB",
    )
    rendered = (
        jinja2.Environment()
        .from_string(plugin.macro_definition() + "\n" + out)
        .render(database="RUNTIME")
    )
    assert "DEFINE SECURE VIEW RUNTIME.PUBLIC.V" in rendered
    assert "COMMENT='hi'" in rendered
    assert " AS\n" in rendered
    assert "SELECT 1 AS X FROM RUNTIME.PUBLIC.T" in rendered
    assert "{{ database }}" not in rendered
    assert rendered.rstrip().endswith(";")


def test_body_with_jinja_braces_is_protected() -> None:
    """Literal `{{ x }}` in the body must survive DCM's render pass.

    The wrapped body in the invocation contains `{% raw %}{{ x }}{% endraw %}`;
    when DCM renders the file, the raw block keeps the `{{ x }}` literal
    intact. We exercise that single render pass here."""
    out = plugin.to_define_and_invocation(
        "CREATE OR REPLACE VIEW MYDB.PUBLIC.V AS SELECT '{{ x }}' AS LITERAL",
        comment=None,
        use_macros=True,
        database="MYDB",
    )
    # The invocation written to disk must contain raw markers so DCM's pass
    # honours the literal `{{ x }}`.
    assert "{% raw %}" in out
    assert "{% endraw %}" in out

    rendered = (
        jinja2.Environment()
        .from_string(plugin.macro_definition() + "\n" + out)
        .render(database="RUNTIME")
    )
    # After Jinja's render, the raw block is consumed but its content is
    # preserved literally — that is exactly the property the markers are
    # there to provide.
    assert "{{ x }}" in rendered


def test_to_define_and_invocation_raw_mode() -> None:
    out = plugin.to_define_and_invocation(
        "CREATE OR REPLACE VIEW MYDB.PUBLIC.V AS SELECT 1",
        comment=None,
        use_macros=False,
        database="MYDB",
    )
    assert out.upper().startswith("DEFINE VIEW")
    assert "{{ database }}.PUBLIC.V" in out


def test_macro_definition_is_valid_jinja() -> None:
    env = jinja2.Environment()
    env.parse(plugin.macro_definition())


@pytest.mark.parametrize(
    "ddl,expected",
    [
        (
            "DEFINE VIEW MYDB.PUBLIC.V AS SELECT 1",
            {"schema": "PUBLIC", "name": "V", "body": "SELECT 1"},
        ),
        (
            "DEFINE SECURE VIEW MYDB.PUBLIC.V AS SELECT 1",
            {
                "schema": "PUBLIC",
                "name": "V",
                "secure": True,
                "body": "SELECT 1",
            },
        ),
        (
            "DEFINE RECURSIVE VIEW MYDB.PUBLIC.V AS SELECT 1",
            {
                "schema": "PUBLIC",
                "name": "V",
                "recursive": True,
                "body": "SELECT 1",
            },
        ),
        (
            "DEFINE VIEW MYDB.PUBLIC.V (A, B) AS SELECT 1, 2",
            {
                "schema": "PUBLIC",
                "name": "V",
                "column_list": "(A, B)",
                "body": "SELECT 1, 2",
            },
        ),
        (
            "DEFINE VIEW MYDB.PUBLIC.V COPY GRANTS AS SELECT 1",
            {
                "schema": "PUBLIC",
                "name": "V",
                "copy_grants": True,
                "body": "SELECT 1",
            },
        ),
        (
            "DEFINE VIEW MYDB.PUBLIC.V COMMENT='hi' AS SELECT 1",
            {
                "schema": "PUBLIC",
                "name": "V",
                "comment": "hi",
                "body": "SELECT 1",
            },
        ),
        (
            "DEFINE VIEW {{ database }}.PUBLIC.V AS SELECT 1",
            {"schema": "PUBLIC", "name": "V", "body": "SELECT 1"},
        ),
    ],
)
def test_parse_view_ddl_clauses(ddl: str, expected: dict) -> None:
    assert parse_view_ddl(ddl) == expected


@pytest.mark.parametrize(
    "ddl",
    [
        # Per-column policies not supported in v1.
        "DEFINE VIEW MYDB.PUBLIC.V (A MASKING POLICY P) AS SELECT 1",
        # Top-level row access policy not supported.
        "DEFINE VIEW MYDB.PUBLIC.V WITH ROW ACCESS POLICY P ON (A) AS SELECT 1",
        # CREATE not yet rewritten.
        "CREATE VIEW MYDB.PUBLIC.V AS SELECT 1",
        # Missing AS body.
        "DEFINE VIEW MYDB.PUBLIC.V",
    ],
)
def test_parse_view_ddl_rejects_unsupported(ddl: str) -> None:
    with pytest.raises(ViewParseError):
        parse_view_ddl(ddl)
