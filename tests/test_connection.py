"""Tests for the snow-CLI-style connection resolver."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from dcmexporter.connection import (
    SnowflakeConnectionError,
    open_connection,
    resolve_account_identifier,
)


def test_open_connection_uses_named_connection() -> None:
    with patch("dcmexporter.connection.snowflake_connect") as connect:
        connect.return_value = MagicMock()
        open_connection(connection_name="MYCONN")
    connect.assert_called_once_with(connection_name="MYCONN")


def test_open_connection_default_uses_env_var(monkeypatch) -> None:
    monkeypatch.setenv("SNOWFLAKE_DEFAULT_CONNECTION_NAME", "envconn")
    with patch("dcmexporter.connection.snowflake_connect") as connect:
        connect.return_value = MagicMock()
        open_connection(connection_name=None)
    connect.assert_called_once_with(connection_name="envconn")


def test_open_connection_no_name_no_env_uses_default(monkeypatch) -> None:
    monkeypatch.delenv("SNOWFLAKE_DEFAULT_CONNECTION_NAME", raising=False)
    with patch("dcmexporter.connection.snowflake_connect") as connect:
        connect.return_value = MagicMock()
        open_connection(connection_name=None)
    connect.assert_called_once_with()


def test_open_connection_failure_wraps() -> None:
    with patch("dcmexporter.connection.snowflake_connect") as connect:
        connect.side_effect = RuntimeError("boom")
        with pytest.raises(SnowflakeConnectionError, match="boom"):
            open_connection(connection_name="bad")


def test_resolve_account_identifier_returns_attribute() -> None:
    conn = MagicMock()
    conn.account = "AB12345"
    assert resolve_account_identifier(conn) == "AB12345"


def test_resolve_account_identifier_returns_empty_when_missing() -> None:
    conn = MagicMock(spec=[])  # no `account` attribute
    assert resolve_account_identifier(conn) == ""
