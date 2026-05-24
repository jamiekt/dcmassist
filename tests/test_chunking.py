"""Tests for the per-type DDL chunking helper."""

from __future__ import annotations

import pytest

from dcmassist.chunking import (
    DEFAULT_OBJECTS_PER_FILE,
    OBJECTS_PER_FILE_ENV,
    chunk_blocks,
    resolve_objects_per_file,
)


def test_default_constant_is_100() -> None:
    assert DEFAULT_OBJECTS_PER_FILE == 100


def test_env_var_name_is_dcmassist() -> None:
    assert OBJECTS_PER_FILE_ENV == "DCMASSIST_EXPORT_OBJECTS_PER_FILE"


def test_resolve_default_when_unset(monkeypatch) -> None:
    monkeypatch.delenv(OBJECTS_PER_FILE_ENV, raising=False)
    assert resolve_objects_per_file() == 100


def test_resolve_reads_env(monkeypatch) -> None:
    monkeypatch.setenv(OBJECTS_PER_FILE_ENV, "50")
    assert resolve_objects_per_file() == 50


def test_resolve_rejects_non_integer(monkeypatch) -> None:
    monkeypatch.setenv(OBJECTS_PER_FILE_ENV, "abc")
    with pytest.raises(ValueError, match=OBJECTS_PER_FILE_ENV):
        resolve_objects_per_file()


def test_resolve_rejects_zero(monkeypatch) -> None:
    """Zero would be a divide-by-zero / infinite-files trap. Reject explicitly."""
    monkeypatch.setenv(OBJECTS_PER_FILE_ENV, "0")
    with pytest.raises(ValueError, match=OBJECTS_PER_FILE_ENV):
        resolve_objects_per_file()


def test_resolve_rejects_negative(monkeypatch) -> None:
    monkeypatch.setenv(OBJECTS_PER_FILE_ENV, "-5")
    with pytest.raises(ValueError, match=OBJECTS_PER_FILE_ENV):
        resolve_objects_per_file()


def test_chunk_empty_returns_empty() -> None:
    assert chunk_blocks([], slug="table", size=100) == []


def test_chunk_single_file_when_under_limit() -> None:
    blocks = ["a", "b", "c"]
    result = chunk_blocks(blocks, slug="table", size=100)
    assert result == [("table.sql", ["a", "b", "c"])]


def test_chunk_single_file_when_exactly_at_limit() -> None:
    blocks = ["a", "b", "c"]
    result = chunk_blocks(blocks, slug="table", size=3)
    assert result == [("table.sql", ["a", "b", "c"])]


def test_chunk_two_files_when_one_over() -> None:
    blocks = ["a", "b", "c", "d"]
    result = chunk_blocks(blocks, slug="table", size=3)
    assert result == [
        ("table.sql", ["a", "b", "c"]),
        ("table2.sql", ["d"]),
    ]


def test_chunk_many_files_uses_2_3_4_naming() -> None:
    blocks = [str(i) for i in range(7)]
    result = chunk_blocks(blocks, slug="view", size=2)
    assert result == [
        ("view.sql", ["0", "1"]),
        ("view2.sql", ["2", "3"]),
        ("view3.sql", ["4", "5"]),
        ("view4.sql", ["6"]),
    ]


def test_chunk_uses_provided_slug() -> None:
    blocks = ["x"]
    result = chunk_blocks(blocks, slug="file_format", size=100)
    assert result == [("file_format.sql", ["x"])]
