"""Project-owned cron jobs — execution subject, visibility, and writability.

Contract: PLAN.md §3 (frozen).

* **Execution subject = an agent** (candidate ①): ``project_id`` is *ownership
  only*; the job runs through its ``agent_id``, which must be a project-member
  agent. A stopped agent is still listed (S4) — annotated, never hidden.
* **Visibility = me**: the project list only returns jobs the caller created for
  that project. ``owned_by_me`` / ``prompt_hidden`` are a **defensive invariant**
  on top: even if a foreign row ever reaches the response builder, its plaintext
  ``prompt`` is never serialized.
* **Writability = me** (FIND-4): editing/enabling/deleting is limited to
  ``job.user_id == caller`` — the owner and admins cannot touch someone else's job.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

from octop.infra.db.repos.cron import CronJobRepo, CronJobRow
from octop.infra.db.services import SharedServices
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.gateway.threads import ThreadRegistry
from octop.infra.projects.service import (
    PROJECT_MANAGE_CONFIG,
    PROJECT_READ,
    ProjectActor,
    ProjectService,
)

logger = logging.getLogger(__name__)

#: Cron jobs live under the dashboard session key unless the caller pins one.
CRON_CHANNEL_TYPE = "cron"


class AgentRunner(Protocol):
    """The slice of the agent registry this service needs (running state only)."""

    def get_agent(self, agent_id: str) -> Any: ...


def _cron_invalid(message: str) -> OctopError:
    return OctopError(ErrorCode.PROJECT_CRON_INVALID, message)


def new_cron_id() -> str:
    from octop.infra.utils.ulid import new_ulid  # noqa: PLC0415 - cycle-safe

    return f"cron_{new_ulid()}"


class ProjectCronService:
    def __init__(
        self,
        services: SharedServices,
        *,
        project_service: ProjectService | None = None,
        agent_registry: AgentRunner | None = None,
        cron_repo: CronJobRepo | None = None,
    ) -> None:
        self._services = services
        self._projects = project_service or ProjectService(services)
        self._registry = agent_registry
        self._jobs = cron_repo or services.cron_repo

    # ── membership / running state ───────────────────────────────────────────

    def member_agents(self, project_id: str) -> set[str]:
        """Agent subjects of ``project_members`` — the only dispatchable executors."""
        return {
            row.subject_id
            for row in self._services.project_member_repo.list_by_project(project_id)
            if row.subject_type == "agent"
        }

    def _agent_running(self, agent_id: str) -> bool:
        """S4: a stopped agent is a *label*, never an error."""
        if self._registry is None:
            return False
        try:
            self._registry.get_agent(agent_id)
        except Exception:  # noqa: BLE001 - any registry failure means "not running"
            return False
        return True

    def assert_dispatchable(self, project_id: str, agent_id: str) -> None:
        if agent_id not in self.member_agents(project_id):
            raise _cron_invalid(f"Agent {agent_id!r} is not an agent member of this project.")

    # ── serialization (defensive invariant lives here) ───────────────────────

    def serialize_job(self, job: CronJobRow, *, user_id: int) -> dict[str, Any]:
        """One job as the project surface exposes it.

        Public and pure so the defensive invariant is testable **without** the
        list filter: ``owned_by_me`` is computed per row, and a row owned by
        somebody else has ``prompt=None`` + ``prompt_hidden=True`` — no prefix, no
        echo, no exception.
        """
        owned = job.user_id == user_id
        return {
            "cron_id": job.cron_id,
            # ``name`` is withheld for a foreign row as well: the repo derives it from
            # the prompt (``default_cron_name``) when the caller omitted one, so a
            # prompt-derived label would re-echo the very text being redacted.
            "name": job.name if owned else "",
            "agent_id": job.agent_id,
            "schedule_spec": job.trigger,
            "enabled": bool(job.enabled),
            "last_run_at": job.last_run_at,
            "last_status": job.last_status,
            "owned_by_me": owned,
            "prompt": job.prompt if owned else None,
            "prompt_hidden": not owned,
            "agent_running": self._agent_running(job.agent_id),
        }

    # ── reads ────────────────────────────────────────────────────────────────

    def list_jobs(self, project_id: str, *, user: ProjectActor) -> list[dict[str, Any]]:
        """Main behaviour: the project list contains **only the caller's own jobs**."""
        self._projects.assert_project_role(project_id, user=user, required=PROJECT_READ)
        members = self.member_agents(project_id)
        jobs = [
            job
            for job in self._jobs.list_by_project(project_id, user_id=user.id)
            if job.agent_id in members
        ]
        return [self.serialize_job(job, user_id=user.id) for job in jobs]

    # ── writes ───────────────────────────────────────────────────────────────

    def create_job(
        self,
        project_id: str,
        *,
        user: ProjectActor,
        name: str | None,
        agent_id: str,
        schedule_spec: str,
        prompt: str,
        enabled: bool = True,
    ) -> dict[str, Any]:
        """Mount a new job onto the project, owned by the caller."""
        self._projects.assert_project_role(project_id, user=user, required=PROJECT_MANAGE_CONFIG)
        self.assert_dispatchable(project_id, agent_id)
        cron_id = new_cron_id()
        self._jobs.create(
            cron_id=cron_id,
            agent_id=agent_id,
            user_id=user.id,
            trigger=schedule_spec,
            prompt=prompt,
            session_key=ThreadRegistry.dashboard_key(agent_id=agent_id, user_id=user.id),
            enabled=enabled,
            name=name,
            project_id=project_id,
        )
        job = self._jobs.get(cron_id)
        if job is None:  # pragma: no cover - insert just succeeded
            raise _cron_invalid("The cron job could not be created.")
        return self.serialize_job(job, user_id=user.id)

    def update_job(
        self,
        project_id: str,
        cron_id: str,
        *,
        user: ProjectActor,
        name: str | None = None,
        schedule_spec: str | None = None,
        prompt: str | None = None,
        enabled: bool | None = None,
    ) -> dict[str, Any]:
        """Edit / enable / disable — only the caller's own job (FIND-4)."""
        self._projects.assert_project_role(project_id, user=user, required=PROJECT_MANAGE_CONFIG)
        job = self._require_own_job(project_id, cron_id, user=user)
        self._jobs.update(
            job.cron_id,
            name=name,
            trigger=schedule_spec,
            prompt=prompt,
            enabled=enabled,
        )
        refreshed = self._jobs.get(job.cron_id) or job
        return self.serialize_job(refreshed, user_id=user.id)

    def delete_job(self, project_id: str, cron_id: str, *, user: ProjectActor) -> bool:
        """Delete — only the caller's own job (FIND-4)."""
        self._projects.assert_project_role(project_id, user=user, required=PROJECT_MANAGE_CONFIG)
        job = self._require_own_job(project_id, cron_id, user=user)
        self._jobs.delete(job.cron_id)
        return True

    # ── internals ────────────────────────────────────────────────────────────

    def _require_own_job(self, project_id: str, cron_id: str, *, user: ProjectActor) -> CronJobRow:
        """404 for a job outside this project; 403 when it belongs to somebody else."""
        job = self._jobs.get(cron_id)
        if job is None or job.project_id != project_id:
            raise OctopError(ErrorCode.PROJECT_NOT_FOUND, "Project not found.")
        if job.user_id != user.id:
            raise OctopError(
                ErrorCode.PROJECT_FORBIDDEN,
                "This cron job belongs to another user.",
            )
        return job
