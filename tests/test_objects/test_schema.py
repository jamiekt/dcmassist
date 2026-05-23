"""Tests for the Schema plugin."""

from __future__ import annotations

from unittest.mock import MagicMock

import jinja2

from dcmexporter.objects.schema import plugin
from dcmexporter.types import FQN


def test_discover_uses_show_schemas_in_database() -> None:
    cursor = MagicMock()
    cursor.fetchall.return_value = [
        {"name": "S1", "schema_name": "S1"},
        {"name": "S2", "schema_name": "S2"},
    ]
    out = plugin.discover(cursor, "MYDB", None)
    cursor.execute.assert_called_once_with("SHOW SCHEMAS IN DATABASE MYDB")
    assert [str(f) for f in out] == ["MYDB.S1.S1", "MYDB.S2.S2"]


def test_discover_filters_by_schema() -> None:
    cursor = MagicMock()
    cursor.fetchall.return_value = [{"name": "S", "schema_name": "S"}]
    plugin.discover(cursor, "MYDB", ("S",))
    cursor.execute.assert_called_once_with("SHOW SCHEMAS IN SCHEMA MYDB.S")


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
