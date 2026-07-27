"""Threads table — conversation metadata for history listing and /resume."""

from __future__ import annotations

from dataclasses import dataclass

from octop.infra.db.pool import DatabasePool
from octop.infra.db.repos._base import DbRow, bool_int, map_rows, now_ts


@dataclass(frozen=True)
class ThreadRow:
    id: int
    thread_id: str
    agent_id: str
    user_id: int
    channel_type: str
    session_key: str
    title: str | None
    last_active: int
    created_at: int
    pinned: bool = False

    @classmethod
    def from_row(cls, r: DbRow) -> ThreadRow:
        return cls(
            id=r["id"],
            thread_id=r["thread_id"],
            agent_id=r["agent_id"],
            user_id=r["user_id"],
            channel_type=r["channel_type"],
            session_key=r["session_key"],
            title=r["title"],
            last_active=r["last_active"],
            created_at=r["created_at"],
            pinned=bool(r["pinned"]),
        )


class ThreadRepo:
    def __init__(self, db: DatabasePool) -> None:
        self._db = db

    def insert(
        self,
        *,
        thread_id: str,
        agent_id: str,
        user_id: int,
        channel_type: str,
        session_key: str,
        title: str | None = None,
        last_active: int | None = None,
    ) -> None:
        ts = now_ts()
        with self._db.transaction() as conn:
            conn.execute(
                "INSERT INTO threads(thread_id, agent_id, user_id, channel_type, "
                "session_key, title, last_active, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    thread_id,
                    agent_id,
                    user_id,
                    channel_type,
                    session_key,
                    title,
                    ts if last_active is None else last_active,
                    ts,
                ),
            )

    def get(self, thread_id: str) -> ThreadRow | None:
        with self._db.connect() as conn:
            r = conn.execute("SELECT * FROM threads WHERE thread_id = ?", (thread_id,)).fetchone()
        return ThreadRow.from_row(r) if r else None

    def list_by_agent(self, *, agent_id: str, limit: int = 50) -> list[ThreadRow]:
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM threads WHERE agent_id = ? "
                "ORDER BY pinned DESC, last_active DESC, thread_id DESC LIMIT ?",
                (agent_id, limit),
            ).fetchall()
        return map_rows(rows, ThreadRow)

    def list_by_session(self, *, session_key: str, limit: int = 50) -> list[ThreadRow]:
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM threads WHERE session_key = ? "
                "ORDER BY last_active DESC, thread_id DESC LIMIT ?",
                (session_key, limit),
            ).fetchall()
        return map_rows(rows, ThreadRow)

    def set_title_if_null(self, thread_id: str, title: str) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                "UPDATE threads SET title = ? WHERE thread_id = ? AND title IS NULL",
                (title[:40], thread_id),
            )

    def update_title(self, thread_id: str, title: str) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                "UPDATE threads SET title = ? WHERE thread_id = ?",
                (title[:40], thread_id),
            )

    def set_pinned(self, thread_id: str, pinned: bool) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                "UPDATE threads SET pinned = ? WHERE thread_id = ?",
                (bool_int(pinned), thread_id),
            )

    def touch_last_active(self, thread_id: str) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                "UPDATE threads SET last_active = ? WHERE thread_id = ?",
                (now_ts(), thread_id),
            )

    def delete(self, thread_id: str) -> None:
        with self._db.transaction() as conn:
            conn.execute("DELETE FROM threads WHERE thread_id = ?", (thread_id,))
