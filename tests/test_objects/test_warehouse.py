"""Tests for the Warehouse plugin."""

from __future__ import annotations

from unittest.mock import MagicMock

import jinja2

from dcmexporter.objects.warehouse import plugin
from dcmexporter.types import FQN


def test_discover_uses_show_warehouses() -> None:
    cursor = MagicMock()
    cursor.fetchall.return_value = [{"name": "W1"}, {"name": "W2"}]
    out = plugin.discover(cursor, "MYDB", None)
    cursor.execute.assert_called_once_with("SHOW WAREHOUSES")
    assert [str(f) for f in out] == ["W1", "W2"]


def test_discover_filters_by_schema() -> None:
    cursor = MagicMock()
    cursor.fetchall.return_value = [{"name": "W"}]
    plugin.discover(cursor, "MYDB", ("S",))
    cursor.execute.assert_called_once_with("SHOW WAREHOUSES")


def test_get_ddl_calls_get_ddl_function() -> None:
    cursor = MagicMock()
    cursor.fetchone.return_value = [
        "CREATE OR REPLACE WAREHOUSE W WITH WAREHOUSE_SIZE = 'XSMALL'"
    ]
    fqn = FQN("MYDB", None, "W")
    out = plugin.get_ddl(cursor, fqn)
    cursor.execute.assert_called_once_with("SELECT GET_DDL('WAREHOUSE', 'W')")
    assert out.startswith("CREATE")


def test_to_define_and_invocation_macro_mode() -> None:
    out = plugin.to_define_and_invocation(
        "CREATE OR REPLACE WAREHOUSE W WITH WAREHOUSE_SIZE = 'XSMALL'",
        comment="hi",
        use_macros=True,
        database="MYDB",
    )
    assert out.startswith("{{ define_warehouse(")
    assert "raw=" in out


def test_to_define_and_invocation_raw_mode() -> None:
    out = plugin.to_define_and_invocation(
        "CREATE OR REPLACE WAREHOUSE W WITH WAREHOUSE_SIZE = 'XSMALL'",
        comment=None,
        use_macros=False,
        database="MYDB",
    )
    assert out.upper().startswith("DEFINE WAREHOUSE")


def test_macro_definition_is_valid_jinja() -> None:
    env = jinja2.Environment()
    env.parse(plugin.macro_definition())
