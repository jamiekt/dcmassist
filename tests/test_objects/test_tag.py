"""Tests for the Tag plugin."""

from __future__ import annotations

from unittest.mock import MagicMock

import jinja2

from dcmexporter.objects.tag import plugin
from dcmexporter.types import FQN


def test_discover_uses_show_tags_in_database() -> None:
    cursor = MagicMock()
    cursor.fetchall.return_value = [
        {"name": "TG1", "schema_name": "PUBLIC"},
        {"name": "TG2", "schema_name": "PUBLIC"},
    ]
    out = plugin.discover(cursor, "MYDB", None)
    cursor.execute.assert_called_once_with("SHOW TAGS IN DATABASE MYDB")
    assert [str(f) for f in out] == ["MYDB.PUBLIC.TG1", "MYDB.PUBLIC.TG2"]


def test_discover_filters_by_schema() -> None:
    cursor = MagicMock()
    cursor.fetchall.return_value = [{"name": "TG", "schema_name": "S"}]
    plugin.discover(cursor, "MYDB", ("S",))
    cursor.execute.assert_called_once_with("SHOW TAGS IN SCHEMA MYDB.S")


def test_get_ddl_calls_get_ddl_function() -> None:
    cursor = MagicMock()
    cursor.fetchone.return_value = ["CREATE OR REPLACE TAG MYDB.PUBLIC.TG"]
    fqn = FQN("MYDB", "PUBLIC", "TG")
    out = plugin.get_ddl(cursor, fqn)
    cursor.execute.assert_called_once_with("SELECT GET_DDL('TAG', 'MYDB.PUBLIC.TG')")
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
