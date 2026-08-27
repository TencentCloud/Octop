"""Projection rows used by the dashboard history API."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from octop.infra.db.pool import DatabasePool
from octop.infra.db.repos._base import DbRow, now_ts


@dataclass(frozen=True)
class ThreadMessageInput:
    message_id: str | None
    role: str
    message_json: str
    created_at: int


@dataclass(frozen=True)
class ThreadMessageRow:
    seq: int
    message_id: str | None
    role: str
    message_json: str
    created_at: int

    @classmethod
    def from_row(cls, row: DbRow) -> ThreadMessageRow:
        return cls(
            seq=int(row["seq"]),
            message_id=str(row["message_id"]) if row["message_id"] else None,
            role=str(row["role"]),
            message_json=str(row["message_json"]),
            created_at=int(row["created_at"]),
        )


@dataclass(frozen=True)
class ThreadProjectionCandidate:
    thread_id: str
    status: str


@dataclass(frozen=True)
class ThreadProjectionSummary:
    pending: int = 0
    queued: int = 0
    running: int = 0
    failed: int = 0

    @property
    def remaining(self) -> int:
        return self.pending + self.queued + self.running + self.failed


class ThreadMessageRepo:
    """Keep checkpoint-sized data out of normal dashboard history reads."""

    def __init__(self, db: DatabasePool) -> None:
        self._db = db

    def projection_status(self, thread_id: str) -> str:
        with self._db.connect() as conn:
            row = conn.execute(
                "SELECT status FROM thread_history_projection WHERE thread_id = ?",
                (thread_id,),
            ).fetchone()
        return str(row["status"]) if row else "pending"

    def mark_projection(
        self,
        thread_id: str,
        status: str,
        *,
        error: str | None = None,
    ) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                "INSERT INTO thread_history_projection(thread_id, status, updated_at, error) "
                "VALUES (?, ?, ?, ?) "
                "ON CONFLICT(thread_id) DO UPDATE SET "
                "status = excluded.status, updated_at = excluded.updated_at, error = excluded.error",
                (thread_id, status, now_ts(), error),
            )

    def migration_summary(self, *, agent_id: str, user_id: int) -> ThreadProjectionSummary:
        """Count legacy threads that still need a history projection."""
        counts = {"pending": 0, "queued": 0, "running": 0, "failed": 0}
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT COALESCE(p.status, 'pending') AS status, COUNT(*) AS total "
                "FROM threads t LEFT JOIN thread_history_projection p "
                "ON p.thread_id = t.thread_id "
                "WHERE t.agent_id = ? AND t.user_id = ? "
                "AND COALESCE(p.status, 'pending') != 'ready' "
                "GROUP BY COALESCE(p.status, 'pending')",
                (agent_id, user_id),
            ).fetchall()
        for row in rows:
            status = str(row["status"])
            if status in counts:
                counts[status] = int(row["total"])
            else:
                counts["pending"] += int(row["total"])
        return ThreadProjectionSummary(**counts)

    def migration_candidates(
        self,
        *,
        agent_id: str,
        user_id: int,
        limit: int,
    ) -> list[ThreadProjectionCandidate]:
        """Return recent legacy threads first without reading checkpoint blobs."""
        if limit <= 0:
            return []
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT t.thread_id, COALESCE(p.status, 'pending') AS status "
                "FROM threads t LEFT JOIN thread_history_projection p "
                "ON p.thread_id = t.thread_id "
                "WHERE t.agent_id = ? AND t.user_id = ? "
                "AND COALESCE(p.status, 'pending') != 'ready' "
                "ORDER BY t.last_active DESC, t.thread_id DESC LIMIT ?",
                (agent_id, user_id, limit),
            ).fetchall()
        return [
            ThreadProjectionCandidate(thread_id=str(row["thread_id"]), status=str(row["status"]))
            for row in rows
        ]

    def migration_active_thread_ids(self, *, agent_id: str, user_id: int) -> list[str]:
        """Persisted queued/running IDs, used to distinguish live work from restart residue."""
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT t.thread_id FROM threads t "
                "JOIN thread_history_projection p ON p.thread_id = t.thread_id "
                "WHERE t.agent_id = ? AND t.user_id = ? "
                "AND p.status IN ('queued', 'running')",
                (agent_id, user_id),
            ).fetchall()
        return [str(row["thread_id"]) for row in rows]

    def page(
        self,
        thread_id: str,
        *,
        limit: int,
        offset: int = 0,
    ) -> tuple[list[ThreadMessageRow], bool]:
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT seq, message_id, role, message_json, created_at "
                "FROM thread_messages WHERE thread_id = ? "
                "ORDER BY seq DESC LIMIT ? OFFSET ?",
                (thread_id, limit + 1, max(0, offset)),
            ).fetchall()
        has_more = len(rows) > limit
        page = [ThreadMessageRow.from_row(row) for row in rows[:limit]]
        page.reverse()
        return page, has_more

    def append_if_ready(
        self,
        thread_id: str,
        messages: Sequence[ThreadMessageInput],
    ) -> int:
        """Append one completed turn. Pending legacy threads wait for backfill."""
        if not messages:
            return 0
        inserted = 0
        with self._db.transaction() as conn:
            state = conn.execute(
                "SELECT status FROM thread_history_projection WHERE thread_id = ?",
                (thread_id,),
            ).fetchone()
            if state is None or str(state["status"]) != "ready":
                return 0
            if self._db.dialect == "postgresql":
                conn.execute(
                    "SELECT thread_id FROM threads WHERE thread_id = ? FOR UPDATE",
                    (thread_id,),
                ).fetchone()
            row = conn.execute(
                "SELECT COALESCE(MAX(seq), 0) AS max_seq FROM thread_messages WHERE thread_id = ?",
                (thread_id,),
            ).fetchone()
            seq = int(row["max_seq"]) if row else 0
            for message in messages:
                if message.message_id:
                    duplicate = conn.execute(
                        "SELECT 1 FROM thread_messages WHERE thread_id = ? AND message_id = ?",
                        (thread_id, message.message_id),
                    ).fetchone()
                    if duplicate is not None:
                        continue
                seq += 1
                conn.execute(
                    "INSERT INTO thread_messages("
                    "thread_id, seq, message_id, role, message_json, created_at"
                    ") VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        thread_id,
                        seq,
                        message.message_id,
                        message.role,
                        message.message_json,
                        message.created_at,
                    ),
                )
                inserted += 1
        return inserted

    def replace_all(
        self,
        thread_id: str,
        messages: Sequence[ThreadMessageInput],
    ) -> int:
        """Publish a decoded legacy checkpoint using short write batches.

        Readers are gated by ``status != ready``, so the batches stay invisible
        without holding SQLite's writer lock for the entire transcript.
        """
        with self._db.transaction() as conn:
            if self._db.dialect == "postgresql":
                conn.execute(
                    "SELECT thread_id FROM threads WHERE thread_id = ? FOR UPDATE",
                    (thread_id,),
                ).fetchone()
            conn.execute("DELETE FROM thread_messages WHERE thread_id = ?", (thread_id,))
        batch_size = 200
        for start in range(0, len(messages), batch_size):
            with self._db.transaction() as conn:
                for index, message in enumerate(messages[start : start + batch_size], start=start):
                    conn.execute(
                        "INSERT INTO thread_messages("
                        "thread_id, seq, message_id, role, message_json, created_at"
                        ") VALUES (?, ?, ?, ?, ?, ?)",
                        (
                            thread_id,
                            index + 1,
                            message.message_id,
                            message.role,
                            message.message_json,
                            message.created_at,
                        ),
                    )
        self.mark_projection(thread_id, "ready")
        return len(messages)
