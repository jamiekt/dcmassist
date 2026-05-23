"""Tests for the File format plugin."""

from __future__ import annotations

from unittest.mock import MagicMock

import jinja2

from dcmexporter.objects.file_format import plugin
from dcmexporter.types import FQN


def test_discover_uses_show_file_formats_in_database() -> None:
    cursor = MagicMock()
    cursor.fetchall.return_value = [
        {"name": "FF1", "schema_name": "PUBLIC"},
        {"name": "FF2", "schema_name": "PUBLIC"},
    ]
    out = plugin.discover(cursor, "MYDB", None)
    cursor.execute.assert_called_once_with("SHOW FILE FORMATS IN DATABASE MYDB")
    assert [str(f) for f in out] == ["MYDB.PUBLIC.FF1", "MYDB.PUBLIC.FF2"]


def test_discover_filters_by_schema() -> None:
    cursor = MagicMock()
    cursor.fetchall.return_value = [{"name": "FF", "schema_name": "S"}]
    plugin.discover(cursor, "MYDB", ("S",))
    cursor.execute.assert_called_once_with("SHOW FILE FORMATS IN SCHEMA MYDB.S")


def test_get_ddl_calls_get_ddl_function() -> None:
    cursor = MagicMock()
    cursor.fetchone.return_value = [
        "CREATE OR REPLACE FILE FORMAT MYDB.PUBLIC.FF TYPE = CSV"
    ]
    fqn = FQN("MYDB", "PUBLIC", "FF")
    out = plugin.get_ddl(cursor, fqn)
    cursor.execute.assert_called_once_with(
        "SELECT GET_DDL('FILE_FORMAT', 'MYDB.PUBLIC.FF')"
    )
    assert out.startswith("CREATE")


def test_to_define_and_invocation_macro_mode() -> None:
    out = plugin.to_define_and_invocation(
        "CREATE OR REPLACE FILE FORMAT MYDB.PUBLIC.FF TYPE = CSV",
        comment="hi",
        use_macros=True,
        database="MYDB",
    )
    assert out.startswith("{{ define_file_format(")
    assert "raw=" in out


def test_to_define_and_invocation_raw_mode() -> None:
    out = plugin.to_define_and_invocation(
        "CREATE OR REPLACE FILE FORMAT MYDB.PUBLIC.FF TYPE = CSV",
        comment=None,
        use_macros=False,
        database="MYDB",
    )
    assert out.upper().startswith("DEFINE FILE FORMAT")
    assert "{{ database }}.PUBLIC.FF" in out


def test_macro_definition_is_valid_jinja() -> None:
    env = jinja2.Environment()
    env.parse(plugin.macro_definition())
