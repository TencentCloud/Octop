"""Project rows — ``projects`` and ``project_members``.

Resource-table convention (see AGENTS.md §7): every table carries an integer
surrogate PK (``id``) plus a public string id (``project_id``). Foreign keys and
callers use the **string** id; the dataclasses expose the integer as ``pk`` for
the rare case a join needs it.

Task rows and the project timeline live in ``repos/project_tasks.py``. Keeping
roles and statuses as module constants mirrors the value lists in
``018_projects.sql``; the state machine and the permission matrix live in the
service layer, so this module stays SQL-only.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from octop.infra.db.pool import DatabasePool
from octop.infra.db.repos._base import (
    UNSET,
    DbRow,
    map_rows,
    now_ts,
    optional_updates,
    sql_in_placeholders,
)
from octop.infra.utils.ulid import new_short_id

PROJECT_ROLES: tuple[str, ...] = ("owner", "admin", "member", "viewer")

PROJECT_STATUSES: tuple[str, ...] = (
    "draft",
    "active",
    "paused",
    "completed",
    "cancelled",
    "archived",
)

# ``project_members.subject_type`` — who a membership row points at.
MEMBER_SUBJECT_USER = "user"
MEMBER_SUBJECT_AGENT = "agent"
MEMBER_SUBJECT_TEAM = "team"
MEMBER_SUBJECT_TYPES: tuple[str, ...] = (
    MEMBER_SUBJECT_USER,
    MEMBER_SUBJECT_AGENT,
    MEMBER_SUBJECT_TEAM,
)


def project_memory_namespace(project_id: str) -> str:
    """Memory namespace owned by a project (see plan D2: one namespace per project)."""
    return f"project_{project_id}"


# ── projects ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ProjectRow:
    id: str
    pk: int
    name: str
    goal: str
    status: str
    owner_user_id: int
    memory_namespace: str
    inject_version: int
    kb_id: str | None
    start_at: int | None
    due_at: int | None
    created_at: int
    updated_at: int

    @classmethod
    def from_row(cls, r: DbRow) -> ProjectRow:
        return cls(
            id=str(r["project_id"]),
            pk=int(r["id"]),
            name=str(r["name"]),
            goal=str(r["goal"] or ""),
            status=str(r["status"]),
            owner_user_id=int(r["owner_user_id"]),
            memory_namespace=str(r["memory_namespace"]),
            inject_version=int(r["inject_version"]),
            kb_id=(str(r["kb_id"]) if r["kb_id"] is not None else None),
            start_at=(int(r["start_at"]) if r["start_at"] is not None else None),
            due_at=(int(r["due_at"]) if r["due_at"] is not None else None),
            created_at=int(r["created_at"]),
            updated_at=int(r["updated_at"]),
        )


@dataclass(frozen=True)
class ThreadProjectRef:
    """The project a conversation was dispatched from (scalar, one per thread)."""

    project_id: str
    project_name: str


class ProjectRepo:
    def __init__(self, db: DatabasePool) -> None:
        self._db = db

    def _allocate_id(self) -> str:
        for _ in range(16):
            project_id = new_short_id()
            if self.get(project_id) is None:
                return project_id
        raise RuntimeError("failed to allocate unique project id")

    def create(
        self,
        *,
        owner_user_id: int,
        name: str,
        goal: str = "",
        status: str = "draft",
        kb_id: str | None = None,
        start_at: int | None = None,
        due_at: int | None = None,
    ) -> ProjectRow:
        project_id = self._allocate_id()
        ts = now_ts()
        with self._db.transaction() as conn:
            conn.execute(
                "INSERT INTO projects("
                "project_id, name, goal, status, owner_user_id, memory_namespace, "
                "inject_version, kb_id, start_at, due_at, created_at, updated_at"
                ") VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?)",
                (
                    project_id,
                    name,
                    goal,
                    status,
                    owner_user_id,
                    project_memory_namespace(project_id),
                    kb_id,
                    start_at,
                    due_at,
                    ts,
                    ts,
                ),
            )
        row = self.get(project_id)
        if row is None:
            raise RuntimeError(f"project insert failed: {project_id}")
        return row

    def get(self, project_id: str) -> ProjectRow | None:
        with self._db.connect() as conn:
            r = conn.execute(
                "SELECT * FROM projects WHERE project_id = ?", (project_id,)
            ).fetchone()
        return ProjectRow.from_row(r) if r else None

    def list_by_owner(self, owner_user_id: int) -> list[ProjectRow]:
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM projects WHERE owner_user_id = ? ORDER BY updated_at DESC",
                (owner_user_id,),
            ).fetchall()
        return map_rows(rows, ProjectRow)

    def list_for_user(self, user_id: int) -> list[ProjectRow]:
        """Projects the user owns **or** is a member of.

        Membership is keyed on the string subject id, so a user member row is
        ``subject_type='user'`` + ``subject_id=str(user_id)``.
        """
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT p.* FROM projects p "
                "WHERE p.owner_user_id = ? "
                "   OR EXISTS ("
                "        SELECT 1 FROM project_members m "
                "        WHERE m.project_id = p.project_id "
                "          AND m.subject_type = ? AND m.subject_id = ?"
                "      ) "
                "ORDER BY p.updated_at DESC",
                (user_id, MEMBER_SUBJECT_USER, str(user_id)),
            ).fetchall()
        return map_rows(rows, ProjectRow)

    def projects_by_thread(self, thread_ids: Iterable[str]) -> dict[str, ThreadProjectRef]:
        """Reverse lookup: the project each conversation was dispatched from.

        The single thread→project entry point (PLAN.md §4). The data source is
        ``project_tasks.thread_id`` — written only by task dispatch — so a
        conversation the user opened by hand is never a project chat.

        A thread can carry tasks from several projects; the most recently
        updated task wins (``updated_at DESC, task_id DESC``), which keeps every
        value a scalar. One SQL statement, no status/membership filtering: the
        caller has already scoped the thread ids to the current user.
        """
        ids = [str(t) for t in thread_ids]
        if not ids:
            return {}
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT t.thread_id, t.project_id, p.name AS project_name "
                "FROM project_tasks t "
                "JOIN projects p ON p.project_id = t.project_id "
                f"WHERE t.thread_id IN ({sql_in_placeholders(len(ids))}) "
                "ORDER BY t.thread_id ASC, t.updated_at DESC, t.task_id DESC",
                ids,
            ).fetchall()
        refs: dict[str, ThreadProjectRef] = {}
        for r in rows:
            # Rows arrive best-first per thread; keep the first one only.
            refs.setdefault(
                str(r["thread_id"]),
                ThreadProjectRef(
                    project_id=str(r["project_id"]),
                    project_name=str(r["project_name"]),
                ),
            )
        return refs

    def update(
        self,
        project_id: str,
        *,
        name: object = UNSET,
        goal: object = UNSET,
        status: object = UNSET,
        start_at: object = UNSET,
        due_at: object = UNSET,
    ) -> ProjectRow | None:
        """Patch mutable fields; omit a keyword to leave it untouched.

        Pass an explicit ``None`` for ``start_at`` / ``due_at`` to clear it.
        ``kb_id`` is not patchable here — use :meth:`set_kb_id` so the
        compensating-delete flow in the service stays the only writer.
        """
        clauses, params = optional_updates(
            [
                ("name", name),
                ("goal", goal),
                ("status", status),
                ("start_at", start_at),
                ("due_at", due_at),
            ]
        )
        if not clauses:
            return self.get(project_id)
        clauses.append("updated_at = ?")
        params.append(now_ts())
        params.append(project_id)
        with self._db.transaction() as conn:
            conn.execute(
                f"UPDATE projects SET {', '.join(clauses)} WHERE project_id = ?",
                params,
            )
        return self.get(project_id)

    def set_kb_id(self, project_id: str, kb_id: str | None) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                "UPDATE projects SET kb_id = ?, updated_at = ? WHERE project_id = ?",
                (kb_id, now_ts(), project_id),
            )

    def bump_inject_version(self, project_id: str) -> int:
        """Advance the memory-injection revision and return the new value."""
        with self._db.transaction() as conn:
            conn.execute(
                "UPDATE projects SET inject_version = inject_version + 1, updated_at = ? "
                "WHERE project_id = ?",
                (now_ts(), project_id),
            )
        row = self.get(project_id)
        return row.inject_version if row else 0

    def delete(self, project_id: str) -> bool:
        """Delete a project. Child rows cascade via their foreign keys."""
        with self._db.transaction() as conn:
            cur = conn.execute("DELETE FROM projects WHERE project_id = ?", (project_id,))
        return bool(cur.rowcount)


# ── project_members ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ProjectMemberRow:
    pk: int
    project_id: str
    subject_type: str
    subject_id: str
    user_id: int | None
    role: str
    created_at: int

    @classmethod
    def from_row(cls, r: DbRow) -> ProjectMemberRow:
        return cls(
            pk=int(r["id"]),
            project_id=str(r["project_id"]),
            subject_type=str(r["subject_type"]),
            subject_id=str(r["subject_id"]),
            user_id=(int(r["user_id"]) if r["user_id"] is not None else None),
            role=str(r["role"]),
            created_at=int(r["created_at"]),
        )


class ProjectMemberRepo:
    def __init__(self, db: DatabasePool) -> None:
        self._db = db

    def add(
        self,
        *,
        project_id: str,
        subject_type: str,
        subject_id: str,
        role: str = "member",
        user_id: int | None = None,
    ) -> ProjectMemberRow:
        """Insert or re-role a member.

        ``UNIQUE(project_id, subject_type, subject_id)`` means adding an existing
        subject updates its role instead of failing — that keeps the "invite
        again to change role" path idempotent.
        """
        ts = now_ts()
        if user_id is None and subject_type == MEMBER_SUBJECT_USER:
            user_id = int(subject_id)
        with self._db.transaction() as conn:
            conn.execute(
                "INSERT INTO project_members("
                "project_id, subject_type, subject_id, user_id, role, created_at"
                ") VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(project_id, subject_type, subject_id) "
                "DO UPDATE SET role = excluded.role, user_id = excluded.user_id",
                (project_id, subject_type, subject_id, user_id, role, ts),
            )
        row = self.get(project_id, subject_type, subject_id)
        if row is None:
            raise RuntimeError(f"project member insert failed: {project_id}/{subject_id}")
        return row

    def get(self, project_id: str, subject_type: str, subject_id: str) -> ProjectMemberRow | None:
        with self._db.connect() as conn:
            r = conn.execute(
                "SELECT * FROM project_members "
                "WHERE project_id = ? AND subject_type = ? AND subject_id = ?",
                (project_id, subject_type, subject_id),
            ).fetchone()
        return ProjectMemberRow.from_row(r) if r else None

    def role_of(self, project_id: str, subject_type: str, subject_id: str) -> str | None:
        row = self.get(project_id, subject_type, subject_id)
        return row.role if row else None

    def list_by_project(self, project_id: str) -> list[ProjectMemberRow]:
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM project_members WHERE project_id = ? ORDER BY created_at, id",
                (project_id,),
            ).fetchall()
        return map_rows(rows, ProjectMemberRow)

    def count(self, project_id: str) -> int:
        with self._db.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM project_members WHERE project_id = ?",
                (project_id,),
            ).fetchone()
        return int(row["c"]) if row else 0

    def list_project_ids_for_subject(self, subject_type: str, subject_id: str) -> list[str]:
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT project_id FROM project_members WHERE subject_type = ? AND subject_id = ?",
                (subject_type, subject_id),
            ).fetchall()
        return [str(r["project_id"]) for r in rows]

    def remove(self, project_id: str, subject_type: str, subject_id: str) -> bool:
        with self._db.transaction() as conn:
            cur = conn.execute(
                "DELETE FROM project_members "
                "WHERE project_id = ? AND subject_type = ? AND subject_id = ?",
                (project_id, subject_type, subject_id),
            )
        return bool(cur.rowcount)
