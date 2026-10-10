"""Coding sessions repository — persistent Code Console sessions (S3)."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

from octop.infra.db.pool import DatabasePool
from octop.infra.db.repos._base import DbRow

# Session lifecycle statuses.
STATUS_READY = "ready"
STATUS_RUNNING = "running"
STATUS_AWAITING = "awaiting_approval"
STATUS_IDLE = "idle"
STATUS_INTERRUPTED = "interrupted"
STATUS_CLOSED = "closed"

# Statuses that cannot survive a process restart: the in-memory ACP binding
# behind them is gone, so they are reconciled to ``interrupted`` on boot.
ACTIVE_STATUSES = (STATUS_RUNNING, STATUS_AWAITING)

_SESSION_COLS = (
    "session_id, user_id, runner, cwd, status, turns, acp_session_id, "
    "project_id, repository_id, branch, worktree_id, runtime_id, "
    "isolation_level, permission_policy, model_profile, trigger, token_usage, "
    "meta_json, created_at, updated_at, closed_at"
)


def _decode_meta(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        val = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return val if isinstance(val, dict) else {}


@dataclass(frozen=True)
class CodingSessionRow:
    session_id: str
    user_id: int
    runner: str
    cwd: str
    status: str
    turns: int
    acp_session_id: str | None
    project_id: str | None
    repository_id: str | None
    branch: str | None
    worktree_id: str | None
    runtime_id: str | None
    isolation_level: str | None
    permission_policy: str | None
    model_profile: str | None
    trigger: str
    token_usage: int
    meta: dict[str, Any] = field(default_factory=dict)
    created_at: float = 0.0
    updated_at: float = 0.0
    closed_at: float | None = None

    @classmethod
    def from_row(cls, r: DbRow) -> CodingSessionRow:
        return cls(
            session_id=str(r["session_id"]),
            user_id=int(r["user_id"]),
            runner=str(r["runner"]),
            cwd=str(r["cwd"]),
            status=str(r["status"]),
            turns=int(r["turns"]),
            acp_session_id=r["acp_session_id"],
            project_id=r["project_id"],
            repository_id=r["repository_id"],
            branch=r["branch"],
            worktree_id=r["worktree_id"],
            runtime_id=r["runtime_id"],
            isolation_level=r["isolation_level"],
            permission_policy=r["permission_policy"],
            model_profile=r["model_profile"],
            trigger=str(r["trigger"]),
            token_usage=int(r["token_usage"]),
            meta=_decode_meta(r["meta_json"]),
            created_at=float(r["created_at"]),
            updated_at=float(r["updated_at"]),
            closed_at=float(r["closed_at"]) if r["closed_at"] is not None else None,
        )


class CodingSessionRepo:
    def __init__(self, db: DatabasePool) -> None:
        self._db = db

    def create(
        self,
        *,
        session_id: str,
        user_id: int,
        runner: str,
        cwd: str,
        status: str = STATUS_READY,
    ) -> CodingSessionRow:
        now = time.time()
        with self._db.transaction() as conn:
            conn.execute(
                "INSERT INTO coding_sessions("
                "session_id, user_id, runner, cwd, status, turns, "
                "trigger, meta_json, created_at, updated_at"
                ") VALUES (?, ?, ?, ?, ?, 0, 'interactive', '{}', ?, ?)",
                (session_id, user_id, runner, cwd, status, now, now),
            )
        row = self.get(session_id)
        assert row is not None
        return row

    def get(self, session_id: str) -> CodingSessionRow | None:
        with self._db.connect() as conn:
            r = conn.execute(
                f"SELECT {_SESSION_COLS} FROM coding_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        return CodingSessionRow.from_row(r) if r else None

    def list_visible(
        self,
        *,
        user_id: int,
        is_admin: bool,
        include_closed: bool = False,
    ) -> list[CodingSessionRow]:
        sql = f"SELECT {_SESSION_COLS} FROM coding_sessions"
        params: list[Any] = []
        where: list[str] = []
        if not is_admin:
            where.append("user_id = ?")
            params.append(user_id)
        if not include_closed:
            where.append("status != ?")
            params.append(STATUS_CLOSED)
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY created_at DESC"
        with self._db.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [CodingSessionRow.from_row(r) for r in rows]

    def update_status(self, session_id: str, status: str) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                "UPDATE coding_sessions SET status = ?, updated_at = ? WHERE session_id = ?",
                (status, time.time(), session_id),
            )

    def bind_acp(self, session_id: str, acp_session_id: str | None) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                "UPDATE coding_sessions SET acp_session_id = ?, updated_at = ? "
                "WHERE session_id = ?",
                (acp_session_id, time.time(), session_id),
            )

    def bump_turns(self, session_id: str) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                "UPDATE coding_sessions SET turns = turns + 1, updated_at = ? WHERE session_id = ?",
                (time.time(), session_id),
            )

    def set_meta(self, session_id: str, patch: dict[str, Any]) -> None:
        """Merge ``patch`` into the session's ``meta_json`` blob."""
        row = self.get(session_id)
        meta = dict(row.meta if row is not None else {})
        meta.update(patch)
        with self._db.transaction() as conn:
            conn.execute(
                "UPDATE coding_sessions SET meta_json = ?, updated_at = ? WHERE session_id = ?",
                (json.dumps(meta, ensure_ascii=False), time.time(), session_id),
            )

    def close(self, session_id: str) -> None:
        now = time.time()
        with self._db.transaction() as conn:
            conn.execute(
                "UPDATE coding_sessions SET status = ?, closed_at = ?, updated_at = ? "
                "WHERE session_id = ?",
                (STATUS_CLOSED, now, now, session_id),
            )

    def mark_interrupted_pending(self) -> int:
        """Reconcile active sessions left over by a process restart/crash.

        Returns the number of sessions marked interrupted.
        """
        with self._db.transaction() as conn:
            cur = conn.execute(
                "UPDATE coding_sessions SET status = ?, updated_at = ? WHERE status IN (?, ?)",
                (STATUS_INTERRUPTED, time.time(), *ACTIVE_STATUSES),
            )
            return int(cur.rowcount or 0)
