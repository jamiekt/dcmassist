"""Tests for the output-folder writer."""

from __future__ import annotations

from pathlib import Path

import pytest

from dcmexporter.render import OutFolderError, write_outputs


def test_write_outputs_creates_layout(tmp_path: Path) -> None:
    out = tmp_path / "out"
    write_outputs(
        out_folder=out,
        manifest="manifest_version: 2\n",
        makefile=".PHONY: plan\n",
        definitions={"table": "DEFINE TABLE foo;\n"},
        macros={"table": "{% macro define_table() %}{% endmacro %}\n"},
        force=False,
    )
    assert (out / "manifest.yml").read_text() == "manifest_version: 2\n"
    assert (out / "Makefile").read_text() == ".PHONY: plan\n"
    assert (
        out / "sources" / "definitions" / "table.sql"
    ).read_text() == "DEFINE TABLE foo;\n"
    assert (out / "sources" / "macros" / "table.sql").exists()


def test_write_outputs_skips_macros_when_none(tmp_path: Path) -> None:
    out = tmp_path / "out"
    write_outputs(
        out_folder=out,
        manifest="m",
        makefile="M",
        definitions={"table": "x"},
        macros=None,
        force=False,
    )
    assert not (out / "sources" / "macros").exists()


def test_write_outputs_refuses_existing_nonempty(tmp_path: Path) -> None:
    out = tmp_path / "out"
    out.mkdir()
    (out / "stale.txt").write_text("hello")
    with pytest.raises(OutFolderError):
        write_outputs(
            out_folder=out,
            manifest="m",
            makefile="M",
            definitions={"table": "x"},
            macros=None,
            force=False,
        )


def test_write_outputs_force_overwrites(tmp_path: Path) -> None:
    out = tmp_path / "out"
    out.mkdir()
    (out / "stale.txt").write_text("hello")
    write_outputs(
        out_folder=out,
        manifest="m",
        makefile="M",
        definitions={"table": "x"},
        macros=None,
        force=True,
    )
    assert (out / "manifest.yml").read_text() == "m"
    assert not (out / "stale.txt").exists()


def test_write_outputs_skips_empty_definition_files(tmp_path: Path) -> None:
    out = tmp_path / "out"
    write_outputs(
        out_folder=out,
        manifest="m",
        makefile="M",
        definitions={"table": "x", "view": ""},
        macros=None,
        force=False,
    )
    assert (out / "sources" / "definitions" / "table.sql").exists()
    assert not (out / "sources" / "definitions" / "view.sql").exists()
