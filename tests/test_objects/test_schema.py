"""Tests for the Schema plugin."""

from __future__ import annotations

from unittest.mock import MagicMock

import jinja2
import pytest

from dcmassist.objects.schema import SchemaParseError, parse_schema_ddl, plugin
from dcmassist.types import FQN


def test_discover_uses_show_schemas_in_database_when_no_filter() -> None:
    cursor = MagicMock()
    sql_log: list[str] = []
    cursor.execute.side_effect = lambda sql: sql_log.append(sql)
    cursor.fetchall.return_value = [
        {"name": "PUBLIC", "database_name": "MYDB"},
        {"name": "INFORMATION_SCHEMA", "database_name": "MYDB"},
        {"name": "ANALYTICS", "database_name": "MYDB"},
    ]
    out = plugin.discover(cursor, "MYDB", None)
    assert sql_log == ["SHOW SCHEMAS IN DATABASE MYDB LIMIT 10000"]
    # INFORMATION_SCHEMA is excluded (system schema).
    assert [str(f) for f in out] == ["MYDB.ANALYTICS.ANALYTICS", "MYDB.PUBLIC.PUBLIC"]


def test_discover_filters_with_like_per_schema() -> None:
    cursor = MagicMock()
    sql_log: list[str] = []
    cursor.execute.side_effect = lambda sql: sql_log.append(sql)
    fetch_responses = iter(
        [
            [{"name": "S1", "database_name": "MYDB"}],
            [{"name": "S2", "database_name": "MYDB"}],
        ]
    )
    cursor.fetchall.side_effect = lambda: next(fetch_responses)

    out = plugin.discover(cursor, "MYDB", ("S1", "S2"))
    assert sql_log == [
        "SHOW SCHEMAS LIKE 'S1' IN DATABASE MYDB",
        "SHOW SCHEMAS LIKE 'S2' IN DATABASE MYDB",
    ]
    assert [str(f) for f in out] == ["MYDB.S1.S1", "MYDB.S2.S2"]


def test_get_ddl_synthesizes_from_show_schemas() -> None:
    """get_ddl uses SHOW SCHEMAS (not recursive GET_DDL) to build CREATE."""
    cursor = MagicMock()
    cursor.execute.return_value = None
    cursor.fetchall.return_value = [
        {
            "name": "PUBLIC",
            "database_name": "MYDB",
            "comment": "the schema",
            "options": "",
        }
    ]
    fqn = FQN("MYDB", "PUBLIC", "PUBLIC")
    out = plugin.get_ddl(cursor, fqn)
    cursor.execute.assert_called_once_with(
        "SHOW SCHEMAS LIKE 'PUBLIC' IN DATABASE MYDB"
    )
    assert out.startswith("CREATE OR REPLACE SCHEMA MYDB.PUBLIC")
    assert "COMMENT='the schema'" in out


def test_to_define_and_invocation_macro_mode() -> None:
    out = plugin.to_define_and_invocation(
        "CREATE OR REPLACE SCHEMA MYDB.PUBLIC",
        comment="hi",
        use_macros=True,
        database="MYDB",
    )
    assert out.startswith("{{ define_schema(")
    # No raw=: every clause must be a structured kwarg.
    assert "raw=" not in out
    assert "database=database" in out
    assert "name='PUBLIC'" in out


def test_macro_round_trip_renders_full_ddl() -> None:
    out = plugin.to_define_and_invocation(
        "CREATE OR REPLACE TRANSIENT SCHEMA MYDB.PUBLIC\n  WITH MANAGED ACCESS",
        comment="hi",
        use_macros=True,
        database="MYDB",
    )
    rendered = (
        jinja2.Environment()
        .from_string(plugin.macro_definition() + "\n" + out)
        .render(database="RUNTIME")
    )
    assert "DEFINE TRANSIENT SCHEMA RUNTIME.PUBLIC" in rendered
    assert "WITH MANAGED ACCESS" in rendered
    assert "COMMENT='hi'" in rendered
    assert "{{ database }}" not in rendered


def test_to_define_and_invocation_raw_mode() -> None:
    out = plugin.to_define_and_invocation(
        "CREATE OR REPLACE SCHEMA MYDB.PUBLIC",
        comment=None,
        use_macros=False,
        database="MYDB",
    )
    assert out.upper().startswith("DEFINE SCHEMA")
    assert "{{ database }}.PUBLIC" in out


def test_macro_definition_is_valid_jinja() -> None:
    env = jinja2.Environment()
    env.parse(plugin.macro_definition())


@pytest.mark.parametrize(
    "ddl,expected",
    [
        (
            "DEFINE SCHEMA MYDB.PUBLIC;",
            {"name": "PUBLIC"},
        ),
        (
            "DEFINE TRANSIENT SCHEMA MYDB.PUBLIC;",
            {"name": "PUBLIC", "transient": True},
        ),
        (
            "DEFINE SCHEMA MYDB.PUBLIC WITH MANAGED ACCESS;",
            {"name": "PUBLIC", "managed_access": True},
        ),
        (
            "DEFINE SCHEMA MYDB.PUBLIC DATA_RETENTION_TIME_IN_DAYS = 7 "
            "MAX_DATA_EXTENSION_TIME_IN_DAYS = 14;",
            {
                "name": "PUBLIC",
                "data_retention_time_in_days": 7,
                "max_data_extension_time_in_days": 14,
            },
        ),
        (
            "DEFINE SCHEMA MYDB.PUBLIC DEFAULT_DDL_COLLATION = 'en-ci';",
            {"name": "PUBLIC", "default_ddl_collation": "en-ci"},
        ),
        (
            "DEFINE SCHEMA MYDB.PUBLIC COMMENT='it''s fine';",
            {"name": "PUBLIC", "comment": "it's fine"},
        ),
        (
            'DEFINE SCHEMA "my-db"."weird schema";',
            {"name": "weird schema"},
        ),
        (
            "DEFINE SCHEMA {{ database }}.PUBLIC;",
            {"name": "PUBLIC"},
        ),
    ],
)
def test_parse_schema_ddl_clauses(ddl: str, expected: dict) -> None:
    assert parse_schema_ddl(ddl) == expected


@pytest.mark.parametrize(
    "ddl",
    [
        "DEFINE SCHEMA MYDB.PUBLIC HELLO=WORLD;",
        "CREATE SCHEMA MYDB.PUBLIC;",
        "DEFINE SCHEMA",
    ],
)
def test_parse_schema_ddl_rejects_unsupported(ddl: str) -> None:
    with pytest.raises(SchemaParseError):
        parse_schema_ddl(ddl)
