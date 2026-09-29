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
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.utils.ulid import new_short_id

TASK_STATUSES: tuple[str, ...] = (
    "planning",
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


def _json_array(value: object) -> object:
    """Codec for a JSON-array column in a patch: ``UNSET`` stays ``UNSET``.

    The patch semantics (``UNSET`` = leave alone, explicit value = write) decide
    what to do *before* the codec runs, so the sentinel passes through untouched.
    """
    if value is UNSET:
        return UNSET
    return _dump_deps(cast("Iterable[object]", value))


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
    start_at: int | None
    due_at: int | None
    sort_order: int
    created_by: int
    created_at: int
    updated_at: int
    # 025 team-run columns (PLAN「数据模型②·加列」). The four JSON arrays reuse the
    # ``deps`` codec above; the claim/attempt tokens are written by ``claim`` alone
    # so a stale writer can never move them.
    kind: str = "work"
    acceptance: tuple[str, ...] = ()
    in_scope: tuple[str, ...] = ()
    verify: tuple[str, ...] = ()
    changed_paths: tuple[str, ...] = ()
    round: int = 1
    verdict: str | None = None
    attempt: int = 0
    attempt_id: str | None = None
    claimed_by: str | None = None
    claimed_at: int | None = None
    started_at: int | None = None
    phase: str | None = None

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
            start_at=(int(r["start_at"]) if r["start_at"] is not None else None),
            due_at=(int(r["due_at"]) if r["due_at"] is not None else None),
            sort_order=int(r["sort_order"]),
            created_by=int(r["created_by"]),
            created_at=int(r["created_at"]),
            updated_at=int(r["updated_at"]),
            kind=str(r["kind"]),
            acceptance=_parse_deps(r["acceptance"]),
            in_scope=_parse_deps(r["in_scope"]),
            verify=_parse_deps(r["verify"]),
            changed_paths=_parse_deps(r["changed_paths"]),
            round=int(r["round"]),
            verdict=(str(r["verdict"]) if r["verdict"] is not None else None),
            attempt=int(r["attempt"]),
            attempt_id=(str(r["attempt_id"]) if r["attempt_id"] is not None else None),
            claimed_by=(str(r["claimed_by"]) if r["claimed_by"] is not None else None),
            claimed_at=(int(r["claimed_at"]) if r["claimed_at"] is not None else None),
            started_at=(int(r["started_at"]) if r["started_at"] is not None else None),
            phase=(str(r["phase"]) if r["phase"] is not None else None),
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
            raise OctopError(
                ErrorCode.PROJECT_TASK_NOT_FOUND,
                f"parent task {parent_id} does not exist",
            )
        if parent.project_id != project_id:
            raise OctopError(
                ErrorCode.PROJECT_TASK_NOT_FOUND,
                f"parent task {parent_id} belongs to another project",
            )

    def _assert_thread_exists(self, thread_id: str | None) -> None:
        if thread_id is None:
            return
        with self._db.connect() as conn:
            row = conn.execute("SELECT 1 FROM threads WHERE thread_id = ?", (thread_id,)).fetchone()
        if row is None:
            raise OctopError(
                ErrorCode.PROJECT_TASK_THREAD_NOT_FOUND,
                f"thread {thread_id} does not exist",
            )

    def _assert_parent_not_descendant(self, task_id: str, parent_id: str) -> None:
        """Reject an **indirect** cycle: the new parent is a descendant of the task.

        Only reachable once a task may be re-parented (``update``). Walking up
        from the proposed parent must never reach ``task_id``; if it does, the
        move would create ``A -> B -> A`` and the row would become unreachable
        from any root.

        The self-reference (``parent_id == task_id``), a missing parent and a
        cross-project parent stay ``404 PROJECT_TASK_NOT_FOUND`` — they are
        checked before this runs and must not move to this code (batch 3 §5.2).

        The walk is bounded by ``seen``: a chain that is already cyclic (dirty
        data written before this guard existed) and a chain that ends in a
        missing row both stop instead of looping forever.
        """
        seen = {task_id}
        current: str | None = parent_id
        while current is not None:
            if current in seen:
                raise OctopError(
                    ErrorCode.PROJECT_TASK_PARENT_INVALID,
                    f"parent task {parent_id} is a descendant of task {task_id}",
                )
            seen.add(current)
            row = self.get(current)
            current = row.parent_id if row is not None else None

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
        start_at: int | None = None,
        due_at: int | None = None,
        sort_order: int | None = None,
        kind: str = "work",
        acceptance: Iterable[object] = (),
        in_scope: Iterable[object] = (),
        verify: Iterable[object] = (),
        phase: str | None = None,
        task_id: str | None = None,
    ) -> ProjectTaskRow:
        self._assert_parent_ok(project_id, parent_id)
        self._assert_thread_exists(thread_id)
        # A caller-supplied id is honoured verbatim (the plan's API takes ``id?`` so a
        # run can name its own tasks); omitted, the id is allocated as before -- every
        # existing caller is untouched. Uniqueness is the caller's to enforce *before*
        # this insert (``validate_task_graph`` does), because the UNIQUE constraint's
        # failure would surface as a 500 rather than the plan's 409.
        task_id = task_id or self._allocate_id()
        ts = now_ts()
        if sort_order is None:
            sort_order = self.next_sort_order(project_id)
        with self._db.transaction() as conn:
            conn.execute(
                "INSERT INTO project_tasks("
                "task_id, project_id, parent_id, title, description, status, "
                "assignee_type, assignee_id, priority, deps, thread_id, origin_node_id, "
                "start_at, due_at, sort_order, created_by, created_at, updated_at, "
                "kind, acceptance, in_scope, verify, phase"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
                    start_at,
                    due_at,
                    sort_order,
                    created_by,
                    ts,
                    ts,
                    kind,
                    _dump_deps(acceptance),
                    _dump_deps(in_scope),
                    _dump_deps(verify),
                    phase,
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
        start_at: object = UNSET,
        due_at: object = UNSET,
        sort_order: object = UNSET,
        kind: object = UNSET,
        acceptance: object = UNSET,
        in_scope: object = UNSET,
        verify: object = UNSET,
        changed_paths: object = UNSET,
        round: object = UNSET,
        verdict: object = UNSET,
        phase: object = UNSET,
        started_at: object = UNSET,
    ) -> ProjectTaskRow | None:
        current = self.get(task_id)
        if current is None:
            return None
        if parent_id is not UNSET:
            parent_value = cast("str | None", parent_id)
            if parent_value == task_id:
                raise OctopError(
                    ErrorCode.PROJECT_TASK_NOT_FOUND,
                    "a task cannot be its own parent",
                )
            self._assert_parent_ok(current.project_id, parent_value)
            if parent_value is not None:
                # ④ indirect cycle only; the three 404 shapes above are frozen.
                self._assert_parent_not_descendant(task_id, parent_value)
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
                ("start_at", start_at),
                ("due_at", due_at),
                ("sort_order", sort_order),
                ("kind", kind),
                ("acceptance", _json_array(acceptance)),
                ("in_scope", _json_array(in_scope)),
                ("verify", _json_array(verify)),
                ("changed_paths", _json_array(changed_paths)),
                ("round", round),
                ("verdict", verdict),
                ("phase", phase),
                ("started_at", started_at),
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

    # ── attempts (claim / report) ────────────────────────────────────────────
    #
    # ``attempt_id`` is the token a run hands out when it claims a task and the
    # credential every later write must present (PLAN G8): a superseded token
    # cannot move the row. These two methods are the **only** writers of the
    # claim/attempt columns, which is what keeps that guarantee in one place.

    def _attempt_guard(self, task_id: str, expected: str | None) -> tuple[str, list[object]]:
        """``WHERE`` body pinning the row to the attempt the caller last read.

        ``attempt_id`` is nullable, so the guard is spelled in two shapes instead
        of ``attempt_id IS ?``: the PostgreSQL proxy rewrites ``?`` to ``%s`` and
        PostgreSQL rejects a placeholder after ``IS``. Same idiom as
        ``ArtifactRepo.bind`` (``... AND task_id IS NULL``).
        """
        if expected is None:
            return "task_id = ? AND attempt_id IS NULL", [task_id]
        return "task_id = ? AND attempt_id = ?", [task_id, expected]

    def claim(
        self,
        task_id: str,
        *,
        claimed_by: str,
        expected_attempt_id: str | None,
        attempt_id: str | None = None,
    ) -> ProjectTaskRow | None:
        """Claim *task_id* for *claimed_by* under a new attempt.

        Compare-and-set, and nothing else: one ``UPDATE`` whose ``WHERE`` carries
        the attempt the caller gated on. Two racing claims therefore cannot both
        win — the loser's statement matches no row and gets ``None``, which the
        caller answers with ``TEAM_TASK_CLAIM_CONFLICT``. The decision is taken by
        the database, not by a read-then-``if`` in Python (PLAN B26: the loser
        must never twin the owner).

        *expected_attempt_id* is what the caller read **before** its gates ran
        (``None`` until the first claim); passing a freshly re-read value instead
        is a deliberate transfer, which the plan allows. *attempt_id* is the token
        the new attempt runs under — omitted, a fresh one is minted; either way
        ``attempt`` is bumped. ``None`` also covers a task that no longer exists.
        """
        guard, guard_params = self._attempt_guard(task_id, expected_attempt_id)
        ts = now_ts()
        with self._db.transaction() as conn:
            cur = conn.execute(
                "UPDATE project_tasks SET claimed_by = ?, claimed_at = ?, attempt_id = ?, "
                f"attempt = attempt + 1, updated_at = ? WHERE {guard}",
                (claimed_by, ts, attempt_id or new_short_id(), ts, *guard_params),
            )
        if not cur.rowcount:
            return None
        return self.get(task_id)

    def report(
        self,
        task_id: str,
        *,
        attempt_id: str,
        verdict: object = UNSET,
        changed_paths: object = UNSET,
        round: object = UNSET,
        phase: object = UNSET,
    ) -> ProjectTaskRow | None:
        """Record an attempt's outcome; ``None`` when *attempt_id* is stale.

        A write carrying a superseded token is refused (PLAN G8) — the row is left
        untouched and the caller answers ``TEAM_ATTEMPT_STALE``. The guard is
        re-checked inside the ``UPDATE`` as well, so an attempt that is superseded
        between the read and the write is refused too. Patch semantics are the
        same as :meth:`update`: omitted fields stay, explicit ``None`` clears.
        """
        current = self.get(task_id)
        if current is None:
            return None
        if current.attempt_id != attempt_id:
            return None
        clauses, params = optional_updates(
            [
                ("verdict", verdict),
                ("changed_paths", _json_array(changed_paths)),
                ("round", round),
                ("phase", phase),
            ]
        )
        if not clauses:
            return current
        guard, guard_params = self._attempt_guard(task_id, current.attempt_id)
        clauses.append("updated_at = ?")
        params.append(now_ts())
        with self._db.transaction() as conn:
            cur = conn.execute(
                f"UPDATE project_tasks SET {', '.join(clauses)} WHERE {guard}",
                [*params, *guard_params],
            )
        if not cur.rowcount:
            return None
        return self.get(task_id)


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
        self, project_id: str, *, limit: int | None = None, task_id: str | None = None
    ) -> list[TimelineEventRow]:
        """Chronological order — oldest first, which is the replay order.

        ``task_id`` filters **in SQL** (a post-filter would interact with ``limit``
        and drop rows); omitting it leaves the statement byte-identical to before.
        """
        sql = "SELECT * FROM timeline_events WHERE project_id = ?"
        params: list[object] = [project_id]
        if task_id is not None:
            sql += " AND task_id = ?"
            params.append(task_id)
        sql += " ORDER BY at, id"
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
