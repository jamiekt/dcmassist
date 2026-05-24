"""Tests for the output-folder writer."""

from __future__ import annotations

from pathlib import Path

import pytest

from dcmassist.render import OutFolderError, prepare_out_folder, write_outputs


def test_write_outputs_creates_layout(tmp_path: Path) -> None:
    out = tmp_path / "out"
    write_outputs(
        out_folder=out,
        manifest="manifest_version: 2\n",
        makefile=".PHONY: plan\n",
        definitions={"table.sql": "DEFINE TABLE foo;\n"},
        macros={"table": "{% macro define_table() %}{% endmacro %}\n"},
    )
    assert (out / "manifest.yml").read_text() == "manifest_version: 2\n"
    assert (out / "Makefile").read_text() == ".PHONY: plan\n"
    assert (
        out / "sources" / "definitions" / "table.sql"
    ).read_text() == "DEFINE TABLE foo;\n"
    assert (out / "sources" / "macros" / "table.sql").exists()


def test_write_outputs_writes_chunked_definitions(tmp_path: Path) -> None:
    out = tmp_path / "out"
    write_outputs(
        out_folder=out,
        manifest="m",
        makefile="M",
        definitions={
            "table.sql": "block 1",
            "table2.sql": "block 2",
            "table3.sql": "block 3",
        },
        macros=None,
    )
    defs = out / "sources" / "definitions"
    assert (defs / "table.sql").read_text() == "block 1"
    assert (defs / "table2.sql").read_text() == "block 2"
    assert (defs / "table3.sql").read_text() == "block 3"


def test_write_outputs_skips_macros_when_none(tmp_path: Path) -> None:
    out = tmp_path / "out"
    write_outputs(
        out_folder=out,
        manifest="m",
        makefile="M",
        definitions={"table.sql": "x"},
        macros=None,
    )
    assert not (out / "sources" / "macros").exists()


def test_prepare_out_folder_refuses_existing_nonempty(tmp_path: Path) -> None:
    out = tmp_path / "out"
    out.mkdir()
    (out / "stale.txt").write_text("hello")
    with pytest.raises(OutFolderError):
        prepare_out_folder(out, force=False)


def test_prepare_out_folder_force_clears_existing(tmp_path: Path) -> None:
    out = tmp_path / "out"
    out.mkdir()
    (out / "stale.txt").write_text("hello")
    prepare_out_folder(out, force=True)
    assert out.exists()
    assert not (out / "stale.txt").exists()


def test_write_outputs_skips_empty_definition_files(tmp_path: Path) -> None:
    out = tmp_path / "out"
    write_outputs(
        out_folder=out,
        manifest="m",
        makefile="M",
        definitions={"table.sql": "x", "view.sql": ""},
        macros=None,
    )
    assert (out / "sources" / "definitions" / "table.sql").exists()
    assert not (out / "sources" / "definitions" / "view.sql").exists()
