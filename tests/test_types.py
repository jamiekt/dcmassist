"""Tests for SUPPORTED_TYPES canonical list and FQN dataclass."""

from __future__ import annotations

from dcmexporter.types import (
    DCM_TYPES,
    UNIMPLEMENTED_TYPES,
    V1_TYPES,
    FQN,
    normalise_type,
)


def test_dcm_types_includes_v1_and_unimplemented() -> None:
    assert set(V1_TYPES) | set(UNIMPLEMENTED_TYPES) == set(DCM_TYPES)


def test_v1_and_unimplemented_are_disjoint() -> None:
    assert set(V1_TYPES).isdisjoint(set(UNIMPLEMENTED_TYPES))


def test_v1_types_match_spec() -> None:
    """Database is intentionally excluded — DCM rejects DEFINE DATABASE for
    the project's parent database. See UNIMPLEMENTED_TYPES."""
    assert V1_TYPES == (
        "Schema",
        "Table",
        "View",
        "Sequence",
        "Stage",
        "File format",
        "Tag",
    )


def test_database_is_unimplemented() -> None:
    """Keeping it in DCM_TYPES means --include Database / --exclude Database
    still validate, but no DEFINE block is ever emitted."""
    assert "Database" in UNIMPLEMENTED_TYPES
    assert "Database" not in V1_TYPES


def test_normalise_type_case_insensitive() -> None:
    assert normalise_type("table") == "Table"
    assert normalise_type("FILE FORMAT") == "File format"
    assert normalise_type("File format") == "File format"


def test_normalise_type_unknown_raises() -> None:
    import pytest

    with pytest.raises(ValueError, match="Banana"):
        normalise_type("Banana")


def test_fqn_str_dotted() -> None:
    fqn = FQN(database="MYDB", schema="PUBLIC", name="FOO")
    assert str(fqn) == "MYDB.PUBLIC.FOO"


def test_fqn_str_no_schema() -> None:
    fqn = FQN(database="MYDB", schema=None, name="MYDB")
    assert str(fqn) == "MYDB"


def test_fqn_quoted_dotted() -> None:
    """Quoted form is what Snowflake needs for identifiers like '15MIN_X' or
    mixed case — bare-uppercase resolution silently fails on those."""
    fqn = FQN(database="MYDB", schema="PUBLIC", name="15MIN_X")
    assert fqn.quoted == '"MYDB"."PUBLIC"."15MIN_X"'


def test_fqn_quoted_no_schema() -> None:
    fqn = FQN(database="MYDB", schema=None, name="MYDB")
    assert fqn.quoted == '"MYDB"'


def test_fqn_quoted_escapes_double_quotes() -> None:
    """Snowflake string-escape for `"` inside a quoted identifier is `""`."""
    fqn = FQN(database="MYDB", schema="PUBLIC", name='WEIRD"NAME')
    assert fqn.quoted == '"MYDB"."PUBLIC"."WEIRD""NAME"'
