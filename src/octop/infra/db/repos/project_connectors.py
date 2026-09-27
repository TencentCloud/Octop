"""``project_connectors`` rows — a project's connector **kind** declarations.

R17 red line: this table stores the ``kind`` and nothing else. No instance id, no
credential column: which concrete connector instance (if any) actually serves a
declaration is resolved per user at read time, never persisted here.
"""

from __future__ import annotations

from dataclasses import dataclass

from octop.infra.db.pool import DatabasePool
from octop.infra.db.repos._base import DbRow, map_rows, now_ts


@dataclass(frozen=True)
class ProjectConnectorRow:
    pk: int
    project_id: str
    kind: str
    created_by: int
    created_at: int

    @classmethod
    def from_row(cls, r: DbRow) -> ProjectConnectorRow:
        return cls(
            pk=int(r["id"]),
            project_id=str(r["project_id"]),
            kind=str(r["kind"]),
            created_by=int(r["created_by"]),
            created_at=int(r["created_at"]),
        )


class ProjectConnectorRepo:
    def __init__(self, db: DatabasePool) -> None:
        self._db = db

    def list_by_project(self, project_id: str) -> list[ProjectConnectorRow]:
        """Declared kinds, oldest first (the order the user declared them)."""
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM project_connectors WHERE project_id = ? ORDER BY created_at, id",
                (project_id,),
            ).fetchall()
        return map_rows(rows, ProjectConnectorRow)

    def get(self, project_id: str, kind: str) -> ProjectConnectorRow | None:
        with self._db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM project_connectors WHERE project_id = ? AND kind = ?",
                (project_id, kind),
            ).fetchone()
        return ProjectConnectorRow.from_row(row) if row else None

    def replace_all(
        self, project_id: str, kinds: list[str], *, created_by: int
    ) -> list[ProjectConnectorRow]:
        """Full replacement (PLAN.md §1, S11): the omitted kinds are detached.

        Rows that stay keep their original ``created_at`` so the display order is
        stable across saves that do not change the set.
        """
        wanted = list(dict.fromkeys(kinds))
        ts = now_ts()
        with self._db.transaction() as conn:
            existing = {
                str(row["kind"])
                for row in conn.execute(
                    "SELECT kind FROM project_connectors WHERE project_id = ?", (project_id,)
                ).fetchall()
            }
            for kind in existing - set(wanted):
                conn.execute(
                    "DELETE FROM project_connectors WHERE project_id = ? AND kind = ?",
                    (project_id, kind),
                )
            for kind in wanted:
                if kind in existing:
                    continue
                conn.execute(
                    "INSERT INTO project_connectors(project_id, kind, created_by, created_at) "
                    "VALUES (?, ?, ?, ?)",
                    (project_id, kind, created_by, ts),
                )
        return self.list_by_project(project_id)
