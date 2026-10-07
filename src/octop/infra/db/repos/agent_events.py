"""Agent events repository — append-only Code Console event log (S3).

Dialect notes: ``ON CONFLICT DO NOTHING`` (without a conflict target) and
``executemany`` are supported by both SQLite and PostgreSQL, so the same SQL
runs on both drivers (``?`` placeholders are rewritten to ``%s`` by the pool).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from octop.infra.db.pool import DatabasePool
from octop.infra.db.repos._base import bool_int
from octop.infra.db.repos._base import DbRow

_EVENT_COLS = (
    "id, event_id, session_id, turn_id, seq, ts, kind, is_error, payload_json"
)

# Event kinds that carry conversational text usable for context replay.
REPLAY_KINDS = ("user_prompt", "agent_message")

DEFAULT_LIST_LIMIT = 500
MAX_LIST_LIMIT = 5000


@dataclass(frozen=True)
class AgentEventRow:
    event_id: str
    session_id: str
    seq: int
    ts: float
    kind: str
    payload: dict[str, Any] = field(default_factory=dict)
    turn_id: str = ""
    is_error: bool = False

    @classmethod
    def from_row(cls, r: DbRow) -> AgentEventRow:
        try:
            payload = json.loads(r["payload_json"] or "{}")
        except json.JSONDecodeError:
            payload = {}
        return cls(
            event_id=str(r["event_id"]),
            session_id=str(r["session_id"]),
            seq=int(r["seq"]),
            ts=float(r["ts"]),
            kind=str(r["kind"]),
            payload=payload if isinstance(payload, dict) else {},
            turn_id=str(r["turn_id"] or ""),
            is_error=bool(int(r["is_error"] or 0)),
        )


class AgentEventRepo:
    def __init__(self, db: DatabasePool) -> None:
        self._db = db

    def insert_many(self, events: list[AgentEventRow]) -> int:
        if not events:
            return 0
        payload = [
            (
                e.event_id,
                e.session_id,
                e.turn_id or "",
                e.seq,
                e.ts,
                e.kind,
                bool_int(e.is_error),
                json.dumps(e.payload or {}, ensure_ascii=False),
            )
            for e in events
        ]
        with self._db.transaction() as conn:
            conn.executemany(
                "INSERT INTO agent_events("
                "event_id, session_id, turn_id, seq, ts, kind, is_error, payload_json"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT DO NOTHING",
                payload,
            )
        return len(payload)

    def max_seq(self, session_id: str) -> int:
        with self._db.connect() as conn:
            r = conn.execute(
                "SELECT COALESCE(MAX(seq), 0) FROM agent_events WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        return int(r[0]) if r is not None else 0

    def count(self, session_id: str) -> int:
        with self._db.connect() as conn:
            r = conn.execute(
                "SELECT COUNT(1) FROM agent_events WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        return int(r[0]) if r is not None else 0

    def list_for_session(
        self,
        session_id: str,
        *,
        after_seq: int | None = None,
        limit: int | None = DEFAULT_LIST_LIMIT,
    ) -> list[AgentEventRow]:
        if limit is None or limit > MAX_LIST_LIMIT:
            limit = MAX_LIST_LIMIT
        sql = f"SELECT {_EVENT_COLS} FROM agent_events WHERE session_id = ?"
        params: list[Any] = [session_id]
        if after_seq is not None:
            sql += " AND seq > ?"
            params.append(int(after_seq))
        sql += " ORDER BY seq ASC LIMIT ?"
        params.append(int(limit))
        with self._db.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [AgentEventRow.from_row(r) for r in rows]

    def list_text_events(self, session_id: str, *, max_messages: int) -> list[AgentEventRow]:
        """Most recent conversational text events, returned in chronological order."""
        placeholders = ", ".join("?" for _ in REPLAY_KINDS)
        sql = (
            f"SELECT {_EVENT_COLS} FROM agent_events "
            f"WHERE session_id = ? AND kind IN ({placeholders}) "
            "ORDER BY seq DESC LIMIT ?"
        )
        params: list[Any] = [session_id, *REPLAY_KINDS, int(max_messages)]
        with self._db.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        events = [AgentEventRow.from_row(r) for r in rows]
        events.reverse()
        return events
