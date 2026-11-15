"""Recovery-code hashes (argon2id). Atomic single-spend on use."""

from __future__ import annotations

from dataclasses import dataclass

from octop.infra.db.pool import DatabasePool
from octop.infra.db.repos._base import DbRow, map_rows, now_ts


@dataclass(frozen=True)
class UserRecoveryCodeRow:
    id: int
    user_id: int
    code_hash: str
    used_at: int | None
    created_at: int

    @classmethod
    def from_row(cls, r: DbRow) -> UserRecoveryCodeRow:
        return cls(
            id=int(r["id"]),
            user_id=int(r["user_id"]),
            code_hash=str(r["code_hash"]),
            used_at=int(r["used_at"]) if r["used_at"] is not None else None,
            created_at=int(r["created_at"]),
        )


class UserRecoveryCodeRepo:
    def __init__(self, db: DatabasePool) -> None:
        self._db = db

    def list_unused(self, user_id: int) -> list[UserRecoveryCodeRow]:
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM user_recovery_codes "
                "WHERE user_id = ? AND used_at IS NULL ORDER BY id ASC",
                (user_id,),
            ).fetchall()
        return map_rows(rows, UserRecoveryCodeRow)

    def count_unused(self, user_id: int) -> int:
        with self._db.connect() as conn:
            return int(
                conn.execute(
                    "SELECT COUNT(*) FROM user_recovery_codes "
                    "WHERE user_id = ? AND used_at IS NULL",
                    (user_id,),
                ).fetchone()[0]
            )

    def replace_all(self, user_id: int, code_hashes: list[str]) -> None:
        """Delete unused codes and insert a fresh set (used codes stay as audit)."""
        ts = now_ts()
        with self._db.transaction() as conn:
            conn.execute(
                "DELETE FROM user_recovery_codes WHERE user_id = ? AND used_at IS NULL",
                (user_id,),
            )
            for code_hash in code_hashes:
                conn.execute(
                    "INSERT INTO user_recovery_codes(user_id, code_hash, used_at, created_at) "
                    "VALUES (?, ?, NULL, ?)",
                    (user_id, code_hash, ts),
                )

    def try_spend(self, code_id: int, user_id: int, *, now: int | None = None) -> bool:
        """Atomically mark a code used. Returns False if already spent or missing."""
        ts = now if now is not None else now_ts()
        with self._db.transaction() as conn:
            cur = conn.execute(
                "UPDATE user_recovery_codes SET used_at = ? "
                "WHERE id = ? AND user_id = ? AND used_at IS NULL",
                (ts, code_id, user_id),
            )
            return int(cur.rowcount or 0) > 0

    def delete_all_for_user(self, user_id: int) -> int:
        with self._db.transaction() as conn:
            cur = conn.execute(
                "DELETE FROM user_recovery_codes WHERE user_id = ?",
                (user_id,),
            )
            return int(cur.rowcount or 0)
