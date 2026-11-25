"""Membership of users in user groups."""

from __future__ import annotations

from octop.infra.db.pool import DatabasePool
from octop.infra.db.repos._base import now_ts


class UserGroupMemberRepo:
    def __init__(self, db: DatabasePool) -> None:
        self._db = db

    def group_ids_for_user(self, user_id: int) -> set[str]:
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT user_group_id FROM user_group_member WHERE user_id = ?",
                (user_id,),
            ).fetchall()
        return {str(row["user_group_id"]) for row in rows}

    def user_ids_for_group(self, user_group_id: str) -> list[int]:
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT user_id FROM user_group_member WHERE user_group_id = ? ORDER BY user_id",
                (user_group_id,),
            ).fetchall()
        return [int(row["user_id"]) for row in rows]

    def user_ids_by_group(self) -> dict[str, list[int]]:
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT user_group_id, user_id FROM user_group_member ORDER BY user_id"
            ).fetchall()
        grouped: dict[str, list[int]] = {}
        for row in rows:
            grouped.setdefault(str(row["user_group_id"]), []).append(int(row["user_id"]))
        return grouped

    def counts_by_group(self) -> dict[str, int]:
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT user_group_id, COUNT(*) AS n FROM user_group_member GROUP BY user_group_id"
            ).fetchall()
        return {str(row["user_group_id"]): int(row["n"]) for row in rows}

    def add(self, user_group_id: str, user_id: int) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                "INSERT INTO user_group_member(user_group_id, user_id, created_at) VALUES (?, ?, ?)"
                " ON CONFLICT(user_group_id, user_id) DO NOTHING",
                (user_group_id, user_id, now_ts()),
            )

    def remove(self, user_group_id: str, user_id: int) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                "DELETE FROM user_group_member WHERE user_group_id = ? AND user_id = ?",
                (user_group_id, user_id),
            )

    def replace(self, user_group_id: str, user_ids: list[int]) -> None:
        ts = now_ts()
        with self._db.transaction() as conn:
            conn.execute(
                "DELETE FROM user_group_member WHERE user_group_id = ?",
                (user_group_id,),
            )
            for user_id in user_ids:
                conn.execute(
                    "INSERT INTO user_group_member(user_group_id, user_id, created_at)"
                    " VALUES (?, ?, ?)",
                    (user_group_id, user_id, ts),
                )
