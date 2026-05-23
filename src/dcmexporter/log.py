"""Per-run log file written into the output folder.

The orchestrator emits a terse status line and final summary on stderr; the
detailed timeline of every discover, get_ddl, and per-object error goes here.
This is what users tail when something goes wrong: stderr tells them
*something* failed, and the log tells them *which* objects and *why*.

Each run truncates the file so the log reflects the latest run only — past
runs are in git history (the export output) anyway, and an ever-growing log
is a footgun on small disks / large databases.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import IO


class RunLog:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._stream: IO[str] | None = path.open("w", encoding="utf-8")

    def info(self, message: str) -> None:
        self._write("INFO", message)

    def warn(self, message: str) -> None:
        self._write("WARN", message)

    def error(self, message: str) -> None:
        self._write("ERROR", message)

    def close(self) -> None:
        if self._stream is not None:
            self._stream.close()
            self._stream = None

    @property
    def path(self) -> Path:
        return self._path

    def _write(self, level: str, message: str) -> None:
        if self._stream is None:
            return
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        self._stream.write(f"{ts} {level} {message}\n")
        self._stream.flush()
