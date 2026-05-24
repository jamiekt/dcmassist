"""Rich-backed live status dashboard for long export runs.

Long export runs (80K+ tables) emit very little until they finish, which makes
the CLI feel hung. This module renders a self-refreshing panel via
``rich.live.Live`` when stderr is a TTY and stays silent otherwise so logs/CI
output don't fill with control characters. Errors and the final summary still
print as normal lines (use ``.log()`` to write above the panel).
"""

from __future__ import annotations

import os
import sys
from types import TracebackType
from typing import IO

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text


class StatusDashboard:
    """Live panel dashboard. Use as a context manager.

    All setters are safe to call before ``__enter__`` and after ``__exit__``;
    they update the held state and either re-render the live panel or do
    nothing if the dashboard is disabled or not currently running.
    """

    def __init__(self, stream: IO[str] | None = None) -> None:
        self._stream: IO[str] = stream if stream is not None else sys.stderr
        self._enabled = self._is_tty(self._stream) and not _disabled_by_env()
        self._database = ""
        self._now = ""
        self._schema = ""
        self._exported = 0
        self._errors = 0
        self._skipped = 0
        self._console: Console | None = None
        self._live: Live | None = None

    # --- context manager ---------------------------------------------------

    def __enter__(self) -> "StatusDashboard":
        if not self._enabled:
            return self
        self._console = Console(
            file=self._stream,
            force_terminal=True,
            highlight=False,
        )
        self._live = Live(
            self._render(),
            console=self._console,
            refresh_per_second=8,
            transient=True,
        )
        self._live.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._live is not None:
            self._live.stop()
            self._live = None
        self._console = None

    # --- state setters -----------------------------------------------------

    def set_database(self, database: str) -> None:
        self._database = database
        self._refresh()

    def set_now(self, message: str) -> None:
        self._now = message
        self._refresh()

    def set_schema(self, message: str) -> None:
        self._schema = message
        self._refresh()

    def set_counts(self, *, exported: int, errors: int, skipped: int) -> None:
        self._exported = exported
        self._errors = errors
        self._skipped = skipped
        self._refresh()

    def log(self, message: str) -> None:
        """Write a one-shot line that scrolls above the live panel.

        Use for warnings/errors that would otherwise be overwritten by the
        next refresh. When the dashboard is disabled (non-TTY, NO_COLOR, or
        DCMASSIST_NO_STATUS=1) the message still reaches stderr-equivalent
        output so CI/piped runs don't silently lose warnings.
        """
        if self._console is not None:
            self._console.print(message)
            return
        print(message, file=self._stream)

    # --- internals ---------------------------------------------------------

    def _refresh(self) -> None:
        if self._live is None:
            return
        self._live.update(self._render())

    def _render(self) -> Panel:
        body = Table.grid(padding=(0, 2))
        body.add_column(style="dim", no_wrap=True)
        body.add_column(overflow="ellipsis")
        body.add_row("database:", Text(self._database))
        body.add_row("now:", Text(self._now, style="cyan"))
        body.add_row("schema:", Text(self._schema, style="magenta"))

        counts = Text()
        counts.append(f"exported={self._exported}", style="green")
        counts.append("  ")
        errors_style = "red" if self._errors else "dim"
        counts.append(f"errors={self._errors}", style=errors_style)
        counts.append("  ")
        skipped_style = "yellow" if self._skipped else "dim"
        counts.append(f"skipped={self._skipped}", style=skipped_style)

        return Panel(
            Group(body, Text(""), counts),
            title="dcmassist",
            title_align="left",
            border_style="dim",
        )

    @staticmethod
    def _is_tty(stream: IO[str]) -> bool:
        isatty = getattr(stream, "isatty", None)
        return bool(isatty and isatty())


def _disabled_by_env() -> bool:
    if os.environ.get("NO_COLOR"):
        return True
    return os.environ.get("DCMASSIST_NO_STATUS") == "1"
