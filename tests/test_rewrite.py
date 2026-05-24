"""Tests for the AST rewriter helpers."""

from __future__ import annotations

import jinja2

from dcmassist.rewrite import (
    JinjaExpr,
    create_to_define,
    inject_comment_if_missing,
    parameterise_database,
    parameterise_database_as_expr,
    render_macro_invocation,
)


def test_create_to_define_table() -> None:
    out = create_to_define("CREATE OR REPLACE TABLE FOO (X INT)")
    assert out.upper().startswith("DEFINE TABLE FOO")
    assert "CREATE" not in out.upper()


def test_create_to_define_secure_view() -> None:
    out = create_to_define("CREATE OR REPLACE SECURE VIEW V AS SELECT 1")
    assert out.upper().startswith("DEFINE SECURE VIEW V")


def test_create_to_define_idempotent() -> None:
    once = create_to_define("CREATE OR REPLACE TABLE FOO (X INT)")
    twice = create_to_define(once)
    assert once == twice


def test_inject_comment_when_missing() -> None:
    out = inject_comment_if_missing("DEFINE TABLE FOO (X INT)", comment="hello")
    assert "COMMENT='hello'" in out


def test_inject_comment_preserves_existing() -> None:
    src = "DEFINE TABLE FOO (X INT) COMMENT='keep me'"
    out = inject_comment_if_missing(src, comment="overwrite")
    assert "COMMENT='keep me'" in out
    assert "overwrite" not in out


def test_inject_comment_empty_string_when_missing() -> None:
    out = inject_comment_if_missing("DEFINE TABLE FOO (X INT)", comment="")
    assert "COMMENT=''" in out


def test_inject_comment_escapes_single_quotes() -> None:
    out = inject_comment_if_missing("DEFINE TABLE FOO (X INT)", comment="it's fine")
    assert "it''s fine" in out


def test_inject_comment_unsupported_type_is_noop() -> None:
    out = inject_comment_if_missing(
        "DEFINE TABLE FOO (X INT)",
        comment="hi",
        supports_comment=False,
    )
    assert "COMMENT" not in out


def test_parameterise_database_replaces_fqn() -> None:
    out = parameterise_database("DEFINE TABLE MYDB.PUBLIC.FOO (X INT)", database="MYDB")
    assert "{{ database }}.PUBLIC.FOO" in out
    assert "MYDB" not in out.replace("{{ database }}", "")


def test_parameterise_database_skips_substring_in_other_identifier() -> None:
    out = parameterise_database(
        "DEFINE TABLE MYDB.PUBLIC.MYDB_AUDIT (X INT)", database="MYDB"
    )
    assert "{{ database }}.PUBLIC.MYDB_AUDIT" in out


def test_parameterise_database_replaces_inside_body() -> None:
    out = parameterise_database(
        "DEFINE STAGE MYDB.PUBLIC.S URL='s3://bucket' STORAGE_INTEGRATION = MYDB_INT",
        database="MYDB",
    )
    assert "{{ database }}.PUBLIC.S" in out
    assert "MYDB_INT" in out


def test_parameterise_database_case_insensitive_match() -> None:
    out = parameterise_database("DEFINE TABLE mydb.public.foo (x INT)", database="MYDB")
    assert "{{ database }}" in out


def test_parameterise_database_no_change_when_absent() -> None:
    src = "DEFINE WAREHOUSE WH WAREHOUSE_SIZE='X-Small'"
    assert parameterise_database(src, database="MYDB") == src


def test_render_macro_invocation_quotes_strings() -> None:
    out = render_macro_invocation(
        "define_table",
        kwargs={
            "database": "{{ database }}",
            "schema": "PUBLIC",
            "name": "FOO",
            "columns": [{"name": "X", "type": "INT"}],
        },
    )
    assert out.startswith("{{ define_table(")
    assert "database='{{ database }}'" in out
    assert "schema='PUBLIC'" in out
    assert "name='FOO'" in out
    assert "columns=[{'name': 'X', 'type': 'INT'}]" in out
    assert out.endswith(") }}")


def test_render_macro_invocation_omits_none_values() -> None:
    out = render_macro_invocation(
        "define_table",
        kwargs={"name": "FOO", "comment": None},
    )
    assert "comment=" not in out
    assert "name='FOO'" in out


def test_render_macro_invocation_emits_jinja_expr_unquoted() -> None:
    out = render_macro_invocation(
        "define_table",
        kwargs={"database": JinjaExpr("database"), "name": "FOO"},
    )
    assert "database=database" in out
    assert "database='database'" not in out
    assert "name='FOO'" in out


def test_parameterise_database_as_expr_splits_around_db_references() -> None:
    expr = parameterise_database_as_expr(
        "DEFINE TABLE MYDB.PUBLIC.FOO (X INT)", database="MYDB"
    )
    assert isinstance(expr, JinjaExpr)
    assert "database" in expr.source
    assert "'DEFINE TABLE '" in expr.source
    assert "'.PUBLIC.FOO (X INT)'" in expr.source


def test_parameterise_database_as_expr_renders_through_jinja() -> None:
    """The whole point of the expression form: a single Jinja pass with the
    `database` variable bound must produce DDL with the runtime db name."""
    expr = parameterise_database_as_expr(
        "DEFINE TABLE MYDB.PUBLIC.FOO (X INT)", database="MYDB"
    )
    out = (
        jinja2.Environment()
        .from_string("{{ " + expr.source + " }}")
        .render(database="RUNTIME_DB")
    )
    assert out == "DEFINE TABLE RUNTIME_DB.PUBLIC.FOO (X INT)"


def test_parameterise_database_as_expr_no_match_returns_quoted_literal() -> None:
    expr = parameterise_database_as_expr(
        "DEFINE WAREHOUSE WH SIZE = 'X-Small'", database="MYDB"
    )
    out = (
        jinja2.Environment()
        .from_string("{{ " + expr.source + " }}")
        .render(database="RUNTIME_DB")
    )
    assert out == "DEFINE WAREHOUSE WH SIZE = 'X-Small'"


def test_parameterise_database_as_expr_escapes_single_quotes() -> None:
    expr = parameterise_database_as_expr(
        "DEFINE TABLE MYDB.PUBLIC.FOO COMMENT='it''s fine'", database="MYDB"
    )
    out = (
        jinja2.Environment()
        .from_string("{{ " + expr.source + " }}")
        .render(database="RUNTIME_DB")
    )
    assert out == "DEFINE TABLE RUNTIME_DB.PUBLIC.FOO COMMENT='it''s fine'"
