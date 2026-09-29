"""``project_task_findings`` rows (migration 025).

A finding is one review/test defect raised against a project task. ``task_id`` is
the public string id of ``project_tasks``; ``run_id`` points at the team run that
raised it (nullable, because a finding can be filed outside a run).

``title`` is stored **as submitted**. Normalising it for cross-round comparison is
**not this module's job**: the single authority is ``pipeline.norm_title`` (gate G16
compares through it, and it drops finding ids, ``（P1）`` severity markers and
punctuation). An earlier revision of this repo carried a second, weaker normaliser
here -- it was deleted on purpose, because two normalisers give two different
answers to "is this the same finding". Call ``pipeline.norm_title``.
"""

from __future__ import annotations

from dataclasses import dataclass

from octop.infra.db.pool import DatabasePool
from octop.infra.db.repos._base import DbRow, map_rows, now_ts

FINDING_SEVERITIES = ("low", "medium", "high", "blocker")
FINDING_STATUSES = ("open", "fixed", "waived")
FINDING_VERDICTS = ("pass", "needs_revision", "reject")


@dataclass(frozen=True)
class ProjectTaskFindingRow:
    pk: int
    finding_id: str
    task_id: str
    run_id: str | None
    round: int
    severity: str
    title: str
    detail: str
    verdict: str | None
    status: str
    created_at: int

    @classmethod
    def from_row(cls, r: DbRow) -> ProjectTaskFindingRow:
        return cls(
            pk=int(r["id"]),
            finding_id=str(r["finding_id"]),
            task_id=str(r["task_id"]),
            run_id=(str(r["run_id"]) if r["run_id"] is not None else None),
            round=int(r["round"]),
            severity=str(r["severity"]),
            title=str(r["title"]),
            detail=str(r["detail"]),
            verdict=(str(r["verdict"]) if r["verdict"] is not None else None),
            status=str(r["status"]),
            created_at=int(r["created_at"]),
        )


class ProjectTaskFindingRepo:
    def __init__(self, db: DatabasePool) -> None:
        self._db = db

    def insert(
        self,
        *,
        finding_id: str,
        task_id: str,
        severity: str,
        title: str,
        run_id: str | None = None,
        round: int = 1,
        detail: str = "",
        verdict: str | None = None,
        status: str = "open",
    ) -> ProjectTaskFindingRow:
        with self._db.transaction() as conn:
            conn.execute(
                "INSERT INTO project_task_findings("
                "finding_id, task_id, run_id, round, severity, title, detail, verdict,"
                " status, created_at"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    finding_id,
                    task_id,
                    run_id,
                    round,
                    severity,
                    title,
                    detail,
                    verdict,
                    status,
                    now_ts(),
                ),
            )
        row = self.get(finding_id)
        if row is None:
            raise RuntimeError(f"finding insert failed: {finding_id}")
        return row

    def get(self, finding_id: str) -> ProjectTaskFindingRow | None:
        with self._db.connect() as conn:
            r = conn.execute(
                "SELECT * FROM project_task_findings WHERE finding_id = ?", (finding_id,)
            ).fetchone()
        return ProjectTaskFindingRow.from_row(r) if r is not None else None

    def list_by_task(self, task_id: str) -> list[ProjectTaskFindingRow]:
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM project_task_findings WHERE task_id = ? ORDER BY round ASC, id ASC",
                (task_id,),
            ).fetchall()
        return map_rows(rows, ProjectTaskFindingRow)

    def list_by_run(self, run_id: str) -> list[ProjectTaskFindingRow]:
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM project_task_findings WHERE run_id = ? ORDER BY id ASC",
                (run_id,),
            ).fetchall()
        return map_rows(rows, ProjectTaskFindingRow)
