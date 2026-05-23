"""Tests for the Schema plugin."""

from __future__ import annotations

from unittest.mock import MagicMock

import jinja2

from dcmexporter.objects.schema import plugin
from dcmexporter.types import FQN


def test_discover_uses_show_schemas_in_database_when_no_filter() -> None:
    cursor = MagicMock()
    sql_log: list[str] = []
    cursor.execute.side_effect = lambda sql: sql_log.append(sql)
    cursor.fetchall.return_value = [
        {"name": "PUBLIC", "database_name": "MYDB"},
        {"name": "INFORMATION_SCHEMA", "database_name": "MYDB"},
        {"name": "ANALYTICS", "database_name": "MYDB"},
    ]
    out = plugin.discover(cursor, "MYDB", None)
    assert sql_log == ["SHOW SCHEMAS IN DATABASE MYDB"]
    # INFORMATION_SCHEMA is excluded (system schema).
    assert [str(f) for f in out] == ["MYDB.ANALYTICS.ANALYTICS", "MYDB.PUBLIC.PUBLIC"]


def test_discover_filters_with_like_per_schema() -> None:
    cursor = MagicMock()
    sql_log: list[str] = []
    cursor.execute.side_effect = lambda sql: sql_log.append(sql)
    fetch_responses = iter(
        [
            [{"name": "S1", "database_name": "MYDB"}],
            [{"name": "S2", "database_name": "MYDB"}],
        ]
    )
    cursor.fetchall.side_effect = lambda: next(fetch_responses)

    out = plugin.discover(cursor, "MYDB", ("S1", "S2"))
    assert sql_log == [
        "SHOW SCHEMAS LIKE 'S1' IN DATABASE MYDB",
        "SHOW SCHEMAS LIKE 'S2' IN DATABASE MYDB",
    ]
    assert [str(f) for f in out] == ["MYDB.S1.S1", "MYDB.S2.S2"]


def test_get_ddl_calls_get_ddl_function() -> None:
    cursor = MagicMock()
    cursor.fetchone.return_value = ["CREATE OR REPLACE SCHEMA MYDB.PUBLIC"]
    fqn = FQN("MYDB", "PUBLIC", "PUBLIC")
    out = plugin.get_ddl(cursor, fqn)
    cursor.execute.assert_called_once_with(
        "SELECT GET_DDL('SCHEMA', 'MYDB.PUBLIC.PUBLIC')"
    )
    assert out.startswith("CREATE")


def test_to_define_and_invocation_macro_mode() -> None:
    out = plugin.to_define_and_invocation(
        "CREATE OR REPLACE SCHEMA MYDB.PUBLIC",
        comment="hi",
        use_macros=True,
        database="MYDB",
    )
    assert out.startswith("{{ define_schema(")
    assert "raw=" in out


def test_to_define_and_invocation_raw_mode() -> None:
    out = plugin.to_define_and_invocation(
        "CREATE OR REPLACE SCHEMA MYDB.PUBLIC",
        comment=None,
        use_macros=False,
        database="MYDB",
    )
    assert out.upper().startswith("DEFINE SCHEMA")
    assert "{{ database }}.PUBLIC" in out


def test_macro_definition_is_valid_jinja() -> None:
    env = jinja2.Environment()
    env.parse(plugin.macro_definition())
