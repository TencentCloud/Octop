"""Project skill declarations: the Q9 projection and its enumeration closure.

``project_skills`` stores *declarations*. A declaration is only meaningful as a
**subset of what the agent actually has installed** (PLAN.md §2, "Q9"), so this
module owns two things that must never drift apart:

* :meth:`ProjectSkillService.list_installed` — the three-layer enumeration;
* the effective/stale split and the write-side refusal built on it.

**The enumeration closure is the point of this module.** Neither built-in path
covers the contract alone:

1. the runtime path (``AgentManager.list_skill_summaries``) knows about mounted
   skill packages but needs a *loaded* agent;
2. the offline path scans the workspace only — it runs for a stopped agent but
   would never see a package's skills.

So layer 1 is tried first, and on ``AGENT_NOT_RUNNING`` / ``AGENT_FAILED`` we
fall back to the workspace scan **with the agent's package directories added to
the scan roots**. Without that last part a project could declare a
package-provided skill that the picker can never offer, which is exactly how the
previous dead schema (``project_rooms``) came to exist.

Package resolution is deliberately delegated: the directories come from
``AgentManager.resolve_skill_package_dirs``, a thin wrapper over the existing
private resolver (FIND-5 forbids a second package→directory implementation).
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from typing import Any

from octop.infra.agents.manager import AgentManager, skills_disabled_set
from octop.infra.db.repos.project_skills import ProjectSkillRepo, ProjectSkillRow
from octop.infra.db.repos.projects import MEMBER_SUBJECT_AGENT
from octop.infra.db.services import SharedServices
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.projects.service import (
    PROJECT_MANAGE_CONFIG,
    PROJECT_READ,
    ProjectActor,
    ProjectService,
)
from octop.infra.skills.workspace_catalog import list_workspace_skill_summaries

logger = logging.getLogger(__name__)

#: Raised when a declaration cannot be proven installed. One code, one meaning:
#: the caller asked for a skill the agent does not have (PLAN.md §12).
SKILL_INVALID = ErrorCode.PROJECT_SKILL_INVALID


def _skill_invalid(message: str) -> OctopError:
    return OctopError(SKILL_INVALID, message)


def _normalize_installed(row: Mapping[str, Any]) -> dict[str, Any]:
    """One enumerator row in the public shape (PLAN.md §2.2)."""
    slug = str(row.get("slug") or "").strip()
    return {
        "slug": slug,
        "display_name": str(row.get("name") or slug),
        "kind": str(row.get("kind") or "workspace"),
        "enabled": bool(row.get("enabled", True)),
    }


class ProjectSkillService:
    """Declarations for one project, and the enumeration they must be a subset of."""

    def __init__(
        self,
        services: SharedServices,
        *,
        project_service: ProjectService | None = None,
        agent_manager: AgentManager | None = None,
        skill_repo: ProjectSkillRepo | None = None,
    ) -> None:
        self._services = services
        self._projects = (
            project_service if project_service is not None else ProjectService(services)
        )
        self._agents = agent_manager
        # Injectable so a caller (or a test) can supply the repo without the
        # service registry having been wired yet; T-INT2 owns that registration.
        self._skills = skill_repo if skill_repo is not None else services.project_skill_repo

    # ── layer 1-3: the enumeration closure ───────────────────────────────────

    async def list_installed(self, agent_id: str) -> list[dict[str, Any]]:
        """Skills ``agent_id`` actually has, as ``{slug, display_name, kind, enabled}``.

        Layer 1 asks the running agent (packages included). If the agent is not
        loaded we fall back to the offline scan, which is only equivalent once the
        package roots are part of it — hence layer 3.
        """
        manager = self._agents
        if manager is None:
            # No runtime to ask and no way to resolve package dirs: nothing can
            # be proven installed. Returning empty keeps the Q9 invariant
            # (effective ⊆ installed) true, and makes writes fail closed.
            logger.info("no agent manager available; %s has no provable skills", agent_id)
            return []

        try:
            runtime_rows = await manager.list_skill_summaries(agent_id)
        except OctopError as exc:
            if exc.code not in (ErrorCode.AGENT_NOT_RUNNING, ErrorCode.AGENT_FAILED):
                raise
            logger.debug("agent %s not running (%s); falling back offline", agent_id, exc.code)
        else:
            return [_normalize_installed(row) for row in runtime_rows]

        return self._list_installed_offline(manager, agent_id)

    def _list_installed_offline(self, manager: AgentManager, agent_id: str) -> list[dict[str, Any]]:
        """Layer 2+3: workspace scan **with mounted package roots**.

        Everything here reads persisted state only, so it works for a stopped
        agent. ``package_dirs`` is what makes package-provided skills visible;
        the package roots are scanned first, so a slug present in both a package
        and the workspace resolves to the package (S3).
        """
        cfg = manager.get_config(agent_id)
        workspace_dir = manager.resolve_workspace_dir(agent_id)
        package_dirs = manager.resolve_skill_package_dirs(agent_id)
        rows = list_workspace_skill_summaries(
            workspace_dir,
            skills_disabled=skills_disabled_set(cfg),
            package_dirs=package_dirs,
        )
        return [_normalize_installed(row) for row in rows]

    async def installed_slugs(self, agent_id: str) -> set[str]:
        return {row["slug"] for row in await self.list_installed(agent_id) if row["slug"]}

    # ── reads ────────────────────────────────────────────────────────────────

    async def list_project_skills(
        self, project_id: str, *, user: ProjectActor
    ) -> dict[str, list[dict[str, Any]]]:
        """``{"effective": [...], "stale": [...]}``.

        ``stale`` is *computed*, never stored: a declaration whose skill is no
        longer installed stays in the table (the user is told) until they remove
        it or the skill comes back (PLAN.md §2.3).
        """
        self._projects.assert_project_role(project_id, user=user, required=PROJECT_READ)
        rows = self._skills.list_by_project(project_id)
        return await self._split_effective(rows)

    async def _split_effective(
        self, rows: Sequence[ProjectSkillRow]
    ) -> dict[str, list[dict[str, Any]]]:
        installed = await self._installed_by_agent([row.agent_id for row in rows])
        effective: list[dict[str, Any]] = []
        stale: list[dict[str, Any]] = []
        for row in rows:
            match = installed.get(row.agent_id, {}).get(row.skill_slug)
            if match is None:
                stale.append(
                    {
                        "agent_id": row.agent_id,
                        "skill_slug": row.skill_slug,
                        "reason": "not_installed",
                    }
                )
                continue
            effective.append(
                {
                    "agent_id": row.agent_id,
                    "skill_slug": row.skill_slug,
                    "display_name": match["display_name"],
                    "kind": match["kind"],
                }
            )
        return {"effective": effective, "stale": stale}

    async def _installed_by_agent(
        self, agent_ids: Sequence[str]
    ) -> dict[str, dict[str, dict[str, Any]]]:
        """``{agent_id: {slug: row}}`` — one enumeration per distinct agent."""
        out: dict[str, dict[str, dict[str, Any]]] = {}
        for agent_id in dict.fromkeys(str(a) for a in agent_ids):
            out[agent_id] = {row["slug"]: row for row in await self.list_installed(agent_id)}
        return out

    # ── writes ───────────────────────────────────────────────────────────────

    async def set_project_skills(
        self,
        project_id: str,
        *,
        user: ProjectActor,
        entries: Sequence[Mapping[str, Any]],
    ) -> dict[str, list[dict[str, Any]]]:
        """Full replacement. Every entry must be provably installed.

        A declaration that is not in ``list_installed(agent_id)`` is refused with
        ``PROJECT_SKILL_INVALID`` (409). That *includes* re-submitting an entry
        that is already stored but has since gone stale: a request may not
        persist a disconnected declaration, so the stale row has to be dropped or
        the skill has to come back first (PLAN.md §2.2/§2.3).
        """
        self._projects.assert_project_role(project_id, user=user, required=PROJECT_MANAGE_CONFIG)

        wanted: list[tuple[str, str]] = []
        for entry in entries:
            agent_id = str(entry.get("agent_id") or "").strip()
            slug = str(entry.get("skill_slug") or "").strip()
            if not agent_id or not slug:
                raise _skill_invalid("Each declaration needs both 'agent_id' and 'skill_slug'.")
            wanted.append((agent_id, slug))

        self._assert_agents_are_members(project_id, user=user, agent_ids=[a for a, _ in wanted])

        installed = await self._installed_by_agent([agent_id for agent_id, _ in wanted])
        for agent_id, slug in wanted:
            if slug not in installed.get(agent_id, {}):
                raise _skill_invalid(f"Skill '{slug}' is not installed on agent '{agent_id}'.")

        rows = self._skills.set_project_skills(project_id, wanted, created_by=user.id)
        return await self._split_effective(rows)

    async def validate_declarations(
        self, project_id: str, *, user: ProjectActor, entries: Sequence[Mapping[str, Any]]
    ) -> None:
        """Validate without writing — the same rules as :meth:`set_project_skills`.

        Exposed so a caller that writes declarations through another path (for
        example the project-create orchestration) can reuse this rule set instead
        of restating it; a second copy would be a second source of truth.
        """
        self._projects.assert_project_role(project_id, user=user, required=PROJECT_MANAGE_CONFIG)
        pairs = [
            (str(e.get("agent_id") or "").strip(), str(e.get("skill_slug") or "").strip())
            for e in entries
        ]
        self._assert_agents_are_members(project_id, user=user, agent_ids=[a for a, _ in pairs])
        installed = await self._installed_by_agent([agent_id for agent_id, _ in pairs])
        for agent_id, slug in pairs:
            if slug not in installed.get(agent_id, {}):
                raise _skill_invalid(f"Skill '{slug}' is not installed on agent '{agent_id}'.")

    # ── internals ────────────────────────────────────────────────────────────

    def _assert_agents_are_members(
        self, project_id: str, *, user: ProjectActor, agent_ids: Sequence[str]
    ) -> None:
        """Every ``agent_id`` must be an ``agent`` subject of this project."""
        distinct = list(dict.fromkeys(str(a) for a in agent_ids))
        if not distinct:
            return
        members = {
            str(member.subject_id)
            for member in self._projects.list_members(project_id, user=user)
            if member.subject_type == MEMBER_SUBJECT_AGENT
        }
        outsiders = [agent_id for agent_id in distinct if agent_id not in members]
        if outsiders:
            raise _skill_invalid(
                "These agents are not members of the project: " + ", ".join(sorted(outsiders))
            )
