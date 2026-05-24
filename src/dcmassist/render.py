"""Write generated artefacts into the output folder."""

from __future__ import annotations

import shutil
from pathlib import Path


class OutFolderError(RuntimeError):
    """Raised when --out-folder is unsafe to write to."""


def _is_nonempty_dir(path: Path) -> bool:
    return path.exists() and path.is_dir() and any(path.iterdir())


def prepare_out_folder(out_folder: Path, *, force: bool) -> None:
    """Make `out_folder` ready for writing.

    Refuses if non-empty and `force=False`. With `force=True`, clears existing
    contents. Always ensures the folder exists at the end. Called up-front so
    the orchestrator can open the log file inside it before doing any work.
    """
    if _is_nonempty_dir(out_folder) and not force:
        raise OutFolderError(
            f"Output folder {out_folder} exists and is non-empty; pass --force to overwrite"
        )
    if _is_nonempty_dir(out_folder) and force:
        for child in out_folder.iterdir():
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
    out_folder.mkdir(parents=True, exist_ok=True)


def write_outputs(
    *,
    out_folder: Path,
    manifest: str,
    makefile: str,
    definitions: dict[str, str],
    macros: dict[str, str] | None,
) -> None:
    """Write all generated files into out_folder.

    `definitions` is keyed by full filename (``"table.sql"``, ``"table2.sql"``,
    …); the orchestrator decides chunk names. Macros are still keyed by slug
    because there's exactly one macro file per type.

    The folder must already exist — call `prepare_out_folder` first.
    """
    out_folder.mkdir(parents=True, exist_ok=True)
    (out_folder / "manifest.yml").write_text(manifest)
    (out_folder / "Makefile").write_text(makefile)

    definitions_dir = out_folder / "sources" / "definitions"
    definitions_dir.mkdir(parents=True, exist_ok=True)
    for filename, body in definitions.items():
        if not body:
            continue
        (definitions_dir / filename).write_text(body)

    if macros:
        macros_dir = out_folder / "sources" / "macros"
        macros_dir.mkdir(parents=True, exist_ok=True)
        for slug, body in macros.items():
            (macros_dir / f"{slug}.sql").write_text(body)
