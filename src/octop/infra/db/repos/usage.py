"""Token usage ledger access."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from octop.infra.db.pool import DatabasePool
from octop.infra.db.repos._base import (
    DbRow,
    insert_returning_id,
    now_ts,
    sql_unix_day_bucket,
)


@dataclass(frozen=True)
class UsageRow:
    id: int
    ts: int
    agent_id: str
    user_id: int
    thread_id: str
    model: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    source: str

    @classmethod
    def from_row(cls, r: DbRow) -> UsageRow:
        return cls(
            id=r["id"],
            ts=r["ts"],
            agent_id=r["agent_id"],
            user_id=r["user_id"],
            thread_id=r["thread_id"],
            model=r["model"],
            input_tokens=r["input_tokens"],
            output_tokens=r["output_tokens"],
            total_tokens=r["total_tokens"],
            source=r["source"],
        )


# Time-window aliases used by the API. Each maps to ``(start_seconds, end_seconds)``
# tuples computed against ``time.time()`` at query time. Buckets that span
# calendar months/days respect the server's local timezone — finnie's API
# also accepts a ``tz`` override but for octop's MVP the server's TZ is the
# only reference; that's fine for self-hosted single-tenant deploys.
_DAY_S = 86_400


def _resolve_window(window: str) -> tuple[int, int]:
    now = int(time.time())
    end = now + 1
    if window == "today":
        # Midnight today (server local TZ)
        start = now - (now % _DAY_S)
        return start, end
    if window == "yesterday":
        start_today = now - (now % _DAY_S)
        return start_today - _DAY_S, start_today
    if window == "last_7d":
        return now - 7 * _DAY_S, end
    if window == "last_30d":
        return now - 30 * _DAY_S, end
    if window == "all":
        return 0, end
    # Default: last_30d
    return now - 30 * _DAY_S, end


class UsageRepo:
    def __init__(self, db: DatabasePool):
        self._db = db

    # --- write -----------------------------------------------------------

    def record(
        self,
        *,
        agent_id: str,
        user_id: int,
        input_tokens: int,
        output_tokens: int,
        model: str = "",
        thread_id: str = "",
        source: str = "chat",
        ts: int | None = None,
    ) -> int:
        """Append one usage row. Returns the new row id."""
        with self._db.connect() as conn:
            return insert_returning_id(
                conn,
                """
                INSERT INTO usage_log (
                    ts, agent_id, user_id, thread_id, model,
                    input_tokens, output_tokens, total_tokens, source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ts or now_ts(),
                    agent_id,
                    user_id,
                    thread_id,
                    model,
                    int(input_tokens),
                    int(output_tokens),
                    int(input_tokens) + int(output_tokens),
                    source,
                ),
            )

    # --- read / aggregate ------------------------------------------------

    def summary(
        self,
        *,
        user_id: int | None = None,
        agent_id: str | None = None,
        window: str = "last_30d",
        granularity: str = "by_day",
    ) -> dict[str, Any]:
        """Aggregate usage rows, optionally filtered to one user/agent.

        ``user_id=None`` and ``agent_id=None`` returns global totals
        (admin scope); otherwise rows are scoped accordingly.
        """
        start, end = _resolve_window(window)

        where: list[str] = ["ts >= ?", "ts < ?"]
        params: list[Any] = [start, end]
        if user_id is not None:
            where.append("user_id = ?")
            params.append(user_id)
        if agent_id is not None:
            where.append("agent_id = ?")
            params.append(agent_id)
        where_sql = " AND ".join(where)

        # Roll-up totals
        with self._db.connect() as conn:
            row = conn.execute(
                f"""
                SELECT
                    COALESCE(SUM(input_tokens), 0)  AS input_tokens,
                    COALESCE(SUM(output_tokens), 0) AS output_tokens,
                    COALESCE(SUM(total_tokens), 0)  AS total_tokens,
                    COUNT(*)                         AS turns
                FROM usage_log WHERE {where_sql}
                """,
                params,
            ).fetchone()
            totals = {
                "input_tokens": int(row["input_tokens"]),
                "output_tokens": int(row["output_tokens"]),
                "total_tokens": int(row["total_tokens"]),
                "turns": int(row["turns"]),
            }

            buckets: list[dict[str, Any]] = []
            if granularity == "by_day":
                day_expr = sql_unix_day_bucket("ts", dialect=self._db.dialect)
                bucket_rows = conn.execute(
                    f"""
                    SELECT
                        {day_expr} AS bucket,
                        SUM(input_tokens)  AS input_tokens,
                        SUM(output_tokens) AS output_tokens,
                        SUM(total_tokens)  AS total_tokens,
                        COUNT(*)            AS turns
                    FROM usage_log WHERE {where_sql}
                    GROUP BY bucket
                    ORDER BY bucket DESC
                    LIMIT 100
                    """,
                    params,
                ).fetchall()
                buckets = [
                    {
                        "key": r["bucket"],
                        "label": r["bucket"],
                        "input_tokens": int(r["input_tokens"] or 0),
                        "output_tokens": int(r["output_tokens"] or 0),
                        "total_tokens": int(r["total_tokens"] or 0),
                        "turns": int(r["turns"] or 0),
                    }
                    for r in bucket_rows
                ]
            elif granularity == "by_agent":
                bucket_rows = conn.execute(
                    f"""
                    SELECT
                        agent_id           AS bucket,
                        SUM(input_tokens)  AS input_tokens,
                        SUM(output_tokens) AS output_tokens,
                        SUM(total_tokens)  AS total_tokens,
                        COUNT(*)            AS turns
                    FROM usage_log WHERE {where_sql}
                    GROUP BY bucket
                    ORDER BY total_tokens DESC
                    LIMIT 100
                    """,
                    params,
                ).fetchall()
                buckets = [
                    {
                        "key": r["bucket"],
                        "label": r["bucket"],
                        "input_tokens": int(r["input_tokens"] or 0),
                        "output_tokens": int(r["output_tokens"] or 0),
                        "total_tokens": int(r["total_tokens"] or 0),
                        "turns": int(r["turns"] or 0),
                    }
                    for r in bucket_rows
                ]
            elif granularity == "by_model":
                bucket_rows = conn.execute(
                    f"""
                    SELECT
                        COALESCE(NULLIF(model, ''), '(unknown)') AS bucket,
                        SUM(input_tokens)  AS input_tokens,
                        SUM(output_tokens) AS output_tokens,
                        SUM(total_tokens)  AS total_tokens,
                        COUNT(*)            AS turns
                    FROM usage_log WHERE {where_sql}
                    GROUP BY bucket
                    ORDER BY total_tokens DESC
                    LIMIT 100
                    """,
                    params,
                ).fetchall()
                buckets = [
                    {
                        "key": r["bucket"],
                        "label": r["bucket"],
                        "input_tokens": int(r["input_tokens"] or 0),
                        "output_tokens": int(r["output_tokens"] or 0),
                        "total_tokens": int(r["total_tokens"] or 0),
                        "turns": int(r["turns"] or 0),
                    }
                    for r in bucket_rows
                ]
            # ``total`` granularity → no buckets

        avg = totals["total_tokens"] // totals["turns"] if totals["turns"] else 0
        return {
            "window": window,
            "granularity": granularity,
            "range_start": start,
            "range_end": end,
            **totals,
            "avg_per_turn": avg,
            "buckets": buckets,
        }

    def thread_totals(self, *, agent_id: str, thread_id: str) -> dict[str, int]:
        """Aggregate token usage for a single thread."""
        with self._db.connect() as conn:
            row = conn.execute(
                """
                SELECT
                    COALESCE(SUM(input_tokens), 0)  AS input_tokens,
                    COALESCE(SUM(output_tokens), 0) AS output_tokens,
                    COALESCE(SUM(total_tokens), 0)  AS total_tokens,
                    COUNT(*)                         AS turns
                FROM usage_log
                WHERE agent_id = ? AND thread_id = ?
                """,
                (agent_id, thread_id),
            ).fetchone()
        return {
            "input_tokens": int(row["input_tokens"]),
            "output_tokens": int(row["output_tokens"]),
            "total_tokens": int(row["total_tokens"]),
            "turns": int(row["turns"]),
        }
