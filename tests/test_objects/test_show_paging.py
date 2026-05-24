"""Tests for the SHOW-pagination helper."""

from __future__ import annotations

from unittest.mock import MagicMock

from dcmassist.objects._show_paging import paginated_show


def test_single_page_under_limit() -> None:
    """If the first page returns fewer rows than the limit, stop after one call."""
    cursor = MagicMock()
    sql_log: list[str] = []
    cursor.execute.side_effect = lambda sql: sql_log.append(sql)
    cursor.fetchall.return_value = [
        {"name": "A"},
        {"name": "B"},
    ]
    out = paginated_show(cursor, "SHOW THINGS IN SCHEMA MYDB.PUBLIC", page_size=10000)
    assert sql_log == ["SHOW THINGS IN SCHEMA MYDB.PUBLIC LIMIT 10000"]
    assert [r["name"] for r in out] == ["A", "B"]


def test_multiple_pages_continues_until_short_page() -> None:
    """When a page returns exactly page_size rows, fetch another using FROM '<last>'."""
    cursor = MagicMock()
    sql_log: list[str] = []
    cursor.execute.side_effect = lambda sql: sql_log.append(sql)
    pages = iter(
        [
            [{"name": "A"}, {"name": "B"}],
            [{"name": "C"}, {"name": "D"}],
            [{"name": "E"}],
        ]
    )
    cursor.fetchall.side_effect = lambda: next(pages)
    out = paginated_show(cursor, "SHOW THINGS IN SCHEMA MYDB.PUBLIC", page_size=2)
    assert sql_log == [
        "SHOW THINGS IN SCHEMA MYDB.PUBLIC LIMIT 2",
        "SHOW THINGS IN SCHEMA MYDB.PUBLIC LIMIT 2 FROM 'B'",
        "SHOW THINGS IN SCHEMA MYDB.PUBLIC LIMIT 2 FROM 'D'",
    ]
    assert [r["name"] for r in out] == ["A", "B", "C", "D", "E"]


def test_empty_first_page_stops() -> None:
    cursor = MagicMock()
    sql_log: list[str] = []
    cursor.execute.side_effect = lambda sql: sql_log.append(sql)
    cursor.fetchall.return_value = []
    out = paginated_show(cursor, "SHOW THINGS IN SCHEMA MYDB.PUBLIC", page_size=2)
    assert sql_log == ["SHOW THINGS IN SCHEMA MYDB.PUBLIC LIMIT 2"]
    assert out == []


def test_full_page_with_no_more_results_stops_after_short_followup() -> None:
    """Exactly page_size on first page → fetch again; if second page is empty, stop."""
    cursor = MagicMock()
    sql_log: list[str] = []
    cursor.execute.side_effect = lambda sql: sql_log.append(sql)
    pages = iter(
        [
            [{"name": "A"}, {"name": "B"}],
            [],
        ]
    )
    cursor.fetchall.side_effect = lambda: next(pages)
    out = paginated_show(cursor, "SHOW THINGS IN SCHEMA MYDB.PUBLIC", page_size=2)
    assert sql_log == [
        "SHOW THINGS IN SCHEMA MYDB.PUBLIC LIMIT 2",
        "SHOW THINGS IN SCHEMA MYDB.PUBLIC LIMIT 2 FROM 'B'",
    ]
    assert [r["name"] for r in out] == ["A", "B"]


def test_on_page_callback_receives_running_total() -> None:
    """The optional on_page callback fires once per non-empty page with the cumulative count."""
    cursor = MagicMock()
    cursor.execute.side_effect = lambda sql: None
    pages = iter(
        [
            [{"name": "A"}, {"name": "B"}],
            [{"name": "C"}, {"name": "D"}],
            [{"name": "E"}],
        ]
    )
    cursor.fetchall.side_effect = lambda: next(pages)
    seen: list[int] = []
    paginated_show(
        cursor,
        "SHOW THINGS IN SCHEMA MYDB.PUBLIC",
        page_size=2,
        on_page=seen.append,
    )
    assert seen == [2, 4, 5]


def test_last_name_with_single_quote_is_escaped() -> None:
    """Snowflake string escape: ' → ''."""
    cursor = MagicMock()
    sql_log: list[str] = []
    cursor.execute.side_effect = lambda sql: sql_log.append(sql)
    pages = iter(
        [
            [{"name": "X"}, {"name": "TAB'LE"}],
            [{"name": "Y"}],
        ]
    )
    cursor.fetchall.side_effect = lambda: next(pages)
    paginated_show(cursor, "SHOW THINGS IN SCHEMA MYDB.PUBLIC", page_size=2)
    assert sql_log == [
        "SHOW THINGS IN SCHEMA MYDB.PUBLIC LIMIT 2",
        "SHOW THINGS IN SCHEMA MYDB.PUBLIC LIMIT 2 FROM 'TAB''LE'",
    ]
