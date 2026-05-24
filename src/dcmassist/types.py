"""Canonical Snowflake DCM object types and FQN helper.

The DCM_TYPES tuple mirrors the supported-entities list at:
https://docs.snowflake.com/en/user-guide/dcm-projects/dcm-projects-supported-entities
"""

from __future__ import annotations

from dataclasses import dataclass

V1_TYPES: tuple[str, ...] = (
    "Schema",
    "Table",
    "View",
    "Sequence",
    "Stage",
    "File format",
    "Tag",
)

# Database is intentionally NOT in V1_TYPES: DCM rejects DEFINE DATABASE for
# the database the project lives in ("Project cannot manage its parent
# database"). Treating it as unimplemented makes the type name still validate
# but never produces a DEFINE block.
UNIMPLEMENTED_TYPES: tuple[str, ...] = (
    "Database",
    "Dynamic table",
    "Task",
    "Alert",
    "SQL function",
    "Data metric function",
    "SQL procedure",
    "Role",
    "Database role",
    "Grant",
    "Authentication policy",
)

DCM_TYPES: tuple[str, ...] = V1_TYPES + UNIMPLEMENTED_TYPES


def normalise_type(value: str) -> str:
    """Map a user-supplied type string to its canonical form (case-insensitive)."""
    lower = value.strip().lower()
    for canonical in DCM_TYPES:
        if canonical.lower() == lower:
            return canonical
    raise ValueError(f"Unknown DCM object type: {value!r}")


@dataclass(frozen=True)
class FQN:
    database: str
    schema: str | None
    name: str

    def __str__(self) -> str:
        if self.schema is None:
            return self.name
        return f"{self.database}.{self.schema}.{self.name}"

    @property
    def quoted(self) -> str:
        """Snowflake-quoted form: `"DB"."SCHEMA"."NAME"`.

        Required for identifiers that aren't valid bare names — leading digit,
        non-uppercase letters, special characters. Without quoting, Snowflake
        silently up-cases and rejects names that were created with quotes.
        Embedded `"` is escaped by doubling it.
        """
        parts = (
            [self.database, self.schema, self.name] if self.schema else [self.database]
        )
        return ".".join(f'"{p.replace(chr(34), chr(34) * 2)}"' for p in parts)
