"""Data-access layer for the proactive care push records table.

The care_push_records table records the episode_id consumed by each proactive_care
push, used to avoid re-pushing the same event within 30 days.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Sequence

from octop.infra.db.pool import DatabasePool


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
    ) -> None:
        """Batch-insert push records.

        Args:
            agent_id: The agent ID the push belongs to.
            session_key: The session key the push belongs to.
            episode_ids: The list of episode IDs consumed by this push.
            pushed_at: Push timestamp (unix); defaults to the current time.
        """
        if not episode_ids:
            return
        ts = pushed_at if pushed_at is not None else int(time.time())
        rows = [(str(uuid.uuid4()), agent_id, session_key, ep_id, ts) for ep_id in episode_ids]
        with self._db.transaction() as conn:
            conn.executemany(
                "INSERT INTO care_push_records(id, agent_id, session_key, episode_id, pushed_at) "
                "VALUES (?, ?, ?, ?, ?)",
                rows,
            )

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
