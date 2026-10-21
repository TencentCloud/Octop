"""Helpers shared across repo implementations."""

from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, Protocol, TypeVar
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

R_co = TypeVar("R_co", covariant=True)

UNSET = object()

# Row mapping returned by the DB driver (sqlite3.Row today; asyncpg.Record later).
DbRow = Mapping[str, Any]


class _FromRow(Protocol[R_co]):
    @classmethod
    def from_row(cls, row: DbRow) -> R_co: ...


def now_ts() -> int:
    return int(time.time())


def bool_int(value: bool) -> int:
    return 1 if value else 0


def map_rows[R_co](rows: Sequence[DbRow], cls: type[_FromRow[R_co]]) -> list[R_co]:
    return [cls.from_row(r) for r in rows]


def partial_updates(pairs: list[tuple[str, object | None]]) -> tuple[list[str], list[object]]:
    """Build SET clauses for optional fields (None = skip)."""
    clauses: list[str] = []
    params: list[object] = []
    for col, val in pairs:
        if val is None:
            continue
        clauses.append(f"{col} = ?")
        params.append(val)
    return clauses, params


def optional_updates(
    pairs: list[tuple[str, object]],
    *,
    sentinel: object = UNSET,
) -> tuple[list[str], list[object]]:
    """Build SET clauses; sentinel means the field was omitted from the patch."""
    clauses: list[str] = []
    params: list[object] = []
    for col, val in pairs:
        if val is sentinel:
            continue
        clauses.append(f"{col} = ?")
        params.append(val)
    return clauses, params


def sql_in_placeholders(count: int) -> str:
    """``?, ?, ?`` for IN (...) clauses; swap ``?`` → ``%s`` when adding PostgreSQL."""
    return ", ".join("?" * count)


def _utc_offset_hours(timezone: str) -> float:
    """Get current UTC offset in hours for a timezone.

    Uses the current date's offset; DST edge cases at historical boundaries
    are acceptable for daily-bucket display purposes.
    """
    try:
        tz = ZoneInfo(timezone)
        offset = datetime.now(tz).utcoffset()
        return offset.total_seconds() / 3600 if offset else 0.0
    except (ZoneInfoNotFoundError, ValueError):
        return 0.0


def sql_unix_day_bucket(column: str, *, dialect: str = "sqlite", timezone: str = "UTC") -> str:
    """Expression that buckets a unix-epoch integer column into YYYY-MM-DD.

    Args:
        column: The unix-epoch integer column name.
        dialect: SQL dialect ("sqlite" or "postgresql").
        timezone: IANA timezone name (e.g. "Asia/Shanghai") for day boundaries.
                  Defaults to UTC (original behavior).
    """
    if timezone == "UTC":
        tz_offset_hours = 0.0
    else:
        tz_offset_hours = _utc_offset_hours(timezone)

    if dialect == "postgresql":
        # to_timestamp(ts) → timestamp without tz (interpreted as UTC)
        # AT TIME ZONE 'UTC' → timestamp with tz
        # AT TIME ZONE '<tz>' → timestamp without tz in target tz
        return f"to_char(to_timestamp({column}) AT TIME ZONE 'UTC' AT TIME ZONE '{timezone}', 'YYYY-MM-DD')"

    # SQLite: apply hour offset modifier
    if tz_offset_hours == 0:
        return f"date({column}, 'unixepoch')"
    elif tz_offset_hours > 0:
        hours = int(tz_offset_hours)
        return f"date({column}, 'unixepoch', '+{hours} hours')"
    else:
        hours = int(abs(tz_offset_hours))
        return f"date({column}, 'unixepoch', '-{hours} hours')"


def insert_returning_id(conn: Any, sql: str, params: Sequence[object]) -> int:
    """Run INSERT … RETURNING id (SQLite 3.35+ and PostgreSQL)."""
    row = conn.execute(f"{sql} RETURNING id", params).fetchone()
    if row is None:
        raise RuntimeError("INSERT RETURNING id returned no row")
    if isinstance(row, Mapping):
        return int(row["id"])
    return int(row[0])

