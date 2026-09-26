"""Project task rows and the append-only project timeline.

``project_tasks`` and ``timeline_events`` live together because every task
mutation writes a timeline row.

Columns that have no database foreign key (``parent_id``, ``thread_id``) are
validated at write time instead — the plan asks for soft-FK existence checks so
a bogus reference cannot silently create an orphan.

Timeline actions use a ``<subject>.<verb>`` vocabulary so a reader can filter by
prefix; the persisted values are the constants below rather than ad-hoc strings.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, cast

from octop.infra.db.pool import DatabasePool
from octop.infra.db.repos._base import (
    UNSET,
    DbRow,
    insert_returning_id,
    map_rows,
    now_ts,
    optional_updates,
)
from octop.infra.utils.ulid import new_short_id

TASK_STATUSES: tuple[str, ...] = (
    "todo",
    "doing",
    "review",
    "done",
    "blocked",
    "cancelled",
)

#: Who a task can be assigned to (``assignee_type``).
TASK_ASSIGNEE_TYPES: tuple[str, ...] = ("user", "agent", "team")

# ── timeline action vocabulary ───────────────────────────────────────────────
TIMELINE_TASK_CREATED = "task.created"
TIMELINE_TASK_UPDATED = "task.updated"
TIMELINE_TASK_STATUS_CHANGED = "task.status_changed"
TIMELINE_TASK_ASSIGNED = "task.assigned"
TIMELINE_TASK_DELETED = "task.deleted"
TIMELINE_TASK_DISPATCHED = "task.dispatched"


def actor_ref(kind: str, actor_id: object) -> str:
    """Timeline actor string, e.g. ``user:12`` / ``agent:ab12cd``."""
    return f"{kind}:{actor_id}"


def _parse_deps(raw: object) -> tuple[str, ...]:
    try:
        parsed = json.loads(str(raw) if raw else "[]")
    except (TypeError, ValueError):
        return ()
    if not isinstance(parsed, list):
        return ()
    return tuple(str(x) for x in parsed)


def _dump_deps(deps: Iterable[object]) -> str:
    return json.dumps([str(d) for d in deps], ensure_ascii=False)


def _parse_payload(raw: object) -> dict[str, Any]:
    try:
        parsed = json.loads(str(raw) if raw else "{}")
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


# ── project_tasks ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ProjectTaskRow:
    id: str
    pk: int
    project_id: str
    parent_id: str | None
    title: str
    description: str
    status: str
    assignee_type: str | None
    assignee_id: str | None
    priority: int
    deps: tuple[str, ...]
    thread_id: str | None
    origin_node_id: str | None
    due_at: int | None
    sort_order: int
    created_by: int
    created_at: int
    updated_at: int

    @classmethod
    def from_row(cls, r: DbRow) -> ProjectTaskRow:
        return cls(
            id=str(r["task_id"]),
            pk=int(r["id"]),
            project_id=str(r["project_id"]),
            parent_id=(str(r["parent_id"]) if r["parent_id"] is not None else None),
            title=str(r["title"]),
            description=str(r["description"] or ""),
            status=str(r["status"]),
            assignee_type=(str(r["assignee_type"]) if r["assignee_type"] is not None else None),
            assignee_id=(str(r["assignee_id"]) if r["assignee_id"] is not None else None),
            priority=int(r["priority"]),
            deps=_parse_deps(r["deps"]),
            thread_id=(str(r["thread_id"]) if r["thread_id"] is not None else None),
            origin_node_id=(str(r["origin_node_id"]) if r["origin_node_id"] is not None else None),
            due_at=(int(r["due_at"]) if r["due_at"] is not None else None),
            sort_order=int(r["sort_order"]),
            created_by=int(r["created_by"]),
            created_at=int(r["created_at"]),
            updated_at=int(r["updated_at"]),
        )


class ProjectTaskRepo:
    def __init__(self, db: DatabasePool) -> None:
        self._db = db

    def _allocate_id(self) -> str:
        for _ in range(16):
            task_id = new_short_id()
            if self.get(task_id) is None:
                return task_id
        raise RuntimeError("failed to allocate unique task id")

    # ── soft foreign keys (no DB constraint to lean on) ──────────────────────

    def _assert_parent_ok(self, project_id: str, parent_id: str | None) -> None:
        if parent_id is None:
            return
        parent = self.get(parent_id)
        if parent is None:
            raise ValueError(f"parent task {parent_id} does not exist")
        if parent.project_id != project_id:
            raise ValueError(f"parent task {parent_id} belongs to another project")

    def _assert_thread_exists(self, thread_id: str | None) -> None:
        if thread_id is None:
            return
        with self._db.connect() as conn:
            row = conn.execute("SELECT 1 FROM threads WHERE thread_id = ?", (thread_id,)).fetchone()
        if row is None:
            raise ValueError(f"thread {thread_id} does not exist")

    # ── reads ────────────────────────────────────────────────────────────────

    def next_sort_order(self, project_id: str) -> int:
        with self._db.connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(sort_order), -1) AS m FROM project_tasks WHERE project_id = ?",
                (project_id,),
            ).fetchone()
        return int(row["m"]) + 1 if row else 0

    def get(self, task_id: str) -> ProjectTaskRow | None:
        with self._db.connect() as conn:
            r = conn.execute("SELECT * FROM project_tasks WHERE task_id = ?", (task_id,)).fetchone()
        return ProjectTaskRow.from_row(r) if r else None

    def list_by_project(
        self, project_id: str, *, status: str | None = None
    ) -> list[ProjectTaskRow]:
        sql = "SELECT * FROM project_tasks WHERE project_id = ?"
        params: list[object] = [project_id]
        if status is not None:
            sql += " AND status = ?"
            params.append(status)
        sql += " ORDER BY sort_order, created_at, id"
        with self._db.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return map_rows(rows, ProjectTaskRow)

    def list_by_thread(self, thread_id: str) -> list[ProjectTaskRow]:
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM project_tasks WHERE thread_id = ? ORDER BY created_at",
                (thread_id,),
            ).fetchall()
        return map_rows(rows, ProjectTaskRow)

    def count_by_project(self, project_id: str, *, status: str | None = None) -> int:
        sql = "SELECT COUNT(*) AS c FROM project_tasks WHERE project_id = ?"
        params: list[object] = [project_id]
        if status is not None:
            sql += " AND status = ?"
            params.append(status)
        with self._db.connect() as conn:
            row = conn.execute(sql, params).fetchone()
        return int(row["c"]) if row else 0

    # ── writes ───────────────────────────────────────────────────────────────

    def create(
        self,
        *,
        project_id: str,
        title: str,
        created_by: int,
        description: str = "",
        status: str = "todo",
        parent_id: str | None = None,
        assignee_type: str | None = None,
        assignee_id: str | None = None,
        priority: int = 0,
        deps: Iterable[object] = (),
        thread_id: str | None = None,
        origin_node_id: str | None = None,
        due_at: int | None = None,
        sort_order: int | None = None,
    ) -> ProjectTaskRow:
        self._assert_parent_ok(project_id, parent_id)
        self._assert_thread_exists(thread_id)
        task_id = self._allocate_id()
        ts = now_ts()
        if sort_order is None:
            sort_order = self.next_sort_order(project_id)
        with self._db.transaction() as conn:
            conn.execute(
                "INSERT INTO project_tasks("
                "task_id, project_id, parent_id, title, description, status, "
                "assignee_type, assignee_id, priority, deps, thread_id, origin_node_id, "
                "due_at, sort_order, created_by, created_at, updated_at"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    task_id,
                    project_id,
                    parent_id,
                    title,
                    description,
                    status,
                    assignee_type,
                    assignee_id,
                    priority,
                    _dump_deps(deps),
                    thread_id,
                    origin_node_id,
                    due_at,
                    sort_order,
                    created_by,
                    ts,
                    ts,
                ),
            )
        row = self.get(task_id)
        if row is None:
            raise RuntimeError(f"project task insert failed: {task_id}")
        return row

    def update(
        self,
        task_id: str,
        *,
        title: object = UNSET,
        description: object = UNSET,
        status: object = UNSET,
        parent_id: object = UNSET,
        assignee_type: object = UNSET,
        assignee_id: object = UNSET,
        priority: object = UNSET,
        deps: object = UNSET,
        thread_id: object = UNSET,
        origin_node_id: object = UNSET,
        due_at: object = UNSET,
        sort_order: object = UNSET,
    ) -> ProjectTaskRow | None:
        current = self.get(task_id)
        if current is None:
            return None
        if parent_id is not UNSET:
            parent_value = cast("str | None", parent_id)
            if parent_value == task_id:
                raise ValueError("a task cannot be its own parent")
            self._assert_parent_ok(current.project_id, parent_value)
        if thread_id is not UNSET:
            self._assert_thread_exists(cast("str | None", thread_id))

        clauses, params = optional_updates(
            [
                ("title", title),
                ("description", description),
                ("status", status),
                ("parent_id", parent_id),
                ("assignee_type", assignee_type),
                ("assignee_id", assignee_id),
                ("priority", priority),
                (
                    "deps",
                    _dump_deps(cast("Iterable[object]", deps)) if deps is not UNSET else UNSET,
                ),
                ("thread_id", thread_id),
                ("origin_node_id", origin_node_id),
                ("due_at", due_at),
                ("sort_order", sort_order),
            ]
        )
        if not clauses:
            return current
        clauses.append("updated_at = ?")
        params.append(now_ts())
        params.append(task_id)
        with self._db.transaction() as conn:
            conn.execute(
                f"UPDATE project_tasks SET {', '.join(clauses)} WHERE task_id = ?",
                params,
            )
        return self.get(task_id)

    def delete(self, task_id: str) -> bool:
        with self._db.transaction() as conn:
            cur = conn.execute("DELETE FROM project_tasks WHERE task_id = ?", (task_id,))
        return bool(cur.rowcount)


# ── timeline_events ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class TimelineEventRow:
    pk: int
    project_id: str
    task_id: str | None
    actor: str
    action: str
    payload: dict[str, Any]
    at: int

    @classmethod
    def from_row(cls, r: DbRow) -> TimelineEventRow:
        return cls(
            pk=int(r["id"]),
            project_id=str(r["project_id"]),
            task_id=(str(r["task_id"]) if r["task_id"] is not None else None),
            actor=str(r["actor"]),
            action=str(r["action"]),
            payload=_parse_payload(r["payload"]),
            at=int(r["at"]),
        )


class TimelineRepo:
    """Append-only project timeline — rows are never updated or deleted."""

    def __init__(self, db: DatabasePool) -> None:
        self._db = db

    def append(
        self,
        *,
        project_id: str,
        actor: str,
        action: str,
        task_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> TimelineEventRow:
        ts = now_ts()
        with self._db.transaction() as conn:
            # RETURNING id rather than cursor.lastrowid: the PostgreSQL proxy
            # does not expose lastrowid.
            event_pk = insert_returning_id(
                conn,
                "INSERT INTO timeline_events(project_id, task_id, actor, action, payload, at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    project_id,
                    task_id,
                    actor,
                    action,
                    json.dumps(payload or {}, ensure_ascii=False),
                    ts,
                ),
            )
        row = self._get_by_pk(event_pk)
        if row is None:
            raise RuntimeError("timeline insert failed")
        return row

    def _get_by_pk(self, pk: int) -> TimelineEventRow | None:
        with self._db.connect() as conn:
            r = conn.execute("SELECT * FROM timeline_events WHERE id = ?", (pk,)).fetchone()
        return TimelineEventRow.from_row(r) if r else None

    def list_by_project(
        self, project_id: str, *, limit: int | None = None
    ) -> list[TimelineEventRow]:
        """Chronological order — oldest first, which is the replay order."""
        sql = "SELECT * FROM timeline_events WHERE project_id = ? ORDER BY at, id"
        params: list[object] = [project_id]
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        with self._db.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return map_rows(rows, TimelineEventRow)

    def list_by_task(self, task_id: str, *, limit: int | None = None) -> list[TimelineEventRow]:
        sql = "SELECT * FROM timeline_events WHERE task_id = ? ORDER BY at, id"
        params: list[object] = [task_id]
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        with self._db.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return map_rows(rows, TimelineEventRow)

    def count_by_project(self, project_id: str) -> int:
        with self._db.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM timeline_events WHERE project_id = ?",
                (project_id,),
            ).fetchone()
        return int(row["c"]) if row else 0
