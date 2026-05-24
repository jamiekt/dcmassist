"""Synthesize CREATE OR REPLACE SCHEMA DDL from a SHOW SCHEMAS row.

We avoid `GET_DDL('SCHEMA', …)` because Snowflake returns the recursive DDL
of every contained table/view/etc., which can take a very long time on busy
schemas. dcmassist exports each contained object individually anyway, so
the recursive call is wasted work.

A minimal `CREATE OR REPLACE SCHEMA` is enough — child objects bring their
own DDL. We honour `TRANSIENT` and `MANAGED ACCESS` because those properties
can only be set at schema-create time.
"""

from __future__ import annotations

from typing import Any

from dcmassist.types import FQN


class SchemaNotExportable(RuntimeError):
    """Raised when a schema row lacks the data needed to synthesize DDL."""


def synthesize_schema_ddl(fqn: FQN, show_row: dict[str, Any]) -> str:
    """Build a minimal CREATE OR REPLACE SCHEMA statement.

    Inputs:
      fqn: the schema's FQN.
      show_row: a row from `SHOW SCHEMAS …` (DictCursor shape). Relevant
        keys: `name`, `comment`, `options` (e.g. "TRANSIENT, MANAGED ACCESS").

    Output: a SQL string ending in `;`.

    Raises SchemaNotExportable if `name` is missing.
    """
    if not show_row.get("name"):
        raise SchemaNotExportable(f"schema {fqn}: SHOW SCHEMAS row has no name")

    options_raw = show_row.get("options") or ""
    options = {
        token.strip().upper() for token in options_raw.split(",") if token.strip()
    }
    transient = "TRANSIENT" in options
    managed_access = "MANAGED ACCESS" in options

    head = (
        "CREATE OR REPLACE TRANSIENT SCHEMA"
        if transient
        else "CREATE OR REPLACE SCHEMA"
    )
    lines = [f"{head} {fqn.database}.{fqn.name}"]
    if managed_access:
        lines.append("  WITH MANAGED ACCESS")
    comment = show_row.get("comment") or ""
    if comment:
        escaped = comment.replace("'", "''")
        lines.append(f"  COMMENT='{escaped}'")
    return "\n".join(lines) + "\n;"
