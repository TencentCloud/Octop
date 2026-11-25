"""Data-access layer for the proactive care push records table.

The care_push_records table records the episode_id consumed by each proactive_care
push (used for 30-day dedup) along with delivery coordinates (thread_id, message_id)
and user reply status for backoff and downstream memory feedback.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from octop.infra.db.pool import DatabasePool
from octop.infra.db.repos._base import DbRow


@dataclass(frozen=True)
class CarePushRecord:
    """One row from ``care_push_records``."""

    id: str
    agent_id: str
    session_key: str
    episode_id: str
    pushed_at: int
    thread_id: str | None = None
    message_id: str | None = None
    care_text: str | None = None
    status: str = "sent"
    replied_at: int | None = None
    reply_message_id: str | None = None

    @classmethod
    def from_row(cls, row: DbRow) -> CarePushRecord:
        return cls(
            id=str(row["id"]),
            agent_id=str(row["agent_id"]),
            session_key=str(row["session_key"]),
            episode_id=str(row["episode_id"]),
            pushed_at=int(row["pushed_at"]),
            thread_id=str(row["thread_id"]) if row["thread_id"] else None,
            message_id=str(row["message_id"]) if row["message_id"] else None,
            care_text=str(row["care_text"]) if row["care_text"] is not None else None,
            status=str(row["status"] or "sent"),
            replied_at=int(row["replied_at"]) if row["replied_at"] is not None else None,
            reply_message_id=str(row["reply_message_id"]) if row["reply_message_id"] else None,
        )


class CarePushRepo:
    """Data-access object for the care_push_records table."""

    def __init__(self, db: DatabasePool) -> None:
        self._db = db

    def insert(
        self,
        *,
        agent_id: str,
        session_key: str,
        episode_ids: Sequence[str],
        pushed_at: int | None = None,
        thread_id: str | None = None,
        message_id: str | None = None,
        care_text: str | None = None,
    ) -> None:
        """Batch-insert push records for one proactive care delivery.

        Args:
            agent_id: The agent ID the push belongs to.
            session_key: The session key the push belongs to.
            episode_ids: The list of episode IDs consumed by this push.
            pushed_at: Push timestamp (unix); defaults to the current time.
            thread_id: Target thread ID where the care message was stored.
            message_id: Canonical ``AIMessage.id`` stored in the thread.
            care_text: Delivered care text (for reply correlation and feedback).
        """
        if not episode_ids:
            return
        ts = pushed_at if pushed_at is not None else int(time.time())
        rows = [
            (
                str(uuid.uuid4()),
                agent_id,
                session_key,
                ep_id,
                ts,
                thread_id,
                message_id,
                care_text,
                "sent",
            )
            for ep_id in episode_ids
        ]
        with self._db.transaction() as conn:
            conn.executemany(
                "INSERT INTO care_push_records("
                "id, agent_id, session_key, episode_id, pushed_at, "
                "thread_id, message_id, care_text, status"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )

    def mark_replied_for_thread(
        self,
        *,
        agent_id: str,
        thread_id: str,
        reply_message_id: str | None = None,
        replied_at: int | None = None,
    ) -> int:
        """Record that the user replied in *thread_id* after a proactive care push.

        The latest open (``status='sent'``) care push in *thread_id* is marked
        ``'replied'``; any older still-open pushes in the same thread are marked
        ``'ignored'`` so reply attribution stays tied to the message the user saw.

        Returns:
            Number of rows marked ``'replied'``.
        """
        tid = thread_id.strip()
        if not tid:
            return 0
        ts = replied_at if replied_at is not None else int(time.time())
        with self._db.transaction() as conn:
            latest = conn.execute(
                "SELECT message_id, pushed_at FROM care_push_records "
                "WHERE agent_id = ? AND thread_id = ? AND status = 'sent' AND pushed_at <= ? "
                "ORDER BY pushed_at DESC LIMIT 1",
                (agent_id, tid, ts),
            ).fetchone()
            if latest is None:
                return 0
            latest_mid = latest["message_id"]
            latest_pushed_at = int(latest["pushed_at"])
            if latest_mid:
                cur = conn.execute(
                    "UPDATE care_push_records "
                    "SET status = 'replied', replied_at = ?, reply_message_id = ? "
                    "WHERE agent_id = ? AND thread_id = ? AND status = 'sent' "
                    "AND message_id = ?",
                    (ts, reply_message_id, agent_id, tid, latest_mid),
                )
                replied_count = int(cur.rowcount or 0)
                conn.execute(
                    "UPDATE care_push_records "
                    "SET status = 'ignored' "
                    "WHERE agent_id = ? AND thread_id = ? AND status = 'sent' "
                    "AND pushed_at <= ? AND (message_id IS NULL OR message_id <> ?)",
                    (agent_id, tid, ts, latest_mid),
                )
            else:
                cur = conn.execute(
                    "UPDATE care_push_records "
                    "SET status = 'replied', replied_at = ?, reply_message_id = ? "
                    "WHERE agent_id = ? AND thread_id = ? AND status = 'sent' "
                    "AND pushed_at = ?",
                    (ts, reply_message_id, agent_id, tid, latest_pushed_at),
                )
                replied_count = int(cur.rowcount or 0)
                conn.execute(
                    "UPDATE care_push_records "
                    "SET status = 'ignored' "
                    "WHERE agent_id = ? AND thread_id = ? AND status = 'sent' "
                    "AND pushed_at < ?",
                    (agent_id, tid, latest_pushed_at),
                )
            return replied_count

    def count_consecutive_unanswered(self, agent_id: str, *, limit: int = 20) -> int:
        """Count consecutive recent care pushes for *agent_id* without a reply.

        Multiple episode rows emitted by the same delivery (sharing ``message_id``,
        or ``(pushed_at, session_key)`` for legacy rows) are collapsed into one push.
        """
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT message_id, pushed_at, session_key, status "
                "FROM care_push_records "
                "WHERE agent_id = ? "
                "ORDER BY pushed_at DESC LIMIT ?",
                (agent_id, max(limit * 3, 30)),
            ).fetchall()
        seen_keys: list[tuple[str, int, str]] = []
        push_replied: dict[tuple[str, int, str], bool] = {}
        for row in rows:
            mid = str(row["message_id"] or "")
            key = (mid, int(row["pushed_at"]), str(row["session_key"])) if not mid else (mid, 0, "")
            if key not in push_replied:
                if len(seen_keys) >= limit:
                    break
                seen_keys.append(key)
                push_replied[key] = False
            if str(row["status"] or "sent") == "replied":
                push_replied[key] = True
        streak = 0
        for key in seen_keys:
            if push_replied[key]:
                break
            streak += 1
        return streak

    def list_recent(self, agent_id: str, *, limit: int = 20) -> list[CarePushRecord]:
        """Return the most recent care push rows for *agent_id*."""
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT id, agent_id, session_key, episode_id, pushed_at, "
                "thread_id, message_id, care_text, status, replied_at, reply_message_id "
                "FROM care_push_records WHERE agent_id = ? "
                "ORDER BY pushed_at DESC LIMIT ?",
                (agent_id, limit),
            ).fetchall()
        return [CarePushRecord.from_row(r) for r in rows]

    def latest_pushed_at(self, agent_id: str) -> int | None:
        """Unix time of the most recent care push for ``agent_id``, if any."""
        with self._db.connect() as conn:
            row = conn.execute(
                "SELECT MAX(pushed_at) FROM care_push_records WHERE agent_id = ?",
                (agent_id,),
            ).fetchone()
        if row is None or row[0] is None:
            return None
        return int(row[0])

    def list_pushed_episode_ids(
        self,
        agent_id: str,
        *,
        after_days: int = 30,
    ) -> set[str]:
        """Query the set of episode_ids pushed within the last after_days days.

        Args:
            agent_id: The agent ID to query.
            after_days: Time window (days), default 30 days.

        Returns:
            The set of pushed episode_ids.
        """
        cutoff = int(time.time()) - after_days * 86400
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT episode_id FROM care_push_records "
                "WHERE agent_id = ? AND pushed_at >= ?",
                (agent_id, cutoff),
            ).fetchall()
        return {r[0] for r in rows}
