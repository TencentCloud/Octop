"""Project content rows — the discussion line, and (later) the requirement layer.

Appendix C of the plan puts three tables in this module:

* ``project_comments`` — a task's discussion line (plan T3.1, **this** card)
* ``node_mark_logs`` — the requirement-node type-change log
* ``requirement_nodes`` — the requirement half of the two-layer model

Only ``project_comments`` has a repo so far; ``node_mark_logs`` and
``requirement_nodes`` are the next card (T3.2) and deliberately have none yet.

Resource-table convention (AGENTS.md §7): integer surrogate ``id`` plus the public
string ``comment_id``, exposed as ``id`` with the integer kept as ``pk``.

``task_id`` and ``thread_id`` carry no database foreign key, so ``task_id`` is
checked at write time instead — the same soft-FK approach as
``ProjectTaskRepo._assert_parent_ok``.
"""

from __future__ import annotations

from dataclasses import dataclass

from octop.infra.db.pool import DatabasePool
from octop.infra.db.repos._base import DbRow, map_rows, now_ts
from octop.infra.utils.ulid import new_short_id

#: ``project_comments.author_type`` — who wrote the words.
COMMENT_AUTHOR_USER = "user"
COMMENT_AUTHOR_AGENT = "agent"
COMMENT_AUTHOR_TYPES: tuple[str, ...] = (COMMENT_AUTHOR_USER, COMMENT_AUTHOR_AGENT)

#: ``project_comments.source`` — which surface produced the row.
COMMENT_SOURCE_DASHBOARD = "dashboard"
COMMENT_SOURCE_AGENT = "agent"

#: A plain discussion comment; requirement-node markers arrive with T3.2.
COMMENT_NODE_NONE = "none"
#: A comment marked as the discussion's conclusion (PLAN §5 采纳). The column has
#: no CHECK constraint, so this is a value, not a schema change — zero migrations.
COMMENT_NODE_CONCLUSION = "conclusion"


# ── project_comments ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ProjectCommentRow:
    id: str
    pk: int
    project_id: str
    task_id: str | None
    thread_id: str | None
    author_type: str
    author_id: str
    body: str
    source: str
    node_type: str
    created_at: int
    updated_at: int

    @classmethod
    def from_row(cls, r: DbRow) -> ProjectCommentRow:
        return cls(
            id=str(r["comment_id"]),
            pk=int(r["id"]),
            project_id=str(r["project_id"]),
            task_id=(str(r["task_id"]) if r["task_id"] is not None else None),
            thread_id=(str(r["thread_id"]) if r["thread_id"] is not None else None),
            author_type=str(r["author_type"]),
            author_id=str(r["author_id"]),
            body=str(r["body"]),
            source=str(r["source"]),
            node_type=str(r["node_type"]),
            created_at=int(r["created_at"]),
            updated_at=int(r["updated_at"]),
        )


class ProjectCommentRepo:
    """``project_comments`` — one row per contribution to a discussion line."""

    def __init__(self, db: DatabasePool) -> None:
        self._db = db

    def _allocate_id(self) -> str:
        for _ in range(16):
            comment_id = new_short_id()
            if self.get(comment_id) is None:
                return comment_id
        raise RuntimeError("failed to allocate unique comment id")

    # ── soft foreign key (no DB constraint to lean on) ───────────────────────

    def _assert_task_ok(self, project_id: str, task_id: str | None) -> None:
        """Reject a ``task_id`` that is unknown or owned by another project.

        Two distinct messages on purpose, like ``ProjectTaskRepo._assert_parent_ok``:
        "no such task" and "a task from another project" need different fixes.
        """
        if task_id is None:
            return
        with self._db.connect() as conn:
            row = conn.execute(
                "SELECT project_id FROM project_tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
        if row is None:
            raise ValueError(f"task {task_id} does not exist")
        if str(row["project_id"]) != project_id:
            raise ValueError(f"task {task_id} belongs to another project")

    # ── reads ────────────────────────────────────────────────────────────────

    def set_node_type(self, comment_id: str, node_type: str) -> bool:
        """Mark (or unmark) a comment as the conclusion. Idempotent: writing the
        same value twice is a no-op that still reports success."""
        with self._db.transaction() as conn:
            cur = conn.execute(
                "UPDATE project_comments SET node_type = ?, updated_at = ? WHERE comment_id = ?",
                (node_type, now_ts(), comment_id),
            )
        return bool(cur.rowcount > 0)

    def get(self, comment_id: str) -> ProjectCommentRow | None:
        with self._db.connect() as conn:
            r = conn.execute(
                "SELECT * FROM project_comments WHERE comment_id = ?", (comment_id,)
            ).fetchone()
        return ProjectCommentRow.from_row(r) if r else None

    def list_by_project(
        self,
        project_id: str,
        *,
        task_id: str | None = None,
        concluded: bool | None = None,
    ) -> list[ProjectCommentRow]:
        """Chronological (oldest first) — a discussion line reads top to bottom.

        ``concluded`` narrows to (or away from) the adopted conclusion; ``None``
        keeps every comment, which is the pre-existing behaviour.
        """
        sql = "SELECT * FROM project_comments WHERE project_id = ?"
        params: list[object] = [project_id]
        if task_id is not None:
            sql += " AND task_id = ?"
            params.append(task_id)
        if concluded is not None:
            sql += " AND node_type " + ("=" if concluded else "!=") + " ?"
            params.append(COMMENT_NODE_CONCLUSION)
        sql += " ORDER BY created_at, id"
        with self._db.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return map_rows(rows, ProjectCommentRow)

    def count_by_project(
        self,
        project_id: str,
        *,
        task_id: str | None = None,
        concluded: bool | None = None,
    ) -> int:
        sql = "SELECT COUNT(*) AS c FROM project_comments WHERE project_id = ?"
        params: list[object] = [project_id]
        if task_id is not None:
            sql += " AND task_id = ?"
            params.append(task_id)
        if concluded is not None:
            sql += " AND node_type " + ("=" if concluded else "!=") + " ?"
            params.append(COMMENT_NODE_CONCLUSION)
        with self._db.connect() as conn:
            row = conn.execute(sql, params).fetchone()
        return int(row["c"]) if row else 0

    # ── writes ───────────────────────────────────────────────────────────────

    def create(
        self,
        *,
        project_id: str,
        author_type: str,
        author_id: str,
        body: str,
        task_id: str | None = None,
        thread_id: str | None = None,
        source: str = COMMENT_SOURCE_DASHBOARD,
        node_type: str = COMMENT_NODE_NONE,
    ) -> ProjectCommentRow:
        """Insert one comment on a discussion line.

        ``author_type`` / ``body`` are the service's contract to validate; this
        layer only checks the soft foreign key it cannot delegate.
        """
        self._assert_task_ok(project_id, task_id)
        comment_id = self._allocate_id()
        ts = now_ts()
        with self._db.transaction() as conn:
            conn.execute(
                "INSERT INTO project_comments("
                "comment_id, project_id, task_id, thread_id, author_type, author_id, "
                "body, source, node_type, created_at, updated_at"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    comment_id,
                    project_id,
                    task_id,
                    thread_id,
                    author_type,
                    author_id,
                    body,
                    source,
                    node_type,
                    ts,
                    ts,
                ),
            )
        row = self.get(comment_id)
        if row is None:
            raise RuntimeError(f"project comment insert failed: {comment_id}")
        return row
