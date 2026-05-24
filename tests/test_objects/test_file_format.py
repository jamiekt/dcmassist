"""Tests for the File format plugin."""

from __future__ import annotations

from unittest.mock import MagicMock

import jinja2
import pytest

from dcmassist.objects.file_format import (
    FileFormatParseError,
    parse_file_format_ddl,
    plugin,
)
from dcmassist.types import FQN


def test_discover_lists_schemas_then_iterates() -> None:
    cursor = MagicMock()
    sql_log: list[str] = []
    cursor.execute.side_effect = lambda sql: sql_log.append(sql)
    fetch_responses = iter(
        [
            [{"name": "PUBLIC", "database_name": "MYDB"}],
            [
                {"name": "FF1", "schema_name": "PUBLIC", "database_name": "MYDB"},
                {"name": "FF2", "schema_name": "PUBLIC", "database_name": "MYDB"},
            ],
        ]
    )
    cursor.fetchall.side_effect = lambda: next(fetch_responses)

    out = plugin.discover(cursor, "MYDB", None)
    assert sql_log == [
        "SHOW SCHEMAS IN DATABASE MYDB LIMIT 10000",
        "SHOW FILE FORMATS IN SCHEMA MYDB.PUBLIC LIMIT 10000",
    ]
    assert [str(f) for f in out] == ["MYDB.PUBLIC.FF1", "MYDB.PUBLIC.FF2"]


def test_discover_filters_by_schema() -> None:
    cursor = MagicMock()
    sql_log: list[str] = []
    cursor.execute.side_effect = lambda sql: sql_log.append(sql)
    cursor.fetchall.return_value = [
        {"name": "FF", "schema_name": "S", "database_name": "MYDB"}
    ]
    out = plugin.discover(cursor, "MYDB", ("S",))
    assert sql_log == ["SHOW FILE FORMATS IN SCHEMA MYDB.S LIMIT 10000"]
    assert [str(f) for f in out] == ["MYDB.S.FF"]


def test_get_ddl_calls_get_ddl_function() -> None:
    cursor = MagicMock()
    cursor.fetchone.return_value = [
        "CREATE OR REPLACE FILE FORMAT MYDB.PUBLIC.FF TYPE = CSV"
    ]
    fqn = FQN("MYDB", "PUBLIC", "FF")
    out = plugin.get_ddl(cursor, fqn)
    cursor.execute.assert_called_once_with(
        'SELECT GET_DDL(\'FILE_FORMAT\', \'"MYDB"."PUBLIC"."FF"\', TRUE)'
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
    assert "raw=" not in out
    assert "database=database" in out
    assert "schema='PUBLIC'" in out
    assert "name='FF'" in out


def test_macro_round_trip_renders_full_ddl() -> None:
    out = plugin.to_define_and_invocation(
        "CREATE OR REPLACE FILE FORMAT MYDB.PUBLIC.FF "
        "TYPE = 'CSV' FIELD_DELIMITER = ',' SKIP_HEADER = 1",
        comment="hi",
        use_macros=True,
        database="MYDB",
    )
    rendered = (
        jinja2.Environment()
        .from_string(plugin.macro_definition() + "\n" + out)
        .render(database="RUNTIME")
    )
    assert "DEFINE FILE FORMAT RUNTIME.PUBLIC.FF" in rendered
    assert "TYPE = 'CSV'" in rendered
    assert "FIELD_DELIMITER = ','" in rendered
    assert "SKIP_HEADER = 1" in rendered
    assert "COMMENT='hi'" in rendered
    assert "{{ database }}" not in rendered


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


@pytest.mark.parametrize(
    "ddl,expected",
    [
        (
            "DEFINE FILE FORMAT MYDB.PUBLIC.FF TYPE = CSV;",
            {
                "schema": "PUBLIC",
                "name": "FF",
                "options": {"TYPE": "CSV"},
            },
        ),
        (
            "DEFINE FILE FORMAT MYDB.PUBLIC.FF TYPE = 'CSV' "
            "FIELD_DELIMITER = ',' SKIP_HEADER = 1;",
            {
                "schema": "PUBLIC",
                "name": "FF",
                "options": {
                    "TYPE": "'CSV'",
                    "FIELD_DELIMITER": "','",
                    "SKIP_HEADER": "1",
                },
            },
        ),
        (
            "DEFINE FILE FORMAT MYDB.PUBLIC.FF TYPE = 'CSV' "
            "NULL_IF = ('NULL', '\\\\N');",
            {
                "schema": "PUBLIC",
                "name": "FF",
                "options": {
                    "TYPE": "'CSV'",
                    "NULL_IF": "('NULL', '\\\\N')",
                },
            },
        ),
        (
            "DEFINE FILE FORMAT MYDB.PUBLIC.FF TYPE = JSON COMMENT='it''s fine';",
            {
                "schema": "PUBLIC",
                "name": "FF",
                "options": {"TYPE": "JSON"},
                "comment": "it's fine",
            },
        ),
        (
            "DEFINE FILE FORMAT MYDB.PUBLIC.FF;",
            {"schema": "PUBLIC", "name": "FF"},
        ),
        (
            'DEFINE FILE FORMAT "my-db"."weird schema"."123ff" TYPE = CSV;',
            {
                "schema": "weird schema",
                "name": "123ff",
                "options": {"TYPE": "CSV"},
            },
        ),
        (
            "DEFINE FILE FORMAT {{ database }}.PUBLIC.FF TYPE = CSV;",
            {
                "schema": "PUBLIC",
                "name": "FF",
                "options": {"TYPE": "CSV"},
            },
        ),
    ],
)
def test_parse_file_format_ddl_clauses(ddl: str, expected: dict) -> None:
    assert parse_file_format_ddl(ddl) == expected


@pytest.mark.parametrize(
    "ddl",
    [
        "CREATE FILE FORMAT MYDB.PUBLIC.FF TYPE = CSV;",
        "DEFINE FILE FORMAT",
    ],
)
def test_parse_file_format_ddl_rejects_unsupported(ddl: str) -> None:
    with pytest.raises(FileFormatParseError):
        parse_file_format_ddl(ddl)
