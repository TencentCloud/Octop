"""Durable pending ``ask_user_question`` records."""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass
from typing import Any, Literal

from octop.infra.db.pool import DatabasePool
from octop.infra.db.repos._base import DbRow, now_ts

QuestionStatus = Literal["pending", "resuming", "answered", "cancelled"]


def _json_list(value: Any) -> list[dict[str, Any]]:
    parsed = json.loads(value) if isinstance(value, str) else value
    if not isinstance(parsed, list):
        return []
    return [dict(item) for item in parsed if isinstance(item, dict)]


@dataclass(frozen=True)
class PendingUserQuestionRow:
    pending_id: str
    thread_id: str
    agent_id: str
    user_id: int
    session_key: str
    channel_type: str
    questions: list[dict[str, Any]]
    answer: list[dict[str, Any]] | None
    status: QuestionStatus
    created_at: int
    answered_at: int | None

    @classmethod
    def from_row(cls, row: DbRow) -> PendingUserQuestionRow:
        raw_answer = row["answer_json"]
        return cls(
            pending_id=str(row["pending_id"]),
            thread_id=str(row["thread_id"]),
            agent_id=str(row["agent_id"]),
            user_id=int(row["user_id"]),
            session_key=str(row["session_key"]),
            channel_type=str(row["channel_type"]),
            questions=_json_list(row["questions_json"]),
            answer=_json_list(raw_answer) if raw_answer is not None else None,
            status=str(row["status"]),  # type: ignore[arg-type]
            created_at=int(row["created_at"]),
            answered_at=int(row["answered_at"]) if row["answered_at"] is not None else None,
        )


class PendingUserQuestionRepo:
    def __init__(self, db: DatabasePool) -> None:
        self._db = db

    def recover_interrupted_resumes(self) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                "UPDATE pending_user_questions SET status = 'pending' WHERE status = 'resuming'"
            )

    def register(
        self,
        *,
        thread_id: str,
        agent_id: str,
        user_id: int,
        session_key: str,
        channel_type: str,
        questions: list[dict[str, Any]],
    ) -> PendingUserQuestionRow:
        encoded = json.dumps(questions, ensure_ascii=False, separators=(",", ":"))
        with self._db.transaction() as conn:
            existing = conn.execute(
                "SELECT * FROM pending_user_questions "
                "WHERE thread_id = ? AND agent_id = ? AND user_id = ? AND status = 'pending' "
                "ORDER BY created_at DESC LIMIT 1",
                (thread_id, agent_id, user_id),
            ).fetchone()
            if existing is not None and str(existing["questions_json"]) == encoded:
                return PendingUserQuestionRow.from_row(existing)
            conn.execute(
                "UPDATE pending_user_questions SET status = 'cancelled' "
                "WHERE thread_id = ? AND agent_id = ? AND status = 'pending'",
                (thread_id, agent_id),
            )
            pending_id = secrets.token_hex(6)
            created_at = now_ts()
            conn.execute(
                "INSERT INTO pending_user_questions("
                "pending_id, thread_id, agent_id, user_id, session_key, channel_type, "
                "questions_json, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)",
                (
                    pending_id,
                    thread_id,
                    agent_id,
                    user_id,
                    session_key,
                    channel_type,
                    encoded,
                    created_at,
                ),
            )
        row = self.get(pending_id)
        assert row is not None
        return row

    def get(self, pending_id: str) -> PendingUserQuestionRow | None:
        with self._db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM pending_user_questions WHERE pending_id = ?", (pending_id,)
            ).fetchone()
        return PendingUserQuestionRow.from_row(row) if row is not None else None

    def pending_for_thread(
        self, thread_id: str, *, agent_id: str, user_id: int
    ) -> PendingUserQuestionRow | None:
        with self._db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM pending_user_questions "
                "WHERE thread_id = ? AND agent_id = ? AND user_id = ? AND status = 'pending' "
                "ORDER BY created_at DESC LIMIT 1",
                (thread_id, agent_id, user_id),
            ).fetchone()
        return PendingUserQuestionRow.from_row(row) if row is not None else None

    def pending_for_session(
        self, session_key: str, *, agent_id: str
    ) -> PendingUserQuestionRow | None:
        with self._db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM pending_user_questions "
                "WHERE session_key = ? AND agent_id = ? AND status = 'pending' "
                "ORDER BY created_at DESC LIMIT 1",
                (session_key, agent_id),
            ).fetchone()
        return PendingUserQuestionRow.from_row(row) if row is not None else None

    def claim(self, pending_id: str, *, agent_id: str, user_id: int) -> bool:
        with self._db.transaction() as conn:
            cursor = conn.execute(
                "UPDATE pending_user_questions SET status = 'resuming' "
                "WHERE pending_id = ? AND agent_id = ? AND user_id = ? AND status = 'pending'",
                (pending_id, agent_id, user_id),
            )
            return bool(cursor.rowcount)

    def release(self, pending_id: str) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                "UPDATE pending_user_questions SET status = 'pending' "
                "WHERE pending_id = ? AND status = 'resuming'",
                (pending_id,),
            )

    def mark_answered(self, pending_id: str, answers: list[dict[str, Any]]) -> None:
        encoded = json.dumps(answers, ensure_ascii=False, separators=(",", ":"))
        with self._db.transaction() as conn:
            conn.execute(
                "UPDATE pending_user_questions "
                "SET status = 'answered', answer_json = ?, answered_at = ? "
                "WHERE pending_id = ? AND status = 'resuming'",
                (encoded, now_ts(), pending_id),
            )


__all__ = ["PendingUserQuestionRepo", "PendingUserQuestionRow"]
