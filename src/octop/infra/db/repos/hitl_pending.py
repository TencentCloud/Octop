"""Data-access layer for the durable HITL pending records table.

``hitl_pending_records`` mirrors :class:`octop.infra.gateway.hitl.store.
HitlPendingRecord` so ask/approval cards survive server restarts. The gateway
store owns record semantics and the hot cache; this repo is the durability
layer (JSON columns encode/decode here).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from octop.infra.db.pool import DatabasePool
from octop.infra.db.repos._base import DbRow

_UPSERT_SQL = """
INSERT INTO hitl_pending_records(
  pending_id, thread_id, agent_id, user_id, session_key, channel_type,
  action_requests, review_configs, created_at, status,
  ask_question_index, ask_answers
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(pending_id) DO UPDATE SET
  thread_id = excluded.thread_id,
  agent_id = excluded.agent_id,
  user_id = excluded.user_id,
  session_key = excluded.session_key,
  channel_type = excluded.channel_type,
  action_requests = excluded.action_requests,
  review_configs = excluded.review_configs,
  created_at = excluded.created_at,
  status = excluded.status,
  ask_question_index = excluded.ask_question_index,
  ask_answers = excluded.ask_answers
"""

_SELECT_COLUMNS = (
    "pending_id, thread_id, agent_id, user_id, session_key, channel_type, "
    "action_requests, review_configs, created_at, status, "
    "ask_question_index, ask_answers"
)


@dataclass(frozen=True)
class HitlPendingRow:
    pending_id: str
    thread_id: str
    agent_id: str
    user_id: int
    session_key: str
    channel_type: str
    action_requests: list[dict[str, Any]]
    review_configs: list[dict[str, Any]] | None
    created_at: float
    status: str
    ask_question_index: int
    ask_answers: list[str]

    @classmethod
    def from_row(cls, row: DbRow) -> HitlPendingRow:
        review_configs: list[dict[str, Any]] | None = None
        if row["review_configs"] is not None:
            review_configs = _load_json_list(row["review_configs"])
        return cls(
            pending_id=str(row["pending_id"]),
            thread_id=str(row["thread_id"]),
            agent_id=str(row["agent_id"]),
            user_id=int(row["user_id"]),
            session_key=str(row["session_key"]),
            channel_type=str(row["channel_type"]),
            action_requests=_load_json_list(row["action_requests"]),
            review_configs=review_configs,
            created_at=float(row["created_at"]),
            status=str(row["status"]),
            ask_question_index=int(row["ask_question_index"]),
            ask_answers=[str(item) for item in _load_json_list(row["ask_answers"])],
        )


def _load_json_list(raw: object) -> list[Any]:
    if isinstance(raw, (list, tuple)):
        return list(raw)
    if not isinstance(raw, str) or not raw.strip():
        return []
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        return []
    return parsed if isinstance(parsed, list) else []


class HitlPendingRepo:
    """Data-access object for the hitl_pending_records table."""

    def __init__(self, db: DatabasePool) -> None:
        self._db = db

    def upsert(
        self,
        *,
        pending_id: str,
        thread_id: str,
        agent_id: str,
        user_id: int,
        session_key: str,
        channel_type: str,
        action_requests: list[dict[str, Any]],
        review_configs: list[dict[str, Any]] | None,
        created_at: float,
        status: str,
        ask_question_index: int,
        ask_answers: list[str],
    ) -> None:
        """Insert or replace one pending record row (full write-through)."""
        with self._db.transaction() as conn:
            conn.execute(
                _UPSERT_SQL,
                (
                    pending_id,
                    thread_id,
                    agent_id,
                    user_id,
                    session_key,
                    channel_type,
                    json.dumps(action_requests, ensure_ascii=False),
                    (
                        json.dumps(review_configs, ensure_ascii=False)
                        if review_configs is not None
                        else None
                    ),
                    created_at,
                    status,
                    ask_question_index,
                    json.dumps(ask_answers, ensure_ascii=False),
                ),
            )

    def delete(self, pending_id: str) -> None:
        with self._db.connect() as conn:
            conn.execute(
                "DELETE FROM hitl_pending_records WHERE pending_id = ?",
                (pending_id,),
            )

    def list_pending(self) -> list[HitlPendingRow]:
        """Return every row still marked pending; the store applies the TTL."""
        with self._db.connect() as conn:
            rows = conn.execute(
                f"SELECT {_SELECT_COLUMNS} FROM hitl_pending_records "
                "WHERE status = 'pending' ORDER BY created_at"
            ).fetchall()
        return [HitlPendingRow.from_row(row) for row in rows]
