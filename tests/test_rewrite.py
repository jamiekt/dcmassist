"""Tests for the AST rewriter helpers."""

from __future__ import annotations

from dcmexporter.rewrite import create_to_define, inject_comment_if_missing


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
