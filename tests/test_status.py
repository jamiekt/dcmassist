"""Tests for the StatusDashboard helper."""

from __future__ import annotations

import io

from dcmexporter.status import StatusDashboard


class _TtyStream(io.StringIO):
    def isatty(self) -> bool:  # type: ignore[override]
        return True


def test_silent_when_not_tty(monkeypatch) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("DCMEXPORTER_NO_STATUS", raising=False)
    stream = io.StringIO()
    with StatusDashboard(stream=stream) as dash:
        dash.set_database("MYDB")
        dash.set_now("connecting...")
        dash.set_schema("discovering Tables in MYDB.PUBLIC")
        dash.set_counts(exported=1, errors=0, skipped=0)
    assert stream.getvalue() == ""


def test_disabled_by_no_status_env(monkeypatch) -> None:
    monkeypatch.setenv("DCMEXPORTER_NO_STATUS", "1")
    stream = _TtyStream()
    with StatusDashboard(stream=stream) as dash:
        dash.set_database("MYDB")
        dash.set_now("nope")
    assert stream.getvalue() == ""


def test_disabled_by_no_color_env(monkeypatch) -> None:
    """NO_COLOR is the standard opt-out for ANSI; the dashboard depends on
    colour to be readable, so we treat NO_COLOR as 'no dashboard' rather than
    rendering a degraded plain panel."""
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.delenv("DCMEXPORTER_NO_STATUS", raising=False)
    stream = _TtyStream()
    with StatusDashboard(stream=stream) as dash:
        dash.set_database("MYDB")
        dash.set_now("nope")
    assert stream.getvalue() == ""


def test_renders_panel_content_when_tty(monkeypatch) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("DCMEXPORTER_NO_STATUS", raising=False)
    stream = _TtyStream()
    with StatusDashboard(stream=stream) as dash:
        dash.set_database("MYDB")
        dash.set_now("Table MYDB.PUBLIC.ORDERS 12/847")
        dash.set_schema("discovering Views in MYDB.PUBLIC")
        dash.set_counts(exported=531, errors=0, skipped=2)
    out = stream.getvalue()
    assert "MYDB" in out
    assert "ORDERS" in out
    assert "discovering Views" in out
    assert "exported=531" in out
    assert "errors=0" in out
    assert "skipped=2" in out


def test_log_writes_above_panel(monkeypatch) -> None:
    """Errors and warnings need to scroll above the live panel rather than
    overwrite it. Verify .log() output appears in the stream."""
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("DCMEXPORTER_NO_STATUS", raising=False)
    stream = _TtyStream()
    with StatusDashboard(stream=stream) as dash:
        dash.set_database("MYDB")
        dash.log("[dcmexporter] discover failed for Tag: <reason>")
    assert "discover failed for Tag" in stream.getvalue()


def test_setters_safe_before_enter() -> None:
    """Calling setters on an unentered dashboard must not raise. Useful so
    callers can construct the dashboard and update fields conditionally."""
    dash = StatusDashboard(stream=io.StringIO())
    dash.set_database("MYDB")
    dash.set_now("hello")
    dash.set_schema("schema")
    dash.set_counts(exported=0, errors=0, skipped=0)
    dash.log("a message")
