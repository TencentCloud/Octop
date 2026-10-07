"""Coding worktrees repository — git worktree records (S5)."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

from octop.infra.db.pool import DatabasePool
from octop.infra.db.repos._base import DbRow

WORKTREE_COLS = (
    "worktree_id, repository_id, session_id, project_id, branch, path, "
    "status, meta_json, created_at, updated_at"
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
class WorktreeRow:
    worktree_id: str
    repository_id: str | None
    session_id: str
    project_id: str | None
    branch: str
    path: str
    status: str
    meta: dict[str, Any] = field(default_factory=dict)
    created_at: float = 0.0
    updated_at: float = 0.0

    @classmethod
    def from_row(cls, r: DbRow) -> WorktreeRow:
        return cls(
            worktree_id=str(r["worktree_id"]),
            repository_id=r["repository_id"],
            session_id=str(r["session_id"]),
            project_id=r["project_id"],
            branch=str(r["branch"]),
            path=str(r["path"]),
            status=str(r["status"]),
            meta=_decode_meta(r["meta_json"]),
            created_at=float(r["created_at"]),
            updated_at=float(r["updated_at"]),
        )


class WorktreeRepo:
    def __init__(self, db: DatabasePool) -> None:
        self._db = db

    def create(
        self,
        *,
        worktree_id: str,
        session_id: str,
        repository_id: str | None = None,
        project_id: str | None = None,
        branch: str = "",
        path: str = "",
        status: str = "creating",
    ) -> WorktreeRow:
        now = time.time()
        with self._db.transaction() as conn:
            conn.execute(
                "INSERT INTO coding_worktrees("
                "worktree_id, repository_id, session_id, project_id, branch, path, "
                "status, meta_json, created_at, updated_at"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, '{}', ?, ?)",
                (
                    worktree_id,
                    repository_id,
                    session_id,
                    project_id,
                    branch,
                    path,
                    status,
                    now,
                    now,
                ),
            )
        row = self.get(worktree_id)
        assert row is not None
        return row

    def get(self, worktree_id: str) -> WorktreeRow | None:
        with self._db.connect() as conn:
            r = conn.execute(
                f"SELECT {WORKTREE_COLS} FROM coding_worktrees WHERE worktree_id = ?",
                (worktree_id,),
            ).fetchone()
        return WorktreeRow.from_row(r) if r else None

    def by_session(self, session_id: str) -> WorktreeRow | None:
        with self._db.connect() as conn:
            r = conn.execute(
                f"SELECT {WORKTREE_COLS} FROM coding_worktrees WHERE session_id = ? "
                "ORDER BY created_at DESC LIMIT 1",
                (session_id,),
            ).fetchone()
        return WorktreeRow.from_row(r) if r else None

    def update_status(self, worktree_id: str, status: str) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                "UPDATE coding_worktrees SET status = ?, updated_at = ? WHERE worktree_id = ?",
                (status, time.time(), worktree_id),
            )

    def set_path(self, worktree_id: str, path: str) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                "UPDATE coding_worktrees SET path = ?, status = 'ready', "
                "updated_at = ? WHERE worktree_id = ?",
                (path, time.time(), worktree_id),
            )

    def remove(self, worktree_id: str) -> None:
        with self._db.transaction() as conn:
            conn.execute("DELETE FROM coding_worktrees WHERE worktree_id = ?", (worktree_id,))
