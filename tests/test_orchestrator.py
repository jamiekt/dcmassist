"""End-to-end orchestrator test against a fully mocked cursor."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from dcmexporter.config import Config
from dcmexporter.orchestrator import export


def _cfg(out_folder: Path, *, use_macros: bool = True) -> Config:
    return Config(
        database="MYDB",
        schemas=(),
        connection=None,
        targets=("staging",),
        default_target="staging",
        templating_defaults=(),
        configurations=("STAGING",),
        templating_configuration_keys=("environment",),
        includes=("Table",),  # narrow surface for golden test
        excludes=(),
        comment="exported by dcmexporter",
        use_macros=use_macros,
        out_folder=out_folder,
        force=True,
    )


def test_export_writes_full_layout(tmp_path: Path) -> None:
    out = tmp_path / "out"

    fake_cursor = MagicMock()
    fake_conn = MagicMock()
    fake_conn.account = "AB12345"
    fake_conn.cursor.return_value = fake_cursor

    def execute_side_effect(sql, *args, **kwargs):
        fake_cursor._last_sql = sql

    def fetchall_side_effect():
        if "SHOW SCHEMAS" in fake_cursor._last_sql:
            return [
                {"name": "PUBLIC", "database_name": "MYDB"},
                {"name": "ANALYTICS", "database_name": "MYDB"},
            ]
        if "SHOW TABLES" in fake_cursor._last_sql:
            if "ANALYTICS" in fake_cursor._last_sql:
                return [
                    {"name": "T2", "schema_name": "ANALYTICS"},
                    {"name": "T3", "schema_name": "ANALYTICS"},
                ]
            return [{"name": "T1", "schema_name": "PUBLIC"}]
        return []

    def fetchone_side_effect():
        if "GET_DDL" in fake_cursor._last_sql:
            return ["CREATE OR REPLACE TABLE MYDB.PUBLIC.T1 (X INT)"]
        return None

    fake_cursor.execute.side_effect = execute_side_effect
    fake_cursor.fetchall.side_effect = fetchall_side_effect
    fake_cursor.fetchone.side_effect = fetchone_side_effect

    with patch("dcmexporter.orchestrator.open_connection") as oc:
        oc.return_value = fake_conn
        code = export(_cfg(out))

    assert code == 0
    assert (out / "manifest.yml").exists()
    assert (out / "Makefile").exists()
    assert (out / "sources" / "definitions" / "table.sql").exists()
    assert (out / "sources" / "macros" / "table.sql").exists()

    log_text = (out / "dcmexporter.log").read_text()
    assert "ANALYTICS: 2" in log_text
    assert "PUBLIC: 1" in log_text

    table_sql = (out / "sources" / "definitions" / "table.sql").read_text()
    assert "{{ define_table(" in table_sql
    assert "{{ database }}.PUBLIC.T1" in table_sql

    manifest = (out / "manifest.yml").read_text()
    assert "STAGING:" in manifest
    assert "database: MYDB" in manifest
    assert "templating_config: staging" in manifest


def test_export_per_object_get_ddl_failure_continues(tmp_path: Path, capsys) -> None:
    out = tmp_path / "out"
    fake_cursor = MagicMock()
    fake_conn = MagicMock()
    fake_conn.account = "AB12345"
    fake_conn.cursor.return_value = fake_cursor

    def execute_side_effect(sql, *args, **kwargs):
        fake_cursor._last_sql = sql
        if "GET_DDL" in sql and "T_BAD" in sql:
            raise RuntimeError("permission denied")

    def fetchall_side_effect():
        if "SHOW SCHEMAS" in fake_cursor._last_sql:
            return [{"name": "PUBLIC", "database_name": "MYDB"}]
        if "SHOW TABLES" in fake_cursor._last_sql:
            return [
                {"name": "T_OK", "schema_name": "PUBLIC"},
                {"name": "T_BAD", "schema_name": "PUBLIC"},
            ]
        return []

    def fetchone_side_effect():
        if "GET_DDL" in fake_cursor._last_sql:
            return ["CREATE OR REPLACE TABLE MYDB.PUBLIC.T_OK (X INT)"]
        return None

    fake_cursor.execute.side_effect = execute_side_effect
    fake_cursor.fetchall.side_effect = fetchall_side_effect
    fake_cursor.fetchone.side_effect = fetchone_side_effect

    with patch("dcmexporter.orchestrator.open_connection") as oc:
        oc.return_value = fake_conn
        code = export(_cfg(out))

    assert code == 0
    log_text = (out / "dcmexporter.log").read_text()
    assert "T_BAD" in log_text
    assert "permission denied" in log_text
    body = (out / "sources" / "definitions" / "table.sql").read_text()
    assert "T_OK" in body
    assert "T_BAD" not in body


def test_export_no_macros_folder_when_macros_disabled(tmp_path: Path) -> None:
    """With use_macros=False the sources/macros folder must not exist."""
    out = tmp_path / "out"
    fake_cursor = MagicMock()
    fake_conn = MagicMock()
    fake_conn.account = "AB12345"
    fake_conn.cursor.return_value = fake_cursor

    def execute_side_effect(sql, *args, **kwargs):
        fake_cursor._last_sql = sql

    def fetchall_side_effect():
        if "SHOW SCHEMAS" in fake_cursor._last_sql:
            return [{"name": "PUBLIC", "database_name": "MYDB"}]
        if "SHOW TABLES" in fake_cursor._last_sql:
            return [{"name": "T1", "schema_name": "PUBLIC"}]
        return []

    def fetchone_side_effect():
        if "GET_DDL" in fake_cursor._last_sql:
            return ["CREATE OR REPLACE TABLE MYDB.PUBLIC.T1 (X INT)"]
        return None

    fake_cursor.execute.side_effect = execute_side_effect
    fake_cursor.fetchall.side_effect = fetchall_side_effect
    fake_cursor.fetchone.side_effect = fetchone_side_effect

    with patch("dcmexporter.orchestrator.open_connection") as oc:
        oc.return_value = fake_conn
        code = export(_cfg(out, use_macros=False))

    assert code == 0
    assert (out / "sources" / "definitions" / "table.sql").exists()
    assert not (out / "sources" / "macros").exists()


def test_export_no_objects_returns_4_when_errors(tmp_path: Path) -> None:
    out = tmp_path / "out"
    fake_cursor = MagicMock()
    fake_conn = MagicMock()
    fake_conn.account = "AB12345"
    fake_conn.cursor.return_value = fake_cursor

    def execute_side_effect(sql, *args, **kwargs):
        fake_cursor._last_sql = sql
        if "GET_DDL" in sql:
            raise RuntimeError("denied")

    def fetchall_side_effect():
        if "SHOW SCHEMAS" in fake_cursor._last_sql:
            return [{"name": "PUBLIC", "database_name": "MYDB"}]
        if "SHOW TABLES" in fake_cursor._last_sql:
            return [{"name": "T", "schema_name": "PUBLIC"}]
        return []

    fake_cursor.execute.side_effect = execute_side_effect
    fake_cursor.fetchall.side_effect = fetchall_side_effect
    fake_cursor.fetchone.side_effect = lambda: None

    with patch("dcmexporter.orchestrator.open_connection") as oc:
        oc.return_value = fake_conn
        code = export(_cfg(out))

    assert code == 4
