"""Append-only chat trajectory event log."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any, cast

from octop.infra.db.pool import DatabasePool
from octop.infra.db.repos._base import DbRow, bool_int, sql_in_placeholders
from octop.infra.trajectory.types import TrajectoryEvent, TrajectoryKind

_SELECT_COLS = (
    "event_id, agent_id, thread_id, seq, ts, kind, turn_id, "
    "request_seq, is_error, summary, payload_json"
)


def _event_from_row(row: DbRow) -> TrajectoryEvent:
    raw = row["payload_json"]
    loaded: Any = json.loads(str(raw)) if raw else {}
    payload: dict[str, Any] = loaded if isinstance(loaded, dict) else {}
    turn_id = row["turn_id"]
    request_seq = row["request_seq"]
    return TrajectoryEvent(
        event_id=str(row["event_id"]),
        thread_id=str(row["thread_id"]),
        agent_id=str(row["agent_id"]),
        seq=int(row["seq"]),
        ts=float(row["ts"]),
        kind=cast(TrajectoryKind, str(row["kind"])),
        turn_id=str(turn_id) if turn_id else None,
        request_seq=int(request_seq) if request_seq is not None else None,
        is_error=bool(row["is_error"]),
        summary=str(row["summary"] or ""),
        payload=payload,
    )


class TrajectoryEventRepo:
    def __init__(self, db: DatabasePool) -> None:
        self._db = db

    def append(self, event: TrajectoryEvent) -> bool:
        payload_json = json.dumps(event.payload, ensure_ascii=False)
        with self._db.transaction() as conn:
            cursor = conn.execute(
                "INSERT INTO trajectory_events("
                "event_id, agent_id, thread_id, seq, ts, kind, turn_id, "
                "request_seq, is_error, summary, payload_json"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT DO NOTHING",
                (
                    event.event_id,
                    event.agent_id,
                    event.thread_id,
                    event.seq,
                    event.ts,
                    event.kind,
                    event.turn_id,
                    event.request_seq,
                    bool_int(event.is_error),
                    event.summary,
                    payload_json,
                ),
            )
        return int(cursor.rowcount or 0) > 0

    def upsert(self, event: TrajectoryEvent) -> bool:
        payload_json = json.dumps(event.payload, ensure_ascii=False)
        with self._db.transaction() as conn:
            cursor = conn.execute(
                "INSERT INTO trajectory_events("
                "event_id, agent_id, thread_id, seq, ts, kind, turn_id, "
                "request_seq, is_error, summary, payload_json"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(event_id) DO UPDATE SET "
                "ts = excluded.ts, "
                "kind = excluded.kind, "
                "turn_id = excluded.turn_id, "
                "request_seq = excluded.request_seq, "
                "is_error = excluded.is_error, "
                "summary = excluded.summary, "
                "payload_json = excluded.payload_json",
                (
                    event.event_id,
                    event.agent_id,
                    event.thread_id,
                    event.seq,
                    event.ts,
                    event.kind,
                    event.turn_id,
                    event.request_seq,
                    bool_int(event.is_error),
                    event.summary,
                    payload_json,
                ),
            )
        return int(cursor.rowcount or 0) > 0

    def list_before(
        self,
        thread_id: str,
        *,
        before_seq: int | None,
        limit: int,
        kinds: list[str] | None,
    ) -> list[TrajectoryEvent]:
        if limit <= 0:
            return []
        if kinds is not None and not kinds:
            return []
        conditions = ["thread_id = ?"]
        params: list[object] = [thread_id]
        if before_seq is not None:
            conditions.append("seq < ?")
            params.append(before_seq)
        if kinds is not None:
            conditions.append(f"kind IN ({sql_in_placeholders(len(kinds))})")
            params.extend(kinds)
        params.append(limit)
        sql = (
            f"SELECT {_SELECT_COLS} FROM trajectory_events WHERE "
            + " AND ".join(conditions)
            + " ORDER BY seq DESC LIMIT ?"
        )
        with self._db.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        events = [_event_from_row(row) for row in rows]
        events.reverse()
        return events

    def list_from_seq(
        self,
        thread_id: str,
        *,
        from_seq: int,
        limit: int,
    ) -> list[TrajectoryEvent]:
        if limit <= 0:
            return []
        with self._db.connect() as conn:
            rows = conn.execute(
                f"SELECT {_SELECT_COLS} FROM trajectory_events "
                "WHERE thread_id = ? AND seq >= ? ORDER BY seq ASC LIMIT ?",
                (thread_id, from_seq, limit),
            ).fetchall()
        return [_event_from_row(row) for row in rows]

    def prune_older_than_user_turns(self, thread_id: str, keep_user_turns: int) -> int:
        """Drop events before the Nth-newest USER seq (keeps that user and later)."""
        if keep_user_turns <= 0:
            return 0
        with self._db.transaction() as conn:
            row = conn.execute(
                "SELECT seq FROM trajectory_events "
                "WHERE thread_id = ? AND kind = 'user' "
                "ORDER BY seq DESC LIMIT 1 OFFSET ?",
                (thread_id, keep_user_turns - 1),
            ).fetchone()
            if row is None:
                return 0
            cutoff = int(row["seq"])
            cursor = conn.execute(
                "DELETE FROM trajectory_events WHERE thread_id = ? AND seq < ?",
                (thread_id, cutoff),
            )
        return int(cursor.rowcount or 0)

    def get(self, event_id: str) -> TrajectoryEvent | None:
        with self._db.connect() as conn:
            row = conn.execute(
                f"SELECT {_SELECT_COLS} FROM trajectory_events WHERE event_id = ?",
                (event_id,),
            ).fetchone()
        return _event_from_row(row) if row is not None else None

    def delete_for_thread(self, thread_id: str) -> int:
        with self._db.transaction() as conn:
            cursor = conn.execute(
                "DELETE FROM trajectory_events WHERE thread_id = ?",
                (thread_id,),
            )
        return int(cursor.rowcount or 0)

    def iter_for_export(self, thread_id: str) -> Iterator[TrajectoryEvent]:
        with self._db.connect() as conn:
            rows = conn.execute(
                f"SELECT {_SELECT_COLS} FROM trajectory_events "
                "WHERE thread_id = ? ORDER BY seq ASC",
                (thread_id,),
            ).fetchall()
        for row in rows:
            yield _event_from_row(row)
