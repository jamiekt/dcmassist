"""Pure helpers for splitting per-type DDL output into numbered files.

Large databases (e.g. EXPERIMENTATION) can produce a single ``table.sql`` over
40 MB, which is awkward to review and to diff. We split the per-type DDL into
chunks of ``DCMASSIST_EXPORT_OBJECTS_PER_FILE`` objects each (default 100),
naming files ``<slug>.sql``, ``<slug>2.sql``, ``<slug>3.sql``, ... so a small
export still produces just ``table.sql`` (no behaviour change for users below
the threshold).
"""

from __future__ import annotations

import os

DEFAULT_OBJECTS_PER_FILE = 100
OBJECTS_PER_FILE_ENV = "DCMASSIST_EXPORT_OBJECTS_PER_FILE"


def resolve_objects_per_file() -> int:
    """Return the configured chunk size, or the default if the env var isn't set.

    Raises ValueError on a malformed/non-positive value rather than silently
    falling back to the default - a typo in the env var should be loud.
    """
    raw = os.environ.get(OBJECTS_PER_FILE_ENV)
    if raw is None:
        return DEFAULT_OBJECTS_PER_FILE
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(
            f"{OBJECTS_PER_FILE_ENV}={raw!r} is not a positive integer"
        ) from exc
    if value <= 0:
        raise ValueError(f"{OBJECTS_PER_FILE_ENV}={raw!r} is not a positive integer")
    return value


def chunk_blocks(
    blocks: list[str], *, slug: str, size: int
) -> list[tuple[str, list[str]]]:
    """Split a list of DDL blocks into [(filename, blocks)] chunks.

    The first chunk keeps the original ``<slug>.sql`` name; subsequent chunks
    are ``<slug>2.sql``, ``<slug>3.sql``, ... (no ``<slug>1.sql``). An empty
    input yields an empty list - the caller decides whether to skip an empty
    type entirely.
    """
    if not blocks:
        return []
    out: list[tuple[str, list[str]]] = []
    for index, start in enumerate(range(0, len(blocks), size), start=1):
        chunk = blocks[start : start + size]
        suffix = "" if index == 1 else str(index)
        out.append((f"{slug}{suffix}.sql", chunk))
    return out
