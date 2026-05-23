"""Tests for the stage DDL synthesizer."""

from __future__ import annotations

import pytest

from dcmexporter.objects._stage_ddl import (
    StageNotExportable,
    synthesize_stage_ddl,
)
from dcmexporter.types import FQN


def _row(parent: str, prop: str, value: str) -> dict:
    """A DESC STAGE row as DictCursor returns it."""
    return {
        "parent_property": parent,
        "property": prop,
        "property_value": value,
        "property_type": "String",
        "property_default": "",
    }


def test_minimal_external_stage_with_integration() -> None:
    fqn = FQN("MYDB", "PUBLIC", "MYSTAGE")
    rows = [
        _row("STAGE_LOCATION", "URL", '["s3://bucket/path/"]'),
        _row("STAGE_INTEGRATION", "STORAGE_INTEGRATION", "MY_INT"),
        _row("STAGE_CREDENTIALS", "AWS_ROLE", "arn:aws:iam::123:role/secret"),
    ]
    out = synthesize_stage_ddl(fqn, rows)
    assert out.startswith("CREATE OR REPLACE STAGE MYDB.PUBLIC.MYSTAGE")
    assert "URL = 's3://bucket/path/'" in out
    assert "STORAGE_INTEGRATION = MY_INT" in out
    # Credentials must NEVER end up in synthesized DDL.
    assert "AWS_ROLE" not in out
    assert "arn:aws:iam" not in out
    assert out.rstrip().endswith(";")


def test_stage_without_integration_raises() -> None:
    """Legacy stages with embedded credentials only — refuse to export."""
    fqn = FQN("MYDB", "PUBLIC", "OLDSTAGE")
    rows = [
        _row("STAGE_LOCATION", "URL", '["s3://bucket/path/"]'),
        _row("STAGE_CREDENTIALS", "AWS_KEY_ID", "AKIA..."),
    ]
    with pytest.raises(StageNotExportable):
        synthesize_stage_ddl(fqn, rows)


def test_stage_with_no_url_raises() -> None:
    fqn = FQN("MYDB", "PUBLIC", "S")
    rows = [_row("STAGE_INTEGRATION", "STORAGE_INTEGRATION", "INT")]
    with pytest.raises(StageNotExportable):
        synthesize_stage_ddl(fqn, rows)


def test_url_unwrapped_from_json_list() -> None:
    """DESC STAGE returns URL as a JSON-encoded list string: '["s3://..."]'."""
    fqn = FQN("MYDB", "PUBLIC", "S")
    rows = [
        _row("STAGE_LOCATION", "URL", '["s3://bucket/x/"]'),
        _row("STAGE_INTEGRATION", "STORAGE_INTEGRATION", "INT"),
    ]
    out = synthesize_stage_ddl(fqn, rows)
    assert "URL = 's3://bucket/x/'" in out
    assert '["s3' not in out
