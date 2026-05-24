"""Tests for the Table plugin."""

from __future__ import annotations

from unittest.mock import MagicMock

import jinja2
import pytest

from dcmassist.objects.table import TableParseError, parse_table_ddl, plugin
from dcmassist.types import FQN


def test_discover_lists_schemas_then_iterates() -> None:
    cursor = MagicMock()
    sql_log: list[str] = []
    cursor.execute.side_effect = lambda sql: sql_log.append(sql)
    fetch_responses = iter(
        [
            [{"name": "PUBLIC", "database_name": "MYDB"}],
            [
                {"name": "T1", "schema_name": "PUBLIC", "database_name": "MYDB"},
                {"name": "T2", "schema_name": "PUBLIC", "database_name": "MYDB"},
            ],
        ]
    )
    cursor.fetchall.side_effect = lambda: next(fetch_responses)

    out = plugin.discover(cursor, "MYDB", None)
    assert sql_log == [
        "SHOW SCHEMAS IN DATABASE MYDB LIMIT 10000",
        "SHOW TABLES IN SCHEMA MYDB.PUBLIC LIMIT 10000",
    ]
    assert [str(f) for f in out] == ["MYDB.PUBLIC.T1", "MYDB.PUBLIC.T2"]


def test_discover_filters_by_schema() -> None:
    cursor = MagicMock()
    sql_log: list[str] = []
    cursor.execute.side_effect = lambda sql: sql_log.append(sql)
    cursor.fetchall.return_value = [
        {"name": "T", "schema_name": "S", "database_name": "MYDB"}
    ]
    out = plugin.discover(cursor, "MYDB", ("S",))
    assert sql_log == ["SHOW TABLES IN SCHEMA MYDB.S LIMIT 10000"]
    assert [str(f) for f in out] == ["MYDB.S.T"]


def test_get_ddl_calls_get_ddl_function() -> None:
    cursor = MagicMock()
    cursor.fetchone.return_value = ["CREATE OR REPLACE TABLE MYDB.PUBLIC.T (X INT)"]
    fqn = FQN("MYDB", "PUBLIC", "T")
    out = plugin.get_ddl(cursor, fqn)
    cursor.execute.assert_called_once_with(
        'SELECT GET_DDL(\'TABLE\', \'"MYDB"."PUBLIC"."T"\', TRUE)'
    )
    assert out.startswith("CREATE")


def test_to_define_and_invocation_macro_mode() -> None:
    out = plugin.to_define_and_invocation(
        "CREATE OR REPLACE TABLE MYDB.PUBLIC.T (X INT)",
        comment="hi",
        use_macros=True,
        database="MYDB",
    )
    assert out.startswith("{{ define_table(")
    assert "raw=" not in out
    assert "database=database" in out
    assert "schema='PUBLIC'" in out
    assert "name='T'" in out


def test_macro_round_trip_renders_full_ddl() -> None:
    out = plugin.to_define_and_invocation(
        "CREATE OR REPLACE TRANSIENT TABLE MYDB.PUBLIC.T ("
        "ID INT NOT NULL, NAME VARCHAR(100) DEFAULT 'x') "
        "CLUSTER BY (ID) DATA_RETENTION_TIME_IN_DAYS = 3 "
        "CHANGE_TRACKING = TRUE COPY GRANTS",
        comment="hi",
        use_macros=True,
        database="MYDB",
    )
    rendered = (
        jinja2.Environment()
        .from_string(plugin.macro_definition() + "\n" + out)
        .render(database="RUNTIME")
    )
    assert "DEFINE TRANSIENT TABLE RUNTIME.PUBLIC.T" in rendered
    assert "ID INT NOT NULL" in rendered
    assert "NAME VARCHAR(100) DEFAULT 'x'" in rendered
    assert "CLUSTER BY (ID)" in rendered
    assert "DATA_RETENTION_TIME_IN_DAYS = 3" in rendered
    assert "CHANGE_TRACKING = TRUE" in rendered
    assert "COPY GRANTS" in rendered
    assert "COMMENT='hi'" in rendered
    assert "{{ database }}" not in rendered


def test_to_define_and_invocation_raw_mode() -> None:
    out = plugin.to_define_and_invocation(
        "CREATE OR REPLACE TABLE MYDB.PUBLIC.T (X INT)",
        comment=None,
        use_macros=False,
        database="MYDB",
    )
    assert out.upper().startswith("DEFINE TABLE")
    assert "{{ database }}.PUBLIC.T" in out


