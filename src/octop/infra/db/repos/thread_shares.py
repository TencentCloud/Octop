"""Read-only conversation share links."""

from __future__ import annotations

import secrets
import sqlite3
from dataclasses import dataclass

from octop.infra.db.pool import DatabasePool
from octop.infra.db.repos._base import DbRow, now_ts

try:
    from psycopg import errors as pg_errors
except ImportError:  # pragma: no cover - postgres driver is optional in unit tests
    pg_errors = None  # type: ignore[assignment]


def _is_unique_violation(exc: BaseException) -> bool:
    if isinstance(exc, sqlite3.IntegrityError):
        return "unique" in str(exc).lower()
    return pg_errors is not None and isinstance(exc, pg_errors.UniqueViolation)


@dataclass(frozen=True)
class ThreadShareRow:
    id: int
    share_id: str
    thread_id: str
    agent_id: str
    created_by: int
    created_at: int
    revoked_at: int | None

    @classmethod
    def from_row(cls, row: DbRow) -> ThreadShareRow:
        revoked = row["revoked_at"]
        return cls(
            id=int(row["id"]),
            share_id=str(row["share_id"]),
            thread_id=str(row["thread_id"]),
            agent_id=str(row["agent_id"]),
            created_by=int(row["created_by"]),
            created_at=int(row["created_at"]),
            revoked_at=int(revoked) if revoked is not None else None,
        )

    @property
    def active(self) -> bool:
        return self.revoked_at is None


class ThreadShareRepo:
    """One live link per thread. Rotating revokes the previous token."""

    def __init__(self, db: DatabasePool) -> None:
        self._db = db

    def get_active_by_token(self, share_id: str) -> ThreadShareRow | None:
        with self._db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM thread_shares WHERE share_id = ? AND revoked_at IS NULL",
                (share_id,),
            ).fetchone()
        return ThreadShareRow.from_row(row) if row else None

    def get_active_by_thread(self, thread_id: str) -> ThreadShareRow | None:
        with self._db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM thread_shares WHERE thread_id = ? AND revoked_at IS NULL",
                (thread_id,),
            ).fetchone()
        return ThreadShareRow.from_row(row) if row else None

    def ensure(
        self,
        *,
        thread_id: str,
        agent_id: str,
        created_by: int,
    ) -> ThreadShareRow:
        existing = self.get_active_by_thread(thread_id)
        if existing is not None:
            return existing
        return self._insert(thread_id=thread_id, agent_id=agent_id, created_by=created_by)

    def rotate(
        self,
        *,
        thread_id: str,
        agent_id: str,
        created_by: int,
    ) -> ThreadShareRow:
        last_error: BaseException | None = None
        for _ in range(2):
            try:
                return self._revoke_and_insert(
                    thread_id=thread_id,
                    agent_id=agent_id,
                    created_by=created_by,
                )
            except Exception as exc:
                if not _is_unique_violation(exc):
                    raise
                last_error = exc
        assert last_error is not None
        raise last_error

    def revoke(self, thread_id: str) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                "UPDATE thread_shares SET revoked_at = ? "
                "WHERE thread_id = ? AND revoked_at IS NULL",
                (now_ts(), thread_id),
            )

    def _insert(
        self,
        *,
        thread_id: str,
        agent_id: str,
        created_by: int,
    ) -> ThreadShareRow:
        last_error: BaseException | None = None
        for _ in range(2):
            token = secrets.token_urlsafe(24)
            try:
                self._insert_token(
                    token=token,
                    thread_id=thread_id,
                    agent_id=agent_id,
                    created_by=created_by,
                    revoke_first=False,
                )
            except Exception as exc:
                if not _is_unique_violation(exc):
                    raise
                last_error = exc
                active = self.get_active_by_thread(thread_id)
                if active is not None:
                    return active
                continue
            row = self.get_active_by_token(token)
            if row is not None:
                return row
        assert last_error is not None
        raise last_error

    def _revoke_and_insert(
        self,
        *,
        thread_id: str,
        agent_id: str,
        created_by: int,
    ) -> ThreadShareRow:
        token = secrets.token_urlsafe(24)
        self._insert_token(
            token=token,
            thread_id=thread_id,
            agent_id=agent_id,
            created_by=created_by,
            revoke_first=True,
        )
        row = self.get_active_by_token(token)
        if row is None:
            raise RuntimeError("share link was not stored")
        return row

    def _insert_token(
        self,
        *,
        token: str,
        thread_id: str,
        agent_id: str,
        created_by: int,
        revoke_first: bool,
    ) -> None:
        ts = now_ts()
        with self._db.transaction() as conn:
            if revoke_first:
                conn.execute(
                    "UPDATE thread_shares SET revoked_at = ? "
                    "WHERE thread_id = ? AND revoked_at IS NULL",
                    (ts, thread_id),
                )
            conn.execute(
                "INSERT INTO thread_shares("
                "share_id, thread_id, agent_id, created_by, created_at"
                ") VALUES (?, ?, ?, ?, ?)",
                (token, thread_id, agent_id, created_by, ts),
            )
