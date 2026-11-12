"""TOTP secret rows (one pending/verified secret per user)."""

from __future__ import annotations

from dataclasses import dataclass

from octop.infra.db.pool import DatabasePool
from octop.infra.db.repos._base import DbRow, insert_returning_id, now_ts


@dataclass(frozen=True)
class UserTotpRow:
    id: int
    user_id: int
    secret_enc: bytes
    verified_at: int | None
    pending_expires_at: int | None
    last_used_step: int | None
    created_at: int
    updated_at: int

    @classmethod
    def from_row(cls, r: DbRow) -> UserTotpRow:
        raw = r["secret_enc"]
        secret = bytes(raw) if not isinstance(raw, bytes) else raw
        return cls(
            id=int(r["id"]),
            user_id=int(r["user_id"]),
            secret_enc=secret,
            verified_at=int(r["verified_at"]) if r["verified_at"] is not None else None,
            pending_expires_at=(
                int(r["pending_expires_at"]) if r["pending_expires_at"] is not None else None
            ),
            last_used_step=int(r["last_used_step"]) if r["last_used_step"] is not None else None,
            created_at=int(r["created_at"]),
            updated_at=int(r["updated_at"]),
        )

    @property
    def is_verified(self) -> bool:
        return self.verified_at is not None


class UserTotpRepo:
    def __init__(self, db: DatabasePool) -> None:
        self._db = db

    def get_by_user(self, user_id: int) -> UserTotpRow | None:
        with self._db.connect() as conn:
            r = conn.execute(
                "SELECT * FROM user_totp WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        return UserTotpRow.from_row(r) if r else None

    def upsert_pending(
        self,
        user_id: int,
        *,
        secret_enc: bytes,
        pending_expires_at: int,
    ) -> UserTotpRow:
        ts = now_ts()
        with self._db.transaction() as conn:
            existing = conn.execute(
                "SELECT id FROM user_totp WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            if existing is None:
                insert_returning_id(
                    conn,
                    "INSERT INTO user_totp(user_id, secret_enc, verified_at, "
                    "pending_expires_at, last_used_step, created_at, updated_at) "
                    "VALUES (?, ?, NULL, ?, NULL, ?, ?)",
                    (user_id, secret_enc, pending_expires_at, ts, ts),
                )
            else:
                conn.execute(
                    "UPDATE user_totp SET secret_enc = ?, verified_at = NULL, "
                    "pending_expires_at = ?, last_used_step = NULL, updated_at = ? "
                    "WHERE user_id = ?",
                    (secret_enc, pending_expires_at, ts, user_id),
                )
        row = self.get_by_user(user_id)
        assert row is not None
        return row

    def confirm(self, user_id: int, *, verified_at: int | None = None) -> UserTotpRow | None:
        ts = verified_at if verified_at is not None else now_ts()
        with self._db.transaction() as conn:
            conn.execute(
                "UPDATE user_totp SET verified_at = ?, pending_expires_at = NULL, "
                "updated_at = ? WHERE user_id = ? AND verified_at IS NULL",
                (ts, ts, user_id),
            )
        return self.get_by_user(user_id)

    def set_last_used_step(self, user_id: int, step: int) -> bool:
        """Set ``last_used_step`` when it is NULL or strictly less than ``step``."""
        ts = now_ts()
        with self._db.transaction() as conn:
            cur = conn.execute(
                "UPDATE user_totp SET last_used_step = ?, updated_at = ? "
                "WHERE user_id = ? AND (last_used_step IS NULL OR last_used_step < ?)",
                (step, ts, user_id, step),
            )
            return int(cur.rowcount or 0) > 0

    def delete(self, user_id: int) -> bool:
        with self._db.transaction() as conn:
            cur = conn.execute("DELETE FROM user_totp WHERE user_id = ?", (user_id,))
            return int(cur.rowcount or 0) > 0

    def prune_expired_pending(self, *, now: int | None = None) -> int:
        ts = now if now is not None else now_ts()
        with self._db.transaction() as conn:
            cur = conn.execute(
                "DELETE FROM user_totp WHERE verified_at IS NULL "
                "AND pending_expires_at IS NOT NULL AND pending_expires_at < ?",
                (ts,),
            )
            return int(cur.rowcount or 0)
