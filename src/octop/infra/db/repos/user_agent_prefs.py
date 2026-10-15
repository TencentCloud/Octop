"""Per-user agent preferences — sidebar ordering + pinning (cross-device)."""

from __future__ import annotations

from dataclasses import dataclass

from octop.infra.db.pool import DatabasePool
from octop.infra.db.repos._base import DbRow, now_ts

# sort_order sentinel: the agent has never been manually ordered by this user.
UNORDERED = -1


@dataclass(frozen=True)
class UserAgentPrefRow:
    user_id: int
    agent_id: str
    pinned: bool
    sort_order: int
    updated_at: int

    @classmethod
    def from_row(cls, r: DbRow) -> UserAgentPrefRow:
        return cls(
            user_id=int(r["user_id"]),
            agent_id=str(r["agent_id"]),
            pinned=bool(int(r["pinned"] or 0)),
            sort_order=int(r["sort_order"] if r["sort_order"] is not None else UNORDERED),
            updated_at=int(r["updated_at"]),
        )


class UserAgentPrefRepo:
    def __init__(self, db: DatabasePool) -> None:
        self._db = db

    def get_prefs(self, user_id: int) -> dict[str, UserAgentPrefRow]:
        """All preference rows for one user, keyed by agent_id."""
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT user_id, agent_id, pinned, sort_order, updated_at "
                "FROM user_agent_prefs WHERE user_id = ?",
                (user_id,),
            ).fetchall()
        return {str(row["agent_id"]): UserAgentPrefRow.from_row(row) for row in rows}

    def set_pin(self, user_id: int, agent_id: str, pinned: bool) -> None:
        """Upsert the pinned flag; keep any existing manual sort_order."""
        ts = now_ts()
        with self._db.transaction() as conn:
            conn.execute(
                "INSERT INTO user_agent_prefs(user_id, agent_id, pinned, sort_order, updated_at) "
                "VALUES (?, ?, ?, -1, ?) "
                "ON CONFLICT(user_id, agent_id) DO UPDATE SET "
                "pinned = excluded.pinned, updated_at = excluded.updated_at",
                (user_id, agent_id, 1 if pinned else 0, ts),
            )

    def reorder(self, user_id: int, order: list[str]) -> None:
        """Persist a full manual sequence: sort_order = index, last write wins.

        Rows for agents missing from ``order`` are left untouched — the read
        path treats them as unordered (sort_order = -1) via their own row.
        Duplicate ids in ``order`` are collapsed to their first occurrence.
        """
        ts = now_ts()
        seen: set[str] = set()
        pairs: list[tuple[str, int]] = []
        for agent_id in order:
            if not agent_id or agent_id in seen:
                continue
            seen.add(agent_id)
            pairs.append((agent_id, len(pairs)))
        if not pairs:
            return
        with self._db.transaction() as conn:
            conn.executemany(
                "INSERT INTO user_agent_prefs(user_id, agent_id, pinned, sort_order, updated_at) "
                "VALUES (?, ?, 0, ?, ?) "
                "ON CONFLICT(user_id, agent_id) DO UPDATE SET "
                "sort_order = excluded.sort_order, updated_at = excluded.updated_at",
                [(user_id, agent_id, index, ts) for agent_id, index in pairs],
            )
