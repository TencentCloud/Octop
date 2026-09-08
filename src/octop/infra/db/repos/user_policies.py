"""Per-user policy rows — one named policy per user."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from octop.infra.db.pool import DatabasePool
from octop.infra.db.repos._base import DbRow, now_ts, sql_in_placeholders
from octop.infra.utils.ulid import new_ulid


@dataclass(frozen=True)
class UserPolicyRow:
    pk: int
    policy_id: str
    user_id: int
    name: str
    enabled: bool
    value: str
    created_at: int
    updated_at: int

    @classmethod
    def from_row(cls, row: DbRow) -> UserPolicyRow:
        return cls(
            pk=int(row["id"]),
            policy_id=str(row["policy_id"]),
            user_id=int(row["user_id"]),
            name=str(row["name"]),
            enabled=bool(row["enabled"]),
            value=str(row["value"] or ""),
            created_at=int(row["created_at"]),
            updated_at=int(row["updated_at"]),
        )


class UserPolicyRepo:
    def __init__(self, db: DatabasePool) -> None:
        self._db = db

    def get(self, user_id: int, name: str) -> UserPolicyRow | None:
        with self._db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM user_policies WHERE user_id = ? AND name = ?",
                (user_id, name),
            ).fetchone()
        return UserPolicyRow.from_row(row) if row is not None else None

    def list_for_user(self, user_id: int) -> list[UserPolicyRow]:
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM user_policies WHERE user_id = ? ORDER BY name",
                (user_id,),
            ).fetchall()
        return [UserPolicyRow.from_row(row) for row in rows]

    def list_by_user_ids(self, user_ids: list[int]) -> dict[int, list[UserPolicyRow]]:
        if not user_ids:
            return {}
        placeholders = sql_in_placeholders(len(user_ids))
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM user_policies "
                f"WHERE user_id IN ({placeholders}) ORDER BY user_id, name",
                tuple(user_ids),
            ).fetchall()
        out: dict[int, list[UserPolicyRow]] = {}
        for row in rows:
            mapped = UserPolicyRow.from_row(row)
            out.setdefault(mapped.user_id, []).append(mapped)
        return out

    def enabled_values(self, user_id: int) -> dict[str, str]:
        return _enabled_values(self.list_for_user(user_id))

    def enabled_values_by_user_ids(self, user_ids: list[int]) -> dict[int, dict[str, str]]:
        grouped = self.list_by_user_ids(user_ids)
        return {uid: _enabled_values(rows) for uid, rows in grouped.items()}

    def set(self, user_id: int, name: str, value: str | None) -> None:
        self.merge(user_id, {name: value})

    def merge(self, user_id: int, updates: Mapping[str, str | None]) -> None:
        if not updates:
            return
        ts = now_ts()
        with self._db.transaction() as conn:
            for name, value in updates.items():
                if value is None:
                    conn.execute(
                        """
                        UPDATE user_policies
                        SET enabled = 0, updated_at = ?
                        WHERE user_id = ? AND name = ?
                        """,
                        (ts, user_id, name),
                    )
                    continue
                conn.execute(
                    """
                    INSERT INTO user_policies(
                      policy_id, user_id, name, enabled, value, created_at, updated_at
                    )
                    VALUES (?, ?, ?, 1, ?, ?, ?)
                    ON CONFLICT(user_id, name) DO UPDATE SET
                      enabled = 1,
                      value = excluded.value,
                      updated_at = excluded.updated_at
                    """,
                    (new_ulid(), user_id, name, value, ts, ts),
                )


def _enabled_values(rows: list[UserPolicyRow]) -> dict[str, str]:
    return {row.name: row.value for row in rows if row.enabled and row.value}
