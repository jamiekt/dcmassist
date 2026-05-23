"""Wrapper around snowflake.connector that mirrors snow CLI's connection model."""

from __future__ import annotations

import os
from typing import Any

try:
    from snowflake.connector import connect as snowflake_connect
except ImportError:  # pragma: no cover - exercised when the connector is unavailable

    def snowflake_connect(*_args: Any, **_kwargs: Any) -> Any:  # type: ignore[misc]
        raise RuntimeError("snowflake-connector-python is not installed")


class SnowflakeConnectionError(RuntimeError):
    """Raised when the Snowflake connection cannot be established."""


def open_connection(connection_name: str | None) -> Any:
    """Open a Snowflake connection following snow CLI's resolution rules.

    Order of precedence:
    1. Explicit `connection_name` argument.
    2. SNOWFLAKE_DEFAULT_CONNECTION_NAME env var.
    3. snowflake-connector's own default behaviour (reads `~/.snowflake/connections.toml`).
    """
    name = connection_name or os.environ.get("SNOWFLAKE_DEFAULT_CONNECTION_NAME")
    try:
        if name:
            return snowflake_connect(connection_name=name)
        return snowflake_connect()
    except Exception as exc:  # noqa: BLE001 — we re-raise as a domain error
        raise SnowflakeConnectionError(
            f"Failed to open Snowflake connection (name={name!r}): {exc}"
        ) from exc


def resolve_account_identifier(conn: Any) -> str:
    """Return the account identifier from a connection, or '' if unavailable."""
    return str(getattr(conn, "account", "") or "")
