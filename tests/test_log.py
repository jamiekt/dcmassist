"""Tests for the file logger."""

from __future__ import annotations

from pathlib import Path

from dcmexporter.log import RunLog


def test_run_log_writes_lines_with_levels(tmp_path: Path) -> None:
    path = tmp_path / "log.txt"
    log = RunLog(path)
    log.info("hello")
    log.warn("watch out")
    log.error("oops")
    log.close()
    text = path.read_text()
    assert " INFO " in text
    assert " WARN " in text
    assert " ERROR " in text
    assert "hello" in text
    assert "watch out" in text
    assert "oops" in text


def test_run_log_truncates_each_run(tmp_path: Path) -> None:
    """Each export should start a clean log; otherwise the file grows forever."""
    path = tmp_path / "log.txt"
    path.write_text("stale content from a previous run\n")
    log = RunLog(path)
    log.info("fresh")
    log.close()
    assert "stale content" not in path.read_text()
    assert "fresh" in path.read_text()


def test_run_log_close_is_idempotent(tmp_path: Path) -> None:
    log = RunLog(tmp_path / "log.txt")
    log.close()
    log.close()  # second call must not raise
