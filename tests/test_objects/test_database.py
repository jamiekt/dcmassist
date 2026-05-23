"""Tests for the Database plugin."""

from __future__ import annotations

from unittest.mock import MagicMock

import jinja2

from dcmexporter.objects.database import plugin
from dcmexporter.types import FQN


def test_discover_uses_show_databases_like() -> None:
    cursor = MagicMock()
    sql_log: list[str] = []
    cursor.execute.side_effect = lambda sql: sql_log.append(sql)
    cursor.fetchall.return_value = [{"name": "MYDB"}]
    out = plugin.discover(cursor, "MYDB", None)
    assert sql_log == ["SHOW DATABASES LIKE 'MYDB'"]
    assert [str(f) for f in out] == ["MYDB"]


def test_discover_ignores_schemas_argument() -> None:
    """Database is account-level; --schema is meaningless. Same SQL either way."""
    cursor = MagicMock()
    sql_log: list[str] = []
    cursor.execute.side_effect = lambda sql: sql_log.append(sql)
    cursor.fetchall.return_value = [{"name": "MYDB"}]
    plugin.discover(cursor, "MYDB", ("ANY",))
    assert sql_log == ["SHOW DATABASES LIKE 'MYDB'"]


def test_get_ddl_calls_get_ddl_function() -> None:
    cursor = MagicMock()
    cursor.fetchone.return_value = ["CREATE OR REPLACE DATABASE MYDB"]
    fqn = FQN("MYDB", None, "MYDB")
    out = plugin.get_ddl(cursor, fqn)
    cursor.execute.assert_called_once_with("SELECT GET_DDL('DATABASE', 'MYDB')")
    assert out.startswith("CREATE")


def test_to_define_and_invocation_macro_mode() -> None:
    out = plugin.to_define_and_invocation(
        "CREATE OR REPLACE DATABASE MYDB",
        comment="hi",
        use_macros=True,
        database="MYDB",
    )
    assert out.startswith("{{ define_database(")
    assert "raw=" in out


def test_to_define_and_invocation_raw_mode() -> None:
    out = plugin.to_define_and_invocation(
        "CREATE OR REPLACE DATABASE MYDB",
        comment=None,
        use_macros=False,
        database="MYDB",
    )
    assert out.upper().startswith("DEFINE DATABASE")
    assert "{{ database }}" in out


def test_macro_definition_is_valid_jinja() -> None:
    env = jinja2.Environment()
    env.parse(plugin.macro_definition())
