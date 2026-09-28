"""HTTP API for project skill declarations (PLAN.md §2.3).

Thin layer: validate the request shape, call :class:`ProjectSkillService`, map
the result. The coarse ``projects`` permission key gates the routes; the
per-project role check lives in the service (``PROJECT_READ`` to read,
``PROJECT_MANAGE_CONFIG`` to write), so there is exactly one permission
implementation.

``GET`` returns the two sides of the Q9 invariant: ``effective`` (declared *and*
installed) and ``stale`` (declared but no longer installed, shown greyed out and
never auto-deleted).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from octop.api.deps import get_server, require_permission
from octop.infra.projects.service import ProjectActor
from octop.infra.projects.skills import ProjectSkillService
from octop.infra.server import OctopServer
from octop.infra.users.identity import User

router = APIRouter(prefix="/projects")


# ── request / response models ────────────────────────────────────────────────


class ProjectSkillDeclaration(BaseModel):
    agent_id: str = Field(min_length=1, description="Member agent that has the skill.")
    skill_slug: str = Field(min_length=1, description="Skill slug, unique per agent.")


class ProjectSkillsPut(BaseModel):
    skills: list[ProjectSkillDeclaration] = Field(
        default_factory=list,
        description="The project's complete declaration set; an omitted skill is removed.",
    )


class EffectiveSkillOut(BaseModel):
    agent_id: str
    skill_slug: str
    display_name: str
    kind: str = Field(description="workspace | package")


class StaleSkillOut(BaseModel):
    agent_id: str
    skill_slug: str
    reason: str = Field(description="Why the declaration is not effective.")


class ProjectSkillsOut(BaseModel):
    effective: list[EffectiveSkillOut] = Field(
        default_factory=list, description="Declared and currently installed."
    )
    stale: list[StaleSkillOut] = Field(
        default_factory=list,
        description="Declared but no longer installed; kept until the user removes it.",
    )


# ── helpers ──────────────────────────────────────────────────────────────────


def _service(server: OctopServer) -> ProjectSkillService:
    assert server.services is not None
    runtime = server.app_runtime
    return ProjectSkillService(
        server.services,
        agent_manager=runtime.agent_registry if runtime is not None else None,
    )


def _actor(user: User) -> ProjectActor:
    """``User`` already satisfies :class:`ProjectActor`; this keeps mypy honest."""
    return user


def _to_out(payload: dict[str, list[dict[str, object]]]) -> ProjectSkillsOut:
    return ProjectSkillsOut(
        effective=[EffectiveSkillOut(**row) for row in payload["effective"]],  # type: ignore[arg-type]
        stale=[StaleSkillOut(**row) for row in payload["stale"]],  # type: ignore[arg-type]
    )


# ── routes ───────────────────────────────────────────────────────────────────


@router.get(
    "/{project_id}/skills",
    summary="List a project's declared skills",
    tags=["projects"],
    response_model=ProjectSkillsOut,
)
async def list_project_skills(
    project_id: str,
    server: OctopServer = Depends(get_server),
    user: User = Depends(require_permission("projects")),
) -> ProjectSkillsOut:
    """Returns effective and stale declarations — ``stale`` is computed, not stored."""
    payload = await _service(server).list_project_skills(project_id, user=_actor(user))
    return _to_out(payload)


@router.put(
    "/{project_id}/skills",
    summary="Replace a project's declared skills",
    tags=["projects"],
    response_model=ProjectSkillsOut,
)
async def put_project_skills(
    project_id: str,
    body: ProjectSkillsPut,
    server: OctopServer = Depends(get_server),
    user: User = Depends(require_permission("projects")),
) -> ProjectSkillsOut:
    """The body is the project's **whole** declaration set, not a delta.

    Every entry must be installed on that agent (Q9) and the agent must be a
    project member; otherwise ``PROJECT_SKILL_INVALID`` (409). A declaration that
    has since gone stale cannot be re-submitted as-is — it must be dropped or the
    skill must be installed again.
    """
    payload = await _service(server).set_project_skills(
        project_id,
        user=_actor(user),
        entries=[entry.model_dump() for entry in body.skills],
    )
    return _to_out(payload)
