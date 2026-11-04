"""Same-row leases that keep one Octop instance active for a cron run or channel."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

# Long enough for a slow agent turn, short enough that a dead owner is replaced
# within about a minute. Renew well before the deadline.
LEASE_SECONDS = 90
RENEW_SECONDS = 30
RECONCILE_SECONDS = 25


def unix_now_sql(dialect: str) -> str:
    """Database clock as integer Unix seconds, evaluated inside the write."""
    if dialect == "postgresql":
        return "CAST(EXTRACT(EPOCH FROM clock_timestamp()) AS BIGINT)"
    if dialect == "sqlite":
        return "CAST(strftime('%s','now') AS INTEGER)"
    msg = f"unsupported database dialect {dialect!r}"
    raise ValueError(msg)


def cell(row: Mapping[str, Any], key: str, default: Any = None) -> Any:
    try:
        return row[key]
    except (KeyError, IndexError):
        return default


def opt_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)
