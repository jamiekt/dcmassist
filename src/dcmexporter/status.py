"""Single self-updating status line on stderr.

Long export runs (80K+ tables) emit very little until they finish, which makes
the CLI feel hung. This module writes one self-overwriting line via `\\r` when
stderr is a TTY, and stays silent otherwise so logs/CI output don't fill with
control characters. Errors and the final summary still print as normal lines
above the status line.
"""

from __future__ import annotations

import os
import shutil
import sys
from typing import IO


class StatusLine:
    def __init__(self, stream: IO[str] | None = None) -> None:
        self._stream: IO[str] = stream if stream is not None else sys.stderr
        self._enabled = self._is_tty(self._stream) and not _disabled_by_env()
        self._last_width = 0

    @staticmethod
    def _is_tty(stream: IO[str]) -> bool:
        isatty = getattr(stream, "isatty", None)
        return bool(isatty and isatty())

    def update(self, message: str) -> None:
        if not self._enabled:
            return
        width = shutil.get_terminal_size((80, 20)).columns
        text = message[: max(0, width - 1)]
        pad = max(0, self._last_width - len(text))
        self._stream.write("\r" + text + (" " * pad) + "\r" + text)
        self._stream.flush()
        self._last_width = len(text)

    def clear(self) -> None:
        if not self._enabled or self._last_width == 0:
            return
        self._stream.write("\r" + (" " * self._last_width) + "\r")
        self._stream.flush()
        self._last_width = 0


def _disabled_by_env() -> bool:
    if os.environ.get("NO_COLOR"):
        return True
    return os.environ.get("DCMEXPORTER_NO_STATUS") == "1"
