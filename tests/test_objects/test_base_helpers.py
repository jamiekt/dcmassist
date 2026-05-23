"""Tests for V1ObjectPlugin shared helpers."""

from __future__ import annotations

from unittest.mock import MagicMock

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


def test_discover_iterates_schemas_when_no_filter() -> None:
    """When schemas=None, base discover lists schemas first then SHOWs per-schema.
    Avoids Snowflake's 10K-row limit on SHOW <type> IN DATABASE for large DBs.
    """
    cursor = MagicMock()
    sql_log: list[str] = []

    def execute(sql: str) -> None:
        sql_log.append(sql)

    schemas_response = [
        {"name": "PUBLIC", "database_name": "MYDB"},
        {"name": "INFORMATION_SCHEMA", "database_name": "MYDB"},
        {"name": "ANALYTICS", "database_name": "MYDB"},
    ]
    things_in_public = [{"name": "T1", "schema_name": "PUBLIC"}]
    things_in_analytics = [{"name": "T2", "schema_name": "ANALYTICS"}]

    fetch_responses = iter([schemas_response, things_in_public, things_in_analytics])
    cursor.execute.side_effect = execute
    cursor.fetchall.side_effect = lambda: next(fetch_responses)

    plugin = _MinimalPlugin()
    out = plugin.discover(cursor, "MYDB", None)

    assert sql_log == [
        "SHOW SCHEMAS IN DATABASE MYDB LIMIT 10000",
        "SHOW THINGS IN SCHEMA MYDB.ANALYTICS LIMIT 10000",
        "SHOW THINGS IN SCHEMA MYDB.PUBLIC LIMIT 10000",
    ]
    assert [str(f) for f in out] == ["MYDB.ANALYTICS.T2", "MYDB.PUBLIC.T1"]


def test_discover_reports_running_total_on_each_page() -> None:
    """For schemas with many objects, progress callback ticks up as pages arrive.

    Without this, schemas like EXPERIMENTATION.STATSIG (50k+ tables) would
    appear to hang while paginated_show silently fetches several 10k pages.
    """
    cursor = MagicMock()
    cursor.execute.side_effect = lambda sql: None
    cursor.fetchall.return_value = [
        {"name": "T1", "schema_name": "S"},
        {"name": "T2", "schema_name": "S"},
    ]

    seen: list[str] = []
    plugin = _MinimalPlugin()
    plugin.discover(cursor, "MYDB", ("S",), progress=seen.append)

    assert seen[0] == "discovering Tests in MYDB.S"
    assert any("found 2" in msg for msg in seen[1:]), seen


def test_discover_with_schemas_filter_skips_schema_listing() -> None:
    cursor = MagicMock()
    sql_log: list[str] = []

    def execute(sql: str) -> None:
        sql_log.append(sql)

    cursor.execute.side_effect = execute
    cursor.fetchall.return_value = [
        {"name": "T", "schema_name": "S"},
    ]

    plugin = _MinimalPlugin()
    out = plugin.discover(cursor, "MYDB", ("S",))

    assert sql_log == ["SHOW THINGS IN SCHEMA MYDB.S LIMIT 10000"]
    assert [str(f) for f in out] == ["MYDB.S.T"]
