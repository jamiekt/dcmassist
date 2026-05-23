"""Tests for the View plugin."""

from __future__ import annotations

from unittest.mock import MagicMock

import jinja2

from dcmexporter.objects.view import plugin
from dcmexporter.types import FQN


def test_discover_uses_show_views_in_database() -> None:
    cursor = MagicMock()
    cursor.fetchall.return_value = [
        {"name": "V1", "schema_name": "PUBLIC"},
        {"name": "V2", "schema_name": "PUBLIC"},
    ]
    out = plugin.discover(cursor, "MYDB", None)
    cursor.execute.assert_called_once_with("SHOW VIEWS IN DATABASE MYDB")
    assert [str(f) for f in out] == ["MYDB.PUBLIC.V1", "MYDB.PUBLIC.V2"]


def test_discover_filters_by_schema() -> None:
    cursor = MagicMock()
    cursor.fetchall.return_value = [{"name": "V", "schema_name": "S"}]
    plugin.discover(cursor, "MYDB", ("S",))
    cursor.execute.assert_called_once_with("SHOW VIEWS IN SCHEMA MYDB.S")


def test_get_ddl_calls_get_ddl_function() -> None:
    cursor = MagicMock()
    cursor.fetchone.return_value = ["CREATE OR REPLACE VIEW MYDB.PUBLIC.V AS SELECT 1"]
    fqn = FQN("MYDB", "PUBLIC", "V")
    out = plugin.get_ddl(cursor, fqn)
    cursor.execute.assert_called_once_with("SELECT GET_DDL('VIEW', 'MYDB.PUBLIC.V')")
    assert out.startswith("CREATE")


def test_to_define_and_invocation_macro_mode() -> None:
    out = plugin.to_define_and_invocation(
        "CREATE OR REPLACE VIEW MYDB.PUBLIC.V AS SELECT 1",
        comment="hi",
        use_macros=True,
        database="MYDB",
    )
    assert out.startswith("{{ define_view(")
    assert "raw=" in out


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
