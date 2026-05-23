"""Synthesize CREATE OR REPLACE STAGE DDL from DESC STAGE output.

Snowflake does NOT support GET_DDL('STAGE', …) — verified live 2026-05-23. The
workaround is to read structured properties via DESC STAGE and emit a minimal
DDL covering URL + STORAGE_INTEGRATION. AWS/Azure credentials and other secrets
are deliberately excluded — exported DDL is committed to a DCM project (i.e.
git), and credentials belong to the storage integration, not the stage.

Stages without a storage integration (i.e. legacy stages with embedded
credentials only) are not exportable in v1 and raise StageNotExportable; the
orchestrator's per-object catch will log and skip them.
"""

from __future__ import annotations

import json
from typing import Any

from dcmexporter.types import FQN


class StageNotExportable(RuntimeError):
    """Raised when a stage cannot be safely synthesized into committable DDL."""


def synthesize_stage_ddl(fqn: FQN, desc_rows: list[dict[str, Any]]) -> str:
    """Build a minimal CREATE OR REPLACE STAGE statement.

    Inputs:
      fqn: the stage's fully-qualified name.
      desc_rows: raw rows from `DESC STAGE <fqn>`. Each row has the keys
        `parent_property`, `property`, `property_value` (DictCursor shape).

    Output: a SQL string ending in `;`.

    Raises StageNotExportable if URL or STORAGE_INTEGRATION is missing.
    """
    properties: dict[tuple[str, str], str] = {
        (row["parent_property"], row["property"]): row["property_value"]
        for row in desc_rows
    }

    url_raw = properties.get(("STAGE_LOCATION", "URL"), "")
    url = _unwrap_url(url_raw)
    integration = properties.get(("STAGE_INTEGRATION", "STORAGE_INTEGRATION"), "")

    if not url:
        raise StageNotExportable(
            f"stage {fqn}: DESC STAGE returned no STAGE_LOCATION/URL"
        )
    if not integration:
        raise StageNotExportable(
            f"stage {fqn}: no STORAGE_INTEGRATION; v1 refuses to export "
            "stages with embedded credentials"
        )

    return (
        f"CREATE OR REPLACE STAGE {fqn}\n"
        f"  URL = '{url}'\n"
        f"  STORAGE_INTEGRATION = {integration}\n"
        ";"
    )


def _unwrap_url(raw: str) -> str:
    """DESC STAGE encodes URL as a JSON array string: '["s3://..."]'.

    Be lenient: if it parses as a list with one string, use that. Otherwise
    treat the raw value as the URL (works for the rare scalar case).
    """
    if not raw:
        return ""
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        return raw
    if isinstance(parsed, list) and parsed and isinstance(parsed[0], str):
        return parsed[0]
    if isinstance(parsed, str):
        return parsed
    return raw
