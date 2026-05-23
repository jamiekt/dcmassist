"""Wrapper around snowflake.connector that mirrors snow CLI's connection model."""

from __future__ import annotations

import os
from typing import Any

try:
    from snowflake.connector import connect as snowflake_connect
except ImportError:  # pragma: no cover - exercised when the connector is unavailable

    def snowflake_connect(*_args: Any, **_kwargs: Any) -> Any:  # type: ignore[misc]
        raise RuntimeError("snowflake-connector-python is not installed")


try:
    from snowflake.connector import DictCursor
except ImportError:  # pragma: no cover

    class DictCursor:  # type: ignore[no-redef]
        pass


class SnowflakeConnectionError(RuntimeError):
    """Raised when the Snowflake connection cannot be established."""


class _DictCursorConnection:
    """Thin wrapper that makes every `cursor()` call use a DictCursor.

    Plugins call `conn.cursor()` with no arguments; this delegates to the real
    connection but injects DictCursor so rows come back as dicts keyed by
    Snowflake's column names.
    """

    def __init__(self, inner: Any) -> None:
        self._inner = inner

    def cursor(self, cursor_class: Any = None) -> Any:
        return self._inner.cursor(cursor_class or DictCursor)

    def close(self) -> None:
        self._inner.close()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


def open_connection(connection_name: str | None) -> Any:
    """Open a Snowflake connection following snow CLI's resolution rules.

    Order of precedence:
    1. Explicit `connection_name` argument.
    2. SNOWFLAKE_DEFAULT_CONNECTION_NAME env var.
    3. snowflake-connector's own default behaviour (reads `~/.snowflake/connections.toml`).

    The returned connection always yields DictCursor-backed cursors so plugins
    receive dict rows keyed by Snowflake's column names.
    """
    name = connection_name or os.environ.get("SNOWFLAKE_DEFAULT_CONNECTION_NAME")
    try:
        if name:
            inner = snowflake_connect(connection_name=name)
        else:
            inner = snowflake_connect()
    except Exception as exc:  # noqa: BLE001 — we re-raise as a domain error
        raise SnowflakeConnectionError(
            f"Failed to open Snowflake connection (name={name!r}): {exc}"
        ) from exc
    return _DictCursorConnection(inner)


def resolve_account_identifier(conn: Any) -> str:
    """Return the account identifier from a connection, or '' if unavailable."""
    return str(getattr(conn, "account", "") or "")
