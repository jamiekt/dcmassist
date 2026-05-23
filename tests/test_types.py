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
    assert V1_TYPES == (
        "Database",
        "Schema",
        "Table",
        "View",
        "Sequence",
        "Stage",
        "File format",
        "Tag",
        "Warehouse",
    )


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