def test_macro_definition_is_valid_jinja() -> None:
    env = jinja2.Environment()
    env.parse(plugin.macro_definition())


@pytest.mark.parametrize(
    "ddl,expected",
    [
        (
            "DEFINE TABLE MYDB.PUBLIC.T (X INT);",
            {"schema": "PUBLIC", "name": "T", "columns": ["X INT"]},
        ),
        (
            "DEFINE TRANSIENT TABLE MYDB.PUBLIC.T (X INT, Y VARCHAR);",
            {
                "schema": "PUBLIC",
                "name": "T",
                "transient": True,
                "columns": ["X INT", "Y VARCHAR"],
            },
        ),
        (
            "DEFINE TABLE MYDB.PUBLIC.T (X INT) CLUSTER BY (X, SUBSTR(X, 1, 4));",
            {
                "schema": "PUBLIC",
                "name": "T",
                "columns": ["X INT"],
                "cluster_by": ["X", "SUBSTR(X, 1, 4)"],
            },
        ),
        (
            "DEFINE TABLE MYDB.PUBLIC.T (X INT) "
            "DATA_RETENTION_TIME_IN_DAYS = 7 "
            "MAX_DATA_EXTENSION_TIME_IN_DAYS = 14;",
            {
                "schema": "PUBLIC",
                "name": "T",
                "columns": ["X INT"],
                "data_retention_time_in_days": 7,
                "max_data_extension_time_in_days": 14,
            },
        ),
        (
            "DEFINE TABLE MYDB.PUBLIC.T (X INT) CHANGE_TRACKING = TRUE;",
            {
                "schema": "PUBLIC",
                "name": "T",
                "columns": ["X INT"],
                "change_tracking": True,
            },
        ),
        (
            "DEFINE TABLE MYDB.PUBLIC.T (X INT) COPY GRANTS COMMENT='hi';",
            {
                "schema": "PUBLIC",
                "name": "T",
                "columns": ["X INT"],
                "copy_grants": True,
                "comment": "hi",
            },
        ),
        (
            "DEFINE TABLE MYDB.PUBLIC.T (X NUMBER(38,0) IDENTITY(1, 1) NOT NULL, "
            "Y VARCHAR(100) DEFAULT 'a''b' COLLATE 'en-ci');",
            {
                "schema": "PUBLIC",
                "name": "T",
                "columns": [
                    "X NUMBER(38,0) IDENTITY(1, 1) NOT NULL",
                    "Y VARCHAR(100) DEFAULT 'a''b' COLLATE 'en-ci'",
                ],
            },
        ),
        (
            'DEFINE TABLE "my-db"."weird"."T" (X INT);',
            {"schema": "weird", "name": "T", "columns": ["X INT"]},
        ),
        (
            "DEFINE TABLE {{ database }}.PUBLIC.T (X INT);",
            {"schema": "PUBLIC", "name": "T", "columns": ["X INT"]},
        ),
    ],
)
def test_parse_table_ddl_clauses(ddl: str, expected: dict) -> None:
    assert parse_table_ddl(ddl) == expected


@pytest.mark.parametrize(
    "ddl",
    [
        # Per-column masking policy not supported in v1.
        "DEFINE TABLE MYDB.PUBLIC.T (A INT MASKING POLICY P);",
        # Table-level row access policy not supported.
        "DEFINE TABLE MYDB.PUBLIC.T (A INT) WITH ROW ACCESS POLICY P ON (A);",
        # WITH TAG clause not supported.
        "DEFINE TABLE MYDB.PUBLIC.T (A INT) WITH TAG (MYDB.PUBLIC.TG = 'x');",
        # CREATE not yet rewritten.
        "CREATE TABLE MYDB.PUBLIC.T (X INT);",
        # Missing columns.
        "DEFINE TABLE MYDB.PUBLIC.T;",
        # Unknown clause.
        "DEFINE TABLE MYDB.PUBLIC.T (X INT) HELLO=WORLD;",
    ],
)
def test_parse_table_ddl_rejects_unsupported(ddl: str) -> None:
    with pytest.raises(TableParseError):
        parse_table_ddl(ddl)
