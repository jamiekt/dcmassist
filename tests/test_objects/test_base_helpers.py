"""Tests for V1ObjectPlugin shared helpers."""

from __future__ import annotations

import pytest

from dcmexporter.objects._base import V1ObjectPlugin


class _MinimalPlugin(V1ObjectPlugin):
    type_name = "Test"
    file_slug = "test"
    SHOW_FORM = "SHOW THINGS"
    GET_DDL_TYPE = "THING"
    MACRO_BODY = "{% macro define_test() %}{% endmacro %}"


def test_rows_to_fqns_uses_schema_name_key() -> None:
    """Real Snowflake column is `schema_name` (per SHOW VIEWS/TABLES/etc)."""
    plugin = _MinimalPlugin()
    rows = [{"name": "T1", "schema_name": "PUBLIC", "database_name": "MYDB"}]
    out = plugin._rows_to_fqns(rows, "MYDB")
    assert [str(f) for f in out] == ["MYDB.PUBLIC.T1"]


def test_rows_to_fqns_rejects_tuple_rows() -> None:
    """With DictCursor mandatory, tuple rows are an error."""
    plugin = _MinimalPlugin()
    with pytest.raises((TypeError, KeyError)):
        plugin._rows_to_fqns([("created", "T1", "MYDB", "PUBLIC")], "MYDB")
