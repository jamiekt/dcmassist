"""Tests for the Tag plugin."""

from __future__ import annotations

from unittest.mock import MagicMock

import jinja2
import pytest

from dcmassist.objects.tag import TagParseError, parse_tag_ddl, plugin
from dcmassist.types import FQN


def test_discover_lists_schemas_then_iterates() -> None:
    cursor = MagicMock()
    sql_log: list[str] = []
    cursor.execute.side_effect = lambda sql: sql_log.append(sql)
    fetch_responses = iter(
        [
            [{"name": "PUBLIC", "database_name": "MYDB"}],
            [
                {"name": "TG1", "schema_name": "PUBLIC", "database_name": "MYDB"},
                {"name": "TG2", "schema_name": "PUBLIC", "database_name": "MYDB"},
            ],
        ]
    )
    cursor.fetchall.side_effect = lambda: next(fetch_responses)

    out = plugin.discover(cursor, "MYDB", None)
    assert sql_log == [
        "SHOW SCHEMAS IN DATABASE MYDB LIMIT 10000",
        "SHOW TAGS IN SCHEMA MYDB.PUBLIC LIMIT 10000",
    ]
    assert [str(f) for f in out] == ["MYDB.PUBLIC.TG1", "MYDB.PUBLIC.TG2"]


def test_discover_filters_by_schema() -> None:
    cursor = MagicMock()
    sql_log: list[str] = []
    cursor.execute.side_effect = lambda sql: sql_log.append(sql)
    cursor.fetchall.return_value = [
        {"name": "TG", "schema_name": "S", "database_name": "MYDB"}
    ]
    out = plugin.discover(cursor, "MYDB", ("S",))
    assert sql_log == ["SHOW TAGS IN SCHEMA MYDB.S LIMIT 10000"]
    assert [str(f) for f in out] == ["MYDB.S.TG"]


def test_get_ddl_calls_get_ddl_function() -> None:
    cursor = MagicMock()
    cursor.fetchone.return_value = ["CREATE OR REPLACE TAG MYDB.PUBLIC.TG"]
    fqn = FQN("MYDB", "PUBLIC", "TG")
    out = plugin.get_ddl(cursor, fqn)
    cursor.execute.assert_called_once_with(
        'SELECT GET_DDL(\'TAG\', \'"MYDB"."PUBLIC"."TG"\', TRUE)'
    )
    assert out.startswith("CREATE")


def test_to_define_and_invocation_macro_mode() -> None:
    out = plugin.to_define_and_invocation(
        "CREATE OR REPLACE TAG MYDB.PUBLIC.TG",
        comment="hi",
        use_macros=True,
        database="MYDB",
    )
    assert out.startswith("{{ define_tag(")
    assert "raw=" not in out
    assert "database=database" in out
    assert "schema='PUBLIC'" in out
    assert "name='TG'" in out


def test_macro_round_trip_renders_full_ddl() -> None:
    out = plugin.to_define_and_invocation(
        "CREATE OR REPLACE TAG MYDB.PUBLIC.TG ALLOWED_VALUES 'a', 'b'",
        comment="hi",
        use_macros=True,
        database="MYDB",
    )
    rendered = (
        jinja2.Environment()
        .from_string(plugin.macro_definition() + "\n" + out)
        .render(database="RUNTIME")
    )
    assert "DEFINE TAG RUNTIME.PUBLIC.TG" in rendered
    assert "ALLOWED_VALUES 'a', 'b'" in rendered
    assert "COMMENT='hi'" in rendered
    assert "{{ database }}" not in rendered


def test_to_define_and_invocation_raw_mode() -> None:
    out = plugin.to_define_and_invocation(
        "CREATE OR REPLACE TAG MYDB.PUBLIC.TG",
        comment=None,
        use_macros=False,
        database="MYDB",
    )
    assert out.upper().startswith("DEFINE TAG")
    assert "{{ database }}.PUBLIC.TG" in out


def test_macro_definition_is_valid_jinja() -> None:
    env = jinja2.Environment()
    env.parse(plugin.macro_definition())


@pytest.mark.parametrize(
    "ddl,expected",
    [
        (
            "DEFINE TAG MYDB.PUBLIC.TG;",
            {"schema": "PUBLIC", "name": "TG"},
        ),
        (
            "DEFINE TAG MYDB.PUBLIC.TG ALLOWED_VALUES 'a', 'b', 'c';",
            {
                "schema": "PUBLIC",
                "name": "TG",
                "allowed_values": ["a", "b", "c"],
            },
        ),
        (
            "DEFINE TAG MYDB.PUBLIC.TG COMMENT='it''s fine';",
            {"schema": "PUBLIC", "name": "TG", "comment": "it's fine"},
        ),
        (
            "DEFINE TAG MYDB.PUBLIC.TG ALLOWED_VALUES 'a' COMMENT='hi';",
            {
                "schema": "PUBLIC",
                "name": "TG",
                "allowed_values": ["a"],
                "comment": "hi",
            },
        ),
        (
            'DEFINE TAG "my-db"."weird schema"."123tag";',
            {"schema": "weird schema", "name": "123tag"},
        ),
        (
            "DEFINE TAG {{ database }}.PUBLIC.TG;",
            {"schema": "PUBLIC", "name": "TG"},
        ),
    ],
)
def test_parse_tag_ddl_clauses(ddl: str, expected: dict) -> None:
    assert parse_tag_ddl(ddl) == expected


@pytest.mark.parametrize(
    "ddl",
    [
        "DEFINE TAG MYDB.PUBLIC.TG HELLO=WORLD;",
        "CREATE TAG MYDB.PUBLIC.TG;",
        "DEFINE TAG",
    ],
)
def test_parse_tag_ddl_rejects_unsupported(ddl: str) -> None:
    with pytest.raises(TagParseError):
        parse_tag_ddl(ddl)
