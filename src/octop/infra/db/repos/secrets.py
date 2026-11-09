"""Secrets table access."""

from __future__ import annotations

from collections.abc import Callable

from octop.infra.db.pool import DatabasePool
from octop.infra.db.repos._base import now_ts


class SecretRepo:
    def __init__(self, db: DatabasePool):
        self._db = db

    def get(self, k: str) -> bytes | None:
        with self._db.connect() as conn:
            r = conn.execute("SELECT v FROM secrets WHERE k = ?", (k,)).fetchone()
        return bytes(r["v"]) if r else None

    def get_or_create(self, k: str, factory: Callable[[], bytes]) -> bytes:
        existing = self.get(k)
        if existing is not None:
            return existing
        value = factory()
        with self._db.transaction() as conn:
            # Check again inside transaction to avoid race
            r = conn.execute("SELECT v FROM secrets WHERE k = ?", (k,)).fetchone()
            if r is not None:
                return bytes(r["v"])
            conn.execute(
                "INSERT INTO secrets(k, v, created_at) VALUES (?, ?, ?)",
                (k, value, now_ts()),
            )
        return value

    def put(self, k: str, value: bytes) -> None:
        now = now_ts()
        with self._db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO secrets(k, v, created_at) VALUES (?, ?, ?)
                ON CONFLICT(k) DO UPDATE SET v = excluded.v, rotated_at = ?
                """,
                (k, value, now, now),
            )

    def put_if_absent(self, k: str, value: bytes) -> bool:
        """Insert ``value`` when ``k`` is missing. Return whether this call inserted it."""
        with self._db.transaction() as conn:
            cursor = conn.execute(
                """
                INSERT INTO secrets(k, v, created_at) VALUES (?, ?, ?)
                ON CONFLICT(k) DO NOTHING
                """,
                (k, value, now_ts()),
            )
        return int(getattr(cursor, "rowcount", 0) or 0) == 1

    def delete(self, k: str) -> bool:
        with self._db.transaction() as conn:
            row = conn.execute("SELECT 1 FROM secrets WHERE k = ?", (k,)).fetchone()
            if row is None:
                return False
            conn.execute("DELETE FROM secrets WHERE k = ?", (k,))
        return True

    def rotate(self, k: str, new_value: bytes) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                "UPDATE secrets SET v = ?, rotated_at = ? WHERE k = ?",
                (new_value, now_ts(), k),
            )
