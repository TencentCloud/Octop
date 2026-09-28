"""Project skill declarations — ``project_skills``.

The table records **which skills a project declares for which member agent**
(PLAN.md §2.1). The key is ``(project_id, agent_id, skill_slug)`` and not
``(project_id, skill_slug)``, because a slug is only unique *inside one agent's
workspace*: two agents may each own a different skill called ``report``.

This module is SQL only. The projection rule ("a declaration must be a subset of
what the agent actually has installed"), the effective/stale split, and every
permission check live in :mod:`octop.infra.projects.skills`.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from octop.infra.db.pool import DatabasePool
from octop.infra.db.repos._base import (
    DbRow,
    map_rows,
    now_ts,
    sql_in_placeholders,
)


@dataclass(frozen=True)
class ProjectSkillRow:
    pk: int
    project_id: str
    agent_id: str
    skill_slug: str
    created_by: int
    created_at: int

    @classmethod
    def from_row(cls, r: DbRow) -> ProjectSkillRow:
        return cls(
            pk=int(r["id"]),
            project_id=str(r["project_id"]),
            agent_id=str(r["agent_id"]),
            skill_slug=str(r["skill_slug"]),
            created_by=int(r["created_by"]),
            created_at=int(r["created_at"]),
        )


class ProjectSkillRepo:
    def __init__(self, db: DatabasePool) -> None:
        self._db = db

    # ── reads ────────────────────────────────────────────────────────────────

    def get(self, project_id: str, agent_id: str, skill_slug: str) -> ProjectSkillRow | None:
        with self._db.connect() as conn:
            r = conn.execute(
                "SELECT * FROM project_skills "
                "WHERE project_id = ? AND agent_id = ? AND skill_slug = ?",
                (project_id, agent_id, skill_slug),
            ).fetchone()
        return ProjectSkillRow.from_row(r) if r else None

    def list_by_project(self, project_id: str) -> list[ProjectSkillRow]:
        """Declarations in stable order (``agent_id`` then ``skill_slug``)."""
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM project_skills WHERE project_id = ? "
                "ORDER BY agent_id, skill_slug, id",
                (project_id,),
            ).fetchall()
        return map_rows(rows, ProjectSkillRow)

    def list_by_agent(self, project_id: str, agent_id: str) -> list[ProjectSkillRow]:
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM project_skills WHERE project_id = ? AND agent_id = ? "
                "ORDER BY skill_slug, id",
                (project_id, agent_id),
            ).fetchall()
        return map_rows(rows, ProjectSkillRow)

    def count_by_project(self, project_id: str) -> int:
        with self._db.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM project_skills WHERE project_id = ?",
                (project_id,),
            ).fetchone()
        return int(row["c"]) if row else 0

    # ── writes ───────────────────────────────────────────────────────────────

    def set_project_skills(
        self,
        project_id: str,
        entries: Sequence[tuple[str, str]],
        *,
        created_by: int,
    ) -> list[ProjectSkillRow]:
        """Replace the project's declarations with exactly ``entries``.

        The delete and the inserts share one transaction so a reader never sees a
        project whose declarations were cleared but not yet rewritten — the same
        reason ``set_task_values`` is written this way.
        """
        wanted = list(dict.fromkeys((str(agent_id), str(slug)) for agent_id, slug in entries))
        ts = now_ts()
        with self._db.transaction() as conn:
            existing = {
                (str(r["agent_id"]), str(r["skill_slug"]))
                for r in conn.execute(
                    "SELECT agent_id, skill_slug FROM project_skills WHERE project_id = ?",
                    (project_id,),
                ).fetchall()
            }
            drop = sorted(existing - set(wanted))
            for agent_id, slug in drop:
                conn.execute(
                    "DELETE FROM project_skills "
                    "WHERE project_id = ? AND agent_id = ? AND skill_slug = ?",
                    (project_id, agent_id, slug),
                )
            for agent_id, slug in wanted:
                if (agent_id, slug) in existing:
                    continue
                conn.execute(
                    "INSERT INTO project_skills("
                    "project_id, agent_id, skill_slug, created_by, created_at"
                    ") VALUES (?, ?, ?, ?, ?)",
                    (project_id, agent_id, slug, created_by, ts),
                )
        return self.list_by_project(project_id)

    def delete(self, project_id: str, agent_id: str, skill_slug: str) -> bool:
        with self._db.transaction() as conn:
            cur = conn.execute(
                "DELETE FROM project_skills "
                "WHERE project_id = ? AND agent_id = ? AND skill_slug = ?",
                (project_id, agent_id, skill_slug),
            )
        return bool(cur.rowcount)

    def count_for_agents(self, project_id: str, agent_ids: Iterable[str]) -> dict[str, int]:
        """Declarations per agent, in one ``IN`` query (never one per agent)."""
        ids = list(dict.fromkeys(str(a) for a in agent_ids))
        if not ids:
            return {}
        sql = (
            "SELECT agent_id, COUNT(*) AS c FROM project_skills "
            f"WHERE project_id = ? AND agent_id IN ({sql_in_placeholders(len(ids))}) "
            "GROUP BY agent_id"
        )
        with self._db.connect() as conn:
            rows = conn.execute(sql, (project_id, *ids)).fetchall()
        grouped = dict.fromkeys(ids, 0)
        for r in rows:
            grouped[str(r["agent_id"])] = int(r["c"])
        return grouped
