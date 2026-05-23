"""Tests for the Database DDL synthesizer."""

from __future__ import annotations

import pytest

from dcmexporter.objects._database_ddl import (
    DatabaseNotExportable,
    synthesize_database_ddl,
)
from dcmexporter.types import FQN


def _row(**overrides: object) -> dict:
    """A SHOW DATABASES row as DictCursor returns it."""
    base: dict = {
        "name": "MYDB",
        "comment": "",
        "options": "",
        "kind": "STANDARD",
    }
    base.update(overrides)
    return base


def test_minimal_database() -> None:
    fqn = FQN("MYDB", None, "MYDB")
    out = synthesize_database_ddl(fqn, _row())
    assert out.startswith("CREATE OR REPLACE DATABASE MYDB")
    assert out.rstrip().endswith(";")


def test_database_with_comment_emits_comment_clause() -> None:
    fqn = FQN("MYDB", None, "MYDB")
    out = synthesize_database_ddl(fqn, _row(comment="hello world"))
    assert "COMMENT='hello world'" in out


def test_database_comment_escapes_single_quotes() -> None:
    fqn = FQN("MYDB", None, "MYDB")
    out = synthesize_database_ddl(fqn, _row(comment="it's fine"))
    assert "COMMENT='it''s fine'" in out


def test_database_blank_comment_omits_clause() -> None:
    fqn = FQN("MYDB", None, "MYDB")
    out = synthesize_database_ddl(fqn, _row(comment=""))
    assert "COMMENT" not in out


def test_database_missing_name_raises() -> None:
    fqn = FQN("MYDB", None, "MYDB")
    with pytest.raises(DatabaseNotExportable):
        synthesize_database_ddl(fqn, _row(name=""))


def test_database_uses_fqn_name_for_ddl() -> None:
    """The CREATE statement uses the FQN's name, not the SHOW row's name.

    They should match, but the FQN is authoritative for what we write to disk.
    """
    fqn = FQN("MYDB", None, "MYDB")
    out = synthesize_database_ddl(fqn, _row(name="MYDB"))
    assert "CREATE OR REPLACE DATABASE MYDB" in out
