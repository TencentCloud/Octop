"""HTTP surface for project-owned cron jobs (PLAN.md §3.3).

Four routes: list (own jobs only, with the prompt redacted for anything else),
create, edit/enable, delete. ``DELETE`` answers ``{"deleted": true}`` — the same
key name as every other delete route in this domain.

`tags` / mount registration belong to the integration task (T-INT2); each handler
carries its own ``summary``, typed ``response_model`` and permission gate.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from octop.api.deps import get_server, require_permission
from octop.infra.projects.cron import ProjectCronService
from octop.infra.server import OctopServer
from octop.infra.users.identity import User

router = APIRouter(prefix="/projects")


class ProjectCronJobOut(BaseModel):
    """One project-owned cron job.

    ``prompt`` is the plaintext column: it is only ever populated for a job the
    **caller** created. ``prompt_hidden`` marks the redacted case, and
    ``agent_running`` flags a stopped executor without hiding the row (S4).
    """

    cron_id: str
    name: str
    agent_id: str
    schedule_spec: str
    enabled: bool
    last_run_at: int | None
    last_status: str | None
    owned_by_me: bool = Field(description="False only for a defensive-invariant row.")
    prompt: str | None = Field(description="Null whenever the job is not the caller's.")
    prompt_hidden: bool
    agent_running: bool = Field(description="False when the executor agent is stopped.")


class ProjectCronCreate(BaseModel):
    name: str | None = Field(default=None, description="Display name; derived when omitted.")
    agent_id: str = Field(min_length=1, description="Executor; must be a project member agent.")
    schedule_spec: str = Field(min_length=1, description="Cron syntax or @every alias.")
    prompt: str = Field(min_length=1, description="What the job should do each run.")
    enabled: bool = True


class ProjectCronPatch(BaseModel):
    name: str | None = None
    schedule_spec: str | None = None
    prompt: str | None = None
    enabled: bool | None = Field(default=None, description="Start / stop the job.")


def _service(server: OctopServer) -> ProjectCronService:
    assert server.services is not None
    runtime = getattr(server, "app_runtime", None)
    registry = getattr(runtime, "agent_registry", None)
    return ProjectCronService(server.services, agent_registry=registry)


@router.get(
    "/{project_id}/cron",
    summary="List a project's cron jobs",
    response_model=list[ProjectCronJobOut],
)
async def list_project_cron(
    project_id: str,
    server: OctopServer = Depends(get_server),
    user: User = Depends(require_permission("projects")),
) -> list[ProjectCronJobOut]:
    """The caller's own jobs on this project, newest first.

    Another user's job never appears here; if one ever did, its ``prompt`` would be
    null with ``prompt_hidden=true``.
    """
    jobs = _service(server).list_jobs(project_id, user=user)
    return [ProjectCronJobOut(**job) for job in jobs]


@router.post(
    "/{project_id}/cron",
    summary="Schedule a cron job on a project",
    status_code=status.HTTP_201_CREATED,
    response_model=ProjectCronJobOut,
)
async def create_project_cron(
    project_id: str,
    body: ProjectCronCreate,
    server: OctopServer = Depends(get_server),
    user: User = Depends(require_permission("projects")),
) -> ProjectCronJobOut:
    """Create a job owned by the caller; the executor must be a member agent."""
    job = _service(server).create_job(
        project_id,
        user=user,
        name=body.name,
        agent_id=body.agent_id,
        schedule_spec=body.schedule_spec,
        prompt=body.prompt,
        enabled=body.enabled,
    )
    return ProjectCronJobOut(**job)


@router.patch("/{project_id}/cron/{cron_id}", summary="Edit or toggle a project cron job")
async def patch_project_cron(
    project_id: str,
    cron_id: str,
    body: ProjectCronPatch,
    server: OctopServer = Depends(get_server),
    user: User = Depends(require_permission("projects")),
) -> ProjectCronJobOut:
    """Edit fields or flip ``enabled``. Only the job's own creator may do this."""
    job = _service(server).update_job(
        project_id,
        cron_id,
        user=user,
        name=body.name,
        schedule_spec=body.schedule_spec,
        prompt=body.prompt,
        enabled=body.enabled,
    )
    return ProjectCronJobOut(**job)


@router.delete("/{project_id}/cron/{cron_id}", summary="Delete a project cron job")
async def delete_project_cron(
    project_id: str,
    cron_id: str,
    server: OctopServer = Depends(get_server),
    user: User = Depends(require_permission("projects")),
) -> dict[str, Any]:
    """Delete the job. Only its creator may; the owner/admin cannot take it over."""
    deleted = _service(server).delete_job(project_id, cron_id, user=user)
    return {"deleted": deleted}
