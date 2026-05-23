"""Synthesize CREATE OR REPLACE DATABASE DDL from a SHOW DATABASES row.

We avoid `GET_DDL('DATABASE', …)` because Snowflake returns the recursive DDL
of every contained schema/table/view/etc., which can take many minutes — or
effectively never finish — on large databases. dcmexporter exports each
contained object individually anyway, so the recursive call is pure waste.

A minimal `CREATE OR REPLACE DATABASE` is enough: the database statement only
needs to establish the database itself; child objects bring their own DDL.
"""

from __future__ import annotations

from typing import Any

from dcmexporter.types import FQN


class DatabaseNotExportable(RuntimeError):
    """Raised when a database row lacks the data needed to synthesize DDL."""


def synthesize_database_ddl(fqn: FQN, show_row: dict[str, Any]) -> str:
    """Build a minimal CREATE OR REPLACE DATABASE statement.

    Inputs:
      fqn: the database's FQN (schema is None for account-level objects).
      show_row: a row from `SHOW DATABASES LIKE '<name>'` (DictCursor shape).
        Relevant keys: `name`, `comment`.

    Output: a SQL string ending in `;`.

    Raises DatabaseNotExportable if `name` is missing.
    """
    if not show_row.get("name"):
        raise DatabaseNotExportable(f"database {fqn}: SHOW DATABASES row has no name")

    lines = [f"CREATE OR REPLACE DATABASE {fqn.name}"]
    comment = show_row.get("comment") or ""
    if comment:
        escaped = comment.replace("'", "''")
        lines.append(f"  COMMENT='{escaped}'")
    return "\n".join(lines) + "\n;"
