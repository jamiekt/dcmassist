"""Tests for the Sequence plugin."""

from __future__ import annotations

from unittest.mock import MagicMock

import jinja2

from dcmexporter.objects.sequence import plugin
from dcmexporter.types import FQN


def test_discover_uses_show_sequences_in_database() -> None:
    cursor = MagicMock()
    cursor.fetchall.return_value = [
        {"name": "SEQ1", "schema_name": "PUBLIC"},
        {"name": "SEQ2", "schema_name": "PUBLIC"},
    ]
    out = plugin.discover(cursor, "MYDB", None)
    cursor.execute.assert_called_once_with("SHOW SEQUENCES IN DATABASE MYDB")
    assert [str(f) for f in out] == ["MYDB.PUBLIC.SEQ1", "MYDB.PUBLIC.SEQ2"]


def test_discover_filters_by_schema() -> None:
    cursor = MagicMock()
    cursor.fetchall.return_value = [{"name": "SEQ", "schema_name": "S"}]
    plugin.discover(cursor, "MYDB", ("S",))
    cursor.execute.assert_called_once_with("SHOW SEQUENCES IN SCHEMA MYDB.S")


def test_get_ddl_calls_get_ddl_function() -> None:
    cursor = MagicMock()
    cursor.fetchone.return_value = [
        "CREATE OR REPLACE SEQUENCE MYDB.PUBLIC.SEQ START = 1"
    ]
    fqn = FQN("MYDB", "PUBLIC", "SEQ")
    out = plugin.get_ddl(cursor, fqn)
    cursor.execute.assert_called_once_with(
        "SELECT GET_DDL('SEQUENCE', 'MYDB.PUBLIC.SEQ')"
    )
    assert out.startswith("CREATE")


def test_to_define_and_invocation_macro_mode() -> None:
    out = plugin.to_define_and_invocation(
        "CREATE OR REPLACE SEQUENCE MYDB.PUBLIC.SEQ START = 1",
        comment="hi",
        use_macros=True,
        database="MYDB",
    )
    assert out.startswith("{{ define_sequence(")
    assert "raw=" in out


def test_to_define_and_invocation_raw_mode() -> None:
    out = plugin.to_define_and_invocation(
        "CREATE OR REPLACE SEQUENCE MYDB.PUBLIC.SEQ START = 1",
        comment=None,
        use_macros=False,
        database="MYDB",
    )
    assert out.upper().startswith("DEFINE SEQUENCE")
    assert "{{ database }}.PUBLIC.SEQ" in out


def test_macro_definition_is_valid_jinja() -> None:
    env = jinja2.Environment()
    env.parse(plugin.macro_definition())
