"""Tests for the Sequence plugin."""

from __future__ import annotations

from unittest.mock import MagicMock

import jinja2
import pytest

from dcmassist.objects.sequence import (
    SequenceParseError,
    parse_sequence_ddl,
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
                {"name": "SEQ1", "schema_name": "PUBLIC", "database_name": "MYDB"},
                {"name": "SEQ2", "schema_name": "PUBLIC", "database_name": "MYDB"},
            ],
        ]
    )
    cursor.fetchall.side_effect = lambda: next(fetch_responses)

    out = plugin.discover(cursor, "MYDB", None)
    assert sql_log == [
        "SHOW SCHEMAS IN DATABASE MYDB LIMIT 10000",
        "SHOW SEQUENCES IN SCHEMA MYDB.PUBLIC LIMIT 10000",
    ]
    assert [str(f) for f in out] == ["MYDB.PUBLIC.SEQ1", "MYDB.PUBLIC.SEQ2"]


def test_discover_filters_by_schema() -> None:
    cursor = MagicMock()
    sql_log: list[str] = []
    cursor.execute.side_effect = lambda sql: sql_log.append(sql)
    cursor.fetchall.return_value = [
        {"name": "SEQ", "schema_name": "S", "database_name": "MYDB"}
    ]
    out = plugin.discover(cursor, "MYDB", ("S",))
    assert sql_log == ["SHOW SEQUENCES IN SCHEMA MYDB.S LIMIT 10000"]
    assert [str(f) for f in out] == ["MYDB.S.SEQ"]


def test_get_ddl_calls_get_ddl_function() -> None:
    cursor = MagicMock()
    cursor.fetchone.return_value = [
        "CREATE OR REPLACE SEQUENCE MYDB.PUBLIC.SEQ START = 1"
    ]
    fqn = FQN("MYDB", "PUBLIC", "SEQ")
    out = plugin.get_ddl(cursor, fqn)
    cursor.execute.assert_called_once_with(
        'SELECT GET_DDL(\'SEQUENCE\', \'"MYDB"."PUBLIC"."SEQ"\', TRUE)'
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
    # No raw=: every clause must be a structured kwarg.
    assert "raw=" not in out
    assert "database=database" in out
    assert "schema='PUBLIC'" in out
    assert "name='SEQ'" in out
    assert "start=1" in out


def test_macro_round_trip_renders_full_ddl() -> None:
    out = plugin.to_define_and_invocation(
        "CREATE OR REPLACE SEQUENCE MYDB.PUBLIC.SEQ START = 5 INCREMENT = 2 ORDER",
        comment="hi",
        use_macros=True,
        database="MYDB",
    )
    rendered = (
        jinja2.Environment()
        .from_string(plugin.macro_definition() + "\n" + out)
        .render(database="RUNTIME")
    )
    assert "DEFINE SEQUENCE RUNTIME.PUBLIC.SEQ" in rendered
    assert "START = 5" in rendered
    assert "INCREMENT = 2" in rendered
    assert " ORDER" in rendered
    assert "COMMENT='hi'" in rendered
    assert "{{ database }}" not in rendered


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


@pytest.mark.parametrize(
    "ddl,expected",
    [
        (
            "DEFINE SEQUENCE MYDB.PUBLIC.SEQ;",
            {"schema": "PUBLIC", "name": "SEQ"},
        ),
        (
            "DEFINE SEQUENCE MYDB.PUBLIC.SEQ START = 1 INCREMENT = 1;",
            {"schema": "PUBLIC", "name": "SEQ", "start": 1, "increment": 1},
        ),
        (
            "DEFINE SEQUENCE MYDB.PUBLIC.SEQ START WITH 100 INCREMENT BY 5 ORDER;",
            {
                "schema": "PUBLIC",
                "name": "SEQ",
                "start": 100,
                "increment": 5,
                "order": True,
            },
        ),
        (
            "DEFINE SEQUENCE MYDB.PUBLIC.SEQ WITH START 1 NOORDER;",
            {"schema": "PUBLIC", "name": "SEQ", "start": 1, "order": False},
        ),
        (
            "DEFINE SEQUENCE MYDB.PUBLIC.SEQ COMMENT='it''s fine';",
            {"schema": "PUBLIC", "name": "SEQ", "comment": "it's fine"},
        ),
        (
            'DEFINE SEQUENCE "my-db"."weird schema"."123seq" START = 5;',
            {"schema": "weird schema", "name": "123seq", "start": 5},
        ),
        (
            "DEFINE SEQUENCE {{ database }}.PUBLIC.SEQ START = 1;",
            {"schema": "PUBLIC", "name": "SEQ", "start": 1},
        ),
    ],
)
def test_parse_sequence_ddl_clauses(ddl: str, expected: dict) -> None:
    assert parse_sequence_ddl(ddl) == expected


@pytest.mark.parametrize(
    "ddl",
    [
        "DEFINE SEQUENCE MYDB.PUBLIC.SEQ HELLO=WORLD;",  # unknown clause
        "CREATE SEQUENCE MYDB.PUBLIC.SEQ;",  # CREATE not yet rewritten
        "DEFINE SEQUENCE",  # missing FQN
    ],
)
def test_parse_sequence_ddl_rejects_unsupported(ddl: str) -> None:
    with pytest.raises(SequenceParseError):
        parse_sequence_ddl(ddl)
