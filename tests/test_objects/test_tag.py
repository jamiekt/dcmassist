"""Tests for the Tag plugin."""

from __future__ import annotations

from unittest.mock import MagicMock

import jinja2

from dcmexporter.objects.tag import plugin
from dcmexporter.types import FQN


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
        'SELECT GET_DDL(\'TAG\', \'"MYDB"."PUBLIC"."TG"\')'
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
    assert "raw=" in out


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
