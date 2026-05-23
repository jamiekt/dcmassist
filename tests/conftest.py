"""Shared pytest fixtures for dcmexporter tests."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def mock_cursor() -> MagicMock:
    """A MagicMock standing in for a snowflake-connector cursor."""
    return MagicMock()


@pytest.fixture
def tmp_out_folder(tmp_path: Path) -> Path:
    """A fresh empty directory to use as --out-folder."""
    out = tmp_path / "out"
    out.mkdir()
    return out
