"""Tests for the Stage plugin."""

from __future__ import annotations

from unittest.mock import MagicMock

import jinja2
import pytest

from dcmassist.objects.stage import StageParseError, parse_stage_ddl, plugin
from dcmassist.types import FQN


def test_discover_lists_schemas_then_iterates() -> None:
    cursor = MagicMock()
    sql_log: list[str] = []
    cursor.execute.side_effect = lambda sql: sql_log.append(sql)
    fetch_responses = iter(
        [
            [{"name": "PUBLIC", "database_name": "MYDB"}],
            [
                {"name": "ST1", "schema_name": "PUBLIC", "database_name": "MYDB"},
                {"name": "ST2", "schema_name": "PUBLIC", "database_name": "MYDB"},
            ],
        ]
    )
    cursor.fetchall.side_effect = lambda: next(fetch_responses)

    out = plugin.discover(cursor, "MYDB", None)
    assert sql_log == [
        "SHOW SCHEMAS IN DATABASE MYDB LIMIT 10000",
        "SHOW STAGES IN SCHEMA MYDB.PUBLIC LIMIT 10000",
    ]
    assert [str(f) for f in out] == ["MYDB.PUBLIC.ST1", "MYDB.PUBLIC.ST2"]


def test_discover_filters_by_schema() -> None:
    cursor = MagicMock()
    sql_log: list[str] = []
    cursor.execute.side_effect = lambda sql: sql_log.append(sql)
    cursor.fetchall.return_value = [
        {"name": "ST", "schema_name": "S", "database_name": "MYDB"}
    ]
    out = plugin.discover(cursor, "MYDB", ("S",))
    assert sql_log == ["SHOW STAGES IN SCHEMA MYDB.S LIMIT 10000"]
    assert [str(f) for f in out] == ["MYDB.S.ST"]


def test_get_ddl_uses_desc_stage_and_synthesizer() -> None:
    """Stage uses DESC STAGE + synthesizer; GET_DDL('STAGE',...) is unsupported."""
    cursor = MagicMock()
    sql_log: list[str] = []
    cursor.execute.side_effect = lambda sql: sql_log.append(sql)
    cursor.fetchall.return_value = [
        {
            "parent_property": "STAGE_LOCATION",
            "property": "URL",
            "property_value": '["s3://bucket/x/"]',
            "property_type": "String",
            "property_default": "",
        },
        {
            "parent_property": "STAGE_INTEGRATION",
            "property": "STORAGE_INTEGRATION",
            "property_value": "MY_INT",
            "property_type": "String",
            "property_default": "",
        },
    ]
    fqn = FQN("MYDB", "PUBLIC", "S")
    out = plugin.get_ddl(cursor, fqn)
    assert sql_log == ['DESC STAGE "MYDB"."PUBLIC"."S"']
    assert "CREATE OR REPLACE STAGE MYDB.PUBLIC.S" in out
    assert "STORAGE_INTEGRATION = MY_INT" in out


def test_to_define_and_invocation_macro_mode() -> None:
    ddl = (
        "CREATE OR REPLACE STAGE MYDB.PUBLIC.S\n"
        "  URL = 's3://bucket/x/'\n"
        "  STORAGE_INTEGRATION = MY_INT\n"
        ";"
    )
    out = plugin.to_define_and_invocation(
        ddl,
        comment="hi",
        use_macros=True,
        database="MYDB",
    )
    assert out.startswith("{{ define_stage(")
    assert "raw=" not in out
    assert "database=database" in out
    assert "schema='PUBLIC'" in out
    assert "name='S'" in out


def test_macro_round_trip_renders_full_ddl() -> None:
    ddl = (
        "CREATE OR REPLACE STAGE MYDB.PUBLIC.S\n"
        "  URL = 's3://bucket/x/'\n"
        "  STORAGE_INTEGRATION = MY_INT\n"
        ";"
    )
    out = plugin.to_define_and_invocation(
        ddl,
        comment="hi",
        use_macros=True,
        database="MYDB",
    )
    rendered = (
        jinja2.Environment()
        .from_string(plugin.macro_definition() + "\n" + out)
        .render(database="RUNTIME")
    )
    assert "DEFINE STAGE RUNTIME.PUBLIC.S" in rendered
    assert "URL = 's3://bucket/x/'" in rendered
    assert "STORAGE_INTEGRATION = MY_INT" in rendered
    assert "COMMENT='hi'" in rendered
    assert "{{ database }}" not in rendered


def test_to_define_and_invocation_raw_mode() -> None:
    ddl = (
        "CREATE OR REPLACE STAGE MYDB.PUBLIC.S\n"
        "  URL = 's3://bucket/x/'\n"
        "  STORAGE_INTEGRATION = MY_INT\n"
        ";"
    )
    out = plugin.to_define_and_invocation(
        ddl,
        comment=None,
        use_macros=False,
        database="MYDB",
    )
    assert out.upper().startswith("DEFINE STAGE")
    assert "{{ database }}.PUBLIC.S" in out


def test_macro_definition_is_valid_jinja() -> None:
    env = jinja2.Environment()
    env.parse(plugin.macro_definition())


@pytest.mark.parametrize(
    "ddl,expected",
    [
        (
            "DEFINE STAGE MYDB.PUBLIC.S URL = 's3://x/' STORAGE_INTEGRATION = INT;",
            {
                "schema": "PUBLIC",
                "name": "S",
                "url": "s3://x/",
                "storage_integration": "INT",
            },
        ),
        (
            "DEFINE STAGE MYDB.PUBLIC.S URL = 's3://x/' STORAGE_INTEGRATION = INT "
            "COMMENT='hi';",
            {
                "schema": "PUBLIC",
                "name": "S",
                "url": "s3://x/",
                "storage_integration": "INT",
                "comment": "hi",
            },
        ),
        (
            'DEFINE STAGE "my-db"."weird"."S" URL = \'s3://x/\' STORAGE_INTEGRATION = INT;',
            {
                "schema": "weird",
                "name": "S",
                "url": "s3://x/",
                "storage_integration": "INT",
            },
        ),
        (
            "DEFINE STAGE {{ database }}.PUBLIC.S URL = 's3://x/' "
            "STORAGE_INTEGRATION = INT;",
            {
                "schema": "PUBLIC",
                "name": "S",
                "url": "s3://x/",
                "storage_integration": "INT",
            },
        ),
    ],
)
def test_parse_stage_ddl_clauses(ddl: str, expected: dict) -> None:
    assert parse_stage_ddl(ddl) == expected


@pytest.mark.parametrize(
    "ddl",
    [
        "DEFINE STAGE MYDB.PUBLIC.S CREDENTIALS = (AWS_KEY_ID = 'AK');",
        "CREATE STAGE MYDB.PUBLIC.S URL = 's3://x/';",
        "DEFINE STAGE",
    ],
)
def test_parse_stage_ddl_rejects_unsupported(ddl: str) -> None:
    with pytest.raises(StageParseError):
        parse_stage_ddl(ddl)
