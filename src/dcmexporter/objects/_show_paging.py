"""Pagination helper for Snowflake SHOW statements.

Snowflake caps SHOW results at 10,000 rows. Schemas with more objects than that
will fail with `090153 (22000): The result set size exceeded the max number of
rows(10000) supported for SHOW statements`.

The documented workaround is `SHOW … LIMIT N FROM '<last_name>'`: results are
ordered by name, so we page by appending `LIMIT N` and, on each subsequent
call, `FROM '<last_name_seen>'`. We stop when a page returns fewer than `N`
rows (or zero rows).
"""

from __future__ import annotations

from typing import Any

DEFAULT_PAGE_SIZE = 10000


def paginated_show(
    cursor: Any,
    base_sql: str,
    *,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> list[dict[str, Any]]:
    """Run `base_sql` with LIMIT/FROM pagination and return the concatenated rows.

    `base_sql` should be a SHOW statement *without* a trailing LIMIT clause —
    e.g. `SHOW TABLES IN SCHEMA MYDB.PUBLIC`. The helper appends pagination on
    each call.
    """
    rows: list[dict[str, Any]] = []
    last_name: str | None = None
    while True:
        if last_name is None:
            sql = f"{base_sql} LIMIT {page_size}"
        else:
            sql = f"{base_sql} LIMIT {page_size} FROM '{_escape(last_name)}'"
        cursor.execute(sql)
        page = cursor.fetchall()
        if not page:
            break
        rows.extend(page)
        if len(page) < page_size:
            break
        last_name = page[-1]["name"]
    return rows


def _escape(name: str) -> str:
    return name.replace("'", "''")
