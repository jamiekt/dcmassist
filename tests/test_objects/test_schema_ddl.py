"""Tests for the Schema DDL synthesizer."""

from __future__ import annotations

import pytest

from dcmexporter.objects._schema_ddl import (
    SchemaNotExportable,
    synthesize_schema_ddl,
)
from dcmexporter.types import FQN


def _row(**overrides: object) -> dict:
    """A SHOW SCHEMAS row as DictCursor returns it."""
    base: dict = {
        "name": "PUBLIC",
        "database_name": "MYDB",
        "comment": "",
        "options": "",
    }
    base.update(overrides)
    return base


def test_minimal_schema() -> None:
    fqn = FQN("MYDB", "PUBLIC", "PUBLIC")
    out = synthesize_schema_ddl(fqn, _row())
    assert out.startswith("CREATE OR REPLACE SCHEMA MYDB.PUBLIC")
    assert out.rstrip().endswith(";")


def test_schema_with_comment_emits_comment_clause() -> None:
    fqn = FQN("MYDB", "PUBLIC", "PUBLIC")
    out = synthesize_schema_ddl(fqn, _row(comment="hello"))
    assert "COMMENT='hello'" in out


def test_schema_comment_escapes_single_quotes() -> None:
    fqn = FQN("MYDB", "PUBLIC", "PUBLIC")
    out = synthesize_schema_ddl(fqn, _row(comment="it's fine"))
    assert "COMMENT='it''s fine'" in out


def test_schema_blank_comment_omits_clause() -> None:
    fqn = FQN("MYDB", "PUBLIC", "PUBLIC")
    out = synthesize_schema_ddl(fqn, _row(comment=""))
    assert "COMMENT" not in out


def test_schema_missing_name_raises() -> None:
    fqn = FQN("MYDB", "PUBLIC", "PUBLIC")
    with pytest.raises(SchemaNotExportable):
        synthesize_schema_ddl(fqn, _row(name=""))


def test_schema_uses_fqn_for_ddl() -> None:
    """The CREATE statement uses the FQN (db.schema), not the SHOW row's name."""
    fqn = FQN("MYDB", "ANALYTICS", "ANALYTICS")
    out = synthesize_schema_ddl(fqn, _row(name="ANALYTICS", database_name="MYDB"))
    assert "CREATE OR REPLACE SCHEMA MYDB.ANALYTICS" in out


def test_transient_schema_emitted_when_options_indicate() -> None:
    """SHOW SCHEMAS encodes TRANSIENT in `options` (e.g. 'TRANSIENT')."""
    fqn = FQN("MYDB", "T", "T")
    out = synthesize_schema_ddl(fqn, _row(options="TRANSIENT"))
    assert out.startswith("CREATE OR REPLACE TRANSIENT SCHEMA MYDB.T")


def test_managed_access_schema_emitted_when_options_indicate() -> None:
    fqn = FQN("MYDB", "M", "M")
    out = synthesize_schema_ddl(fqn, _row(options="MANAGED ACCESS"))
    assert "WITH MANAGED ACCESS" in out


def test_combined_options() -> None:
    fqn = FQN("MYDB", "M", "M")
    out = synthesize_schema_ddl(fqn, _row(options="TRANSIENT, MANAGED ACCESS"))
    assert out.startswith("CREATE OR REPLACE TRANSIENT SCHEMA MYDB.M")
    assert "WITH MANAGED ACCESS" in out
