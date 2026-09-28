"""``project_artifacts`` rows — the single writer for project file metadata.

The table predates this feature (migration 019); migration 020 added ``size`` and
``mime``. Project attachments reuse it with ``kind='attachment'``: ``task_id``
NULL means *pending* (uploaded from the create-task dialog before the task
exists), a non-NULL ``task_id`` means bound. No new table, no status column.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from octop.infra.db.pool import DatabasePool
from octop.infra.db.repos._base import DbRow, map_rows, now_ts, sql_in_placeholders

ATTACHMENT_KIND = "attachment"


@dataclass(frozen=True)
class ArtifactRow:
    pk: int
    artifact_id: str
    project_id: str
    task_id: str | None
    kind: str
    name: str
    uri: str
    size: int
    mime: str
    hash: str
    created_by: str
    created_at: int
    comment_id: str | None

    @classmethod
    def from_row(cls, r: DbRow) -> ArtifactRow:
        return cls(
            pk=int(r["id"]),
            artifact_id=str(r["artifact_id"]),
            project_id=str(r["project_id"]),
            task_id=(str(r["task_id"]) if r["task_id"] is not None else None),
            kind=str(r["kind"]),
            name=str(r["name"]),
            uri=str(r["uri"]),
            size=int(r["size"]),
            mime=str(r["mime"]),
            hash=str(r["hash"]),
            created_by=str(r["created_by"]),
            created_at=int(r["created_at"]),
            comment_id=r["comment_id"],
        )


class ProjectArtifactRepo:
    def __init__(self, db: DatabasePool) -> None:
        self._db = db

    def artifact_id_exists(self, artifact_id: str) -> bool:
        with self._db.connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM project_artifacts WHERE artifact_id = ?", (artifact_id,)
            ).fetchone()
        return row is not None

    def insert(
        self,
        *,
        artifact_id: str,
        project_id: str,
        task_id: str | None,
        name: str,
        uri: str,
        size: int,
        mime: str,
        file_hash: str,
        created_by: str,
        kind: str = ATTACHMENT_KIND,
    ) -> ArtifactRow:
        ts = now_ts()
        with self._db.transaction() as conn:
            conn.execute(
                "INSERT INTO project_artifacts("
                "artifact_id, project_id, task_id, thread_id, kind, name, uri, agent_id,"
                " kb_document_id, commit_ref, version, hash, size, mime, created_by, created_at"
                ") VALUES (?, ?, ?, NULL, ?, ?, ?, NULL, NULL, NULL, 1, ?, ?, ?, ?, ?)",
                (
                    artifact_id,
                    project_id,
                    task_id,
                    kind,
                    name,
                    uri,
                    file_hash,
                    size,
                    mime,
                    created_by,
                    ts,
                ),
            )
        row = self.get(artifact_id)
        if row is None:
            raise RuntimeError(f"artifact insert failed: {artifact_id}")
        return row

    def get(self, artifact_id: str) -> ArtifactRow | None:
        with self._db.connect() as conn:
            r = conn.execute(
                "SELECT * FROM project_artifacts WHERE artifact_id = ?", (artifact_id,)
            ).fetchone()
        return ArtifactRow.from_row(r) if r else None

    def list_by_task(self, *, project_id: str, task_id: str) -> list[ArtifactRow]:
        """Bound attachments of one task, oldest first (display order)."""
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM project_artifacts "
                "WHERE project_id = ? AND task_id = ? AND kind = ? "
                "ORDER BY created_at, id",
                (project_id, task_id, ATTACHMENT_KIND),
            ).fetchall()
        return map_rows(rows, ArtifactRow)

    def list_by_tasks(
        self, *, project_id: str, task_ids: list[str]
    ) -> dict[str, list[ArtifactRow]]:
        """Resolve attachments for many tasks at once — one ``IN`` query.

        The board renders every task in one pass; a query per task would be N+1.
        """
        if not task_ids:
            return {}
        placeholders = sql_in_placeholders(len(task_ids))
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM project_artifacts "
                f"WHERE project_id = ? AND kind = ? AND task_id IN ({placeholders}) "
                "ORDER BY created_at, id",
                [project_id, ATTACHMENT_KIND, *task_ids],
            ).fetchall()
        grouped: dict[str, list[ArtifactRow]] = {task_id: [] for task_id in task_ids}
        for row in map_rows(rows, ArtifactRow):
            grouped.setdefault(row.task_id or "", []).append(row)
        return grouped

    def list_pending(self, project_id: str) -> list[ArtifactRow]:
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM project_artifacts "
                "WHERE project_id = ? AND kind = ? AND task_id IS NULL "
                "ORDER BY created_at, id",
                (project_id, ATTACHMENT_KIND),
            ).fetchall()
        return map_rows(rows, ArtifactRow)

    def sum_size_for_task(self, task_id: str) -> int:
        with self._db.connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(size), 0) AS total FROM project_artifacts "
                "WHERE kind = ? AND task_id = ?",
                (ATTACHMENT_KIND, task_id),
            ).fetchone()
        return int(row["total"]) if row else 0

    def sum_pending_size(self, project_id: str) -> int:
        with self._db.connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(size), 0) AS total FROM project_artifacts "
                "WHERE kind = ? AND project_id = ? AND task_id IS NULL",
                (ATTACHMENT_KIND, project_id),
            ).fetchone()
        return int(row["total"]) if row else 0

    def bind(self, artifact_id: str, *, task_id: str) -> bool:
        """Bind a **pending** row; an already-bound row is left untouched."""
        with self._db.transaction() as conn:
            cur = conn.execute(
                "UPDATE project_artifacts SET task_id = ? WHERE artifact_id = ? AND task_id IS NULL",
                (task_id, artifact_id),
            )
        return bool(cur.rowcount)

    def unbind(self, artifact_id: str, *, task_id: str) -> bool:
        """Compensating unbind — idempotent, and never touches other tasks' rows."""
        with self._db.transaction() as conn:
            cur = conn.execute(
                "UPDATE project_artifacts SET task_id = NULL WHERE artifact_id = ? AND task_id = ?",
                (artifact_id, task_id),
            )
        return bool(cur.rowcount)

    def bind_comment(self, artifact_id: str, *, comment_id: str) -> bool:
        """Attach an artifact to the comment that introduced it (v23 column).

        Mirrors :meth:`bind` for ``task_id``: the file is inserted first (uploads
        do not know the comment yet) and bound afterwards.
        """
        with self._db.transaction() as conn:
            cur = conn.execute(
                "UPDATE project_artifacts SET comment_id = ? WHERE artifact_id = ?",
                (comment_id, artifact_id),
            )
        return bool(cur.rowcount > 0)

    def list_by_comment(self, *, project_id: str, comment_id: str) -> list[ArtifactRow]:
        """The files one comment owns, oldest first."""
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM project_artifacts WHERE project_id = ? AND comment_id = ? "
                "ORDER BY created_at, artifact_id",
                (project_id, comment_id),
            ).fetchall()
        return map_rows(rows, ArtifactRow)

    def delete_by_comment(self, comment_id: str, *, conn: Any = None) -> int:
        """Delete every artifact bound to a comment; returns how many rows went.

        Takes the caller's transaction (``conn``) because deleting a comment is one
        unit of work: comment row + its attachments + the audit row commit together
        or not at all (PLAN §4).
        """
        statement = "DELETE FROM project_artifacts WHERE comment_id = ?"
        if conn is not None:
            return int(conn.execute(statement, (comment_id,)).rowcount)
        with self._db.transaction() as own:
            return int(own.execute(statement, (comment_id,)).rowcount)

    def delete(self, artifact_id: str) -> bool:
        with self._db.transaction() as conn:
            cur = conn.execute(
                "DELETE FROM project_artifacts WHERE artifact_id = ?", (artifact_id,)
            )
        return bool(cur.rowcount)
