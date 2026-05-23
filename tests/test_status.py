"""Tests for the StatusLine helper."""

from __future__ import annotations

import io

from dcmexporter.status import StatusLine


class _TtyStream(io.StringIO):
    def isatty(self) -> bool:  # type: ignore[override]
        return True


def test_silent_when_not_tty() -> None:
    stream = io.StringIO()
    sl = StatusLine(stream=stream)
    sl.update("hello")
    sl.clear()
    assert stream.getvalue() == ""


def test_writes_carriage_return_and_clears(monkeypatch) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("DCMEXPORTER_NO_STATUS", raising=False)
    stream = _TtyStream()
    sl = StatusLine(stream=stream)
    sl.update("step one")
    sl.update("step two")
    sl.clear()
    out = stream.getvalue()
    assert out.startswith("\r")
    assert "step one" in out
    assert "step two" in out
    # After clear, the line should be blanked back to column 0.
    assert out.endswith("\r")


def test_disabled_by_env(monkeypatch) -> None:
    monkeypatch.setenv("DCMEXPORTER_NO_STATUS", "1")
    stream = _TtyStream()
    sl = StatusLine(stream=stream)
    sl.update("nope")
    assert stream.getvalue() == ""
