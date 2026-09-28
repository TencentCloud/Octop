"""Project tag definitions and their per-task links.

Two tables, one fact each (PLAN.md §4):

* ``project_tags``      — the definition (per-project unique ``name``).
* ``project_task_tags`` — a pure link row; ``UNIQUE(task_id, tag_id)``.

Every tag statement in Octop lives here. The service layer
(:mod:`octop.infra.projects.tags`) owns validation and permissions; this module
stays SQL-only, mirroring ``repos/projects.py``.

``project_task_tags`` carries **no** public id: it is a link table, and callers
address it by the pair it names. Both foreign keys cascade, so deleting a tag
definition or a task leaves no orphan link (SPEC 边界 Case「标签被删除」).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

try:
    from psycopg import errors as pg_errors
except ImportError:  # pragma: no cover - optional PostgreSQL driver
    pg_errors = None  # type: ignore[assignment]

from octop.infra.db.pool import DatabasePool
from octop.infra.db.repos._base import (
    UNSET,
    DbRow,
    insert_returning_id,
    map_rows,
    now_ts,
    optional_updates,
    sql_in_placeholders,
)
from octop.infra.utils.ulid import new_short_id


def _is_unique_violation(exc: BaseException) -> bool:
    """True when the driver rejected a write on a UNIQUE constraint.

    Follows the ``repos/user_roles.py`` convention: the repo reports the
    collision as a ``ValueError`` and the service decides the error code.
    """
    if isinstance(exc, sqlite3.IntegrityError):
        return "unique" in str(exc).lower()
    return pg_errors is not None and isinstance(exc, pg_errors.UniqueViolation)


# ── project_tags ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ProjectTagRow:
    pk: int
    tag_id: str
    project_id: str
    name: str
    color: str
    created_by: int
    created_at: int
    updated_at: int

    @classmethod
    def from_row(cls, r: DbRow) -> ProjectTagRow:
        return cls(
            pk=int(r["id"]),
            tag_id=str(r["tag_id"]),
            project_id=str(r["project_id"]),
            name=str(r["name"]),
            color=str(r["color"]),
            created_by=int(r["created_by"]),
            created_at=int(r["created_at"]),
            updated_at=int(r["updated_at"]),
        )


class ProjectTagRepo:
    def __init__(self, db: DatabasePool) -> None:
        self._db = db

    def _allocate_id(self) -> str:
        for _ in range(8):
            candidate = new_short_id()
            if self.get(candidate) is None:
                return candidate
        raise RuntimeError("failed to allocate unique tag id")

    # ── reads ────────────────────────────────────────────────────────────────

    def get(self, tag_id: str) -> ProjectTagRow | None:
        with self._db.connect() as conn:
            r = conn.execute("SELECT * FROM project_tags WHERE tag_id = ?", (tag_id,)).fetchone()
        return ProjectTagRow.from_row(r) if r else None

    def list_by_project(self, project_id: str) -> list[ProjectTagRow]:
        """Definitions in stable display order (``created_at`` then id)."""
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM project_tags WHERE project_id = ? ORDER BY created_at, id",
                (project_id,),
            ).fetchall()
        return map_rows(rows, ProjectTagRow)

    def find_by_name(self, project_id: str, name: str) -> ProjectTagRow | None:
        with self._db.connect() as conn:
            r = conn.execute(
                "SELECT * FROM project_tags WHERE project_id = ? AND name = ?",
                (project_id, name),
            ).fetchone()
        return ProjectTagRow.from_row(r) if r else None

    def list_by_ids(self, tag_ids: list[str]) -> list[ProjectTagRow]:
        """Batch definition lookup — one ``IN`` query, never one per id."""
        if not tag_ids:
            return []
        sql = f"SELECT * FROM project_tags WHERE tag_id IN ({sql_in_placeholders(len(tag_ids))})"
        with self._db.connect() as conn:
            rows = conn.execute(sql, list(tag_ids)).fetchall()
        return map_rows(rows, ProjectTagRow)

    # ── writes ───────────────────────────────────────────────────────────────

    def create(
        self,
        *,
        project_id: str,
        name: str,
        created_by: int,
        color: str = "",
    ) -> ProjectTagRow:
        tag_id = self._allocate_id()
        ts = now_ts()
        try:
            with self._db.transaction() as conn:
                insert_returning_id(
                    conn,
                    "INSERT INTO project_tags("
                    "tag_id, project_id, name, color, created_by, created_at, updated_at"
                    ") VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (tag_id, project_id, name, color, created_by, ts, ts),
                )
        except Exception as exc:
            if _is_unique_violation(exc):
                raise ValueError("tag_name_taken") from exc
            raise
        row = self.get(tag_id)
        if row is None:
            raise RuntimeError(f"project tag insert failed: {tag_id}")
        return row

    def update(
        self,
        tag_id: str,
        *,
        name: object = UNSET,
        color: object = UNSET,
    ) -> ProjectTagRow | None:
        current = self.get(tag_id)
        if current is None:
            return None
        clauses, params = optional_updates([("name", name), ("color", color)])
        if not clauses:
            return current
        clauses.append("updated_at = ?")
        params.append(now_ts())
        params.append(tag_id)
        try:
            with self._db.transaction() as conn:
                conn.execute(
                    f"UPDATE project_tags SET {', '.join(clauses)} WHERE tag_id = ?",
                    params,
                )
        except Exception as exc:
            if _is_unique_violation(exc):
                raise ValueError("tag_name_taken") from exc
            raise
        return self.get(tag_id)

    def delete(self, tag_id: str) -> bool:
        """Delete a definition. Its links cascade via ``ON DELETE CASCADE``."""
        with self._db.transaction() as conn:
            cur = conn.execute("DELETE FROM project_tags WHERE tag_id = ?", (tag_id,))
        return bool(cur.rowcount)

    # ── project_task_tags (links) ────────────────────────────────────────────

    def list_tag_ids_for_task(self, task_id: str) -> list[str]:
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT tag_id FROM project_task_tags WHERE task_id = ? ORDER BY created_at, id",
                (task_id,),
            ).fetchall()
        return [str(r["tag_id"]) for r in rows]

    def list_tags_for_tasks(self, task_ids: list[str]) -> dict[str, list[ProjectTagRow]]:
        """Resolve tags for many tasks at once.

        The board renders every task in one pass; issuing one query per task
        would be N+1, so this joins the link table and the definition table in a
        single statement and groups in Python.
        """
        if not task_ids:
            return {}
        placeholders = sql_in_placeholders(len(task_ids))
        sql = (
            "SELECT l.task_id AS link_task_id, t.* FROM project_task_tags AS l "
            "JOIN project_tags AS t ON t.tag_id = l.tag_id "
            f"WHERE l.task_id IN ({placeholders}) "
            "ORDER BY l.created_at, l.id"
        )
        with self._db.connect() as conn:
            rows = conn.execute(sql, list(task_ids)).fetchall()
        grouped: dict[str, list[ProjectTagRow]] = {task_id: [] for task_id in task_ids}
        for r in rows:
            grouped.setdefault(str(r["link_task_id"]), []).append(ProjectTagRow.from_row(r))
        return grouped

    def set_task_tags(self, task_id: str, tag_ids: list[str]) -> list[str]:
        """Replace a task's tag set, preserving ``created_at`` of kept links.

        A blind delete-then-insert would reset the ordering of links that did not
        change, so only the difference is written.
        """
        wanted = list(dict.fromkeys(tag_ids))
        with self._db.transaction() as conn:
            existing = {
                str(r["tag_id"])
                for r in conn.execute(
                    "SELECT tag_id FROM project_task_tags WHERE task_id = ?", (task_id,)
                ).fetchall()
            }
            drop = sorted(existing - set(wanted))
            if drop:
                conn.execute(
                    "DELETE FROM project_task_tags WHERE task_id = ? AND tag_id IN "
                    f"({sql_in_placeholders(len(drop))})",
                    (task_id, *drop),
                )
            add = [tag_id for tag_id in wanted if tag_id not in existing]
            ts = now_ts()
            for tag_id in add:
                conn.execute(
                    "INSERT INTO project_task_tags(task_id, tag_id, created_at) VALUES (?, ?, ?)",
                    (task_id, tag_id, ts),
                )
        return self.list_tag_ids_for_task(task_id)

    def count_links_for_tag(self, tag_id: str) -> int:
        """Link rows pointing at one definition (cascade / no-orphan evidence)."""
        with self._db.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM project_task_tags WHERE tag_id = ?",
                (tag_id,),
            ).fetchone()
        return int(row["c"]) if row else 0

    def count_links_for_task(self, task_id: str) -> int:
        with self._db.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM project_task_tags WHERE task_id = ?",
                (task_id,),
            ).fetchone()
        return int(row["c"]) if row else 0

    def count_orphan_links(self) -> int:
        """Links whose definition or task has vanished — must always be 0."""
        with self._db.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM project_task_tags AS l "
                "LEFT JOIN project_tags AS t ON t.tag_id = l.tag_id "
                "LEFT JOIN project_tasks AS k ON k.task_id = l.task_id "
                "WHERE t.tag_id IS NULL OR k.task_id IS NULL"
            ).fetchone()
        return int(row["c"]) if row else 0
