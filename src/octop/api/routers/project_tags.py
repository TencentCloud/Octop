"""HTTP API for project tags (PLAN.md §4).

Thin layer: validate the request shape, call :class:`ProjectTagService`, map the
result. Every route is gated by the coarse ``projects`` permission key; the
per-project role check lives in the service, so there is exactly one permission
implementation (``assert_project_role``).

The tag set of a task is *replaced* wholesale by ``PUT …/tasks/{tid}/tags`` so a
client never has to compute add/remove deltas.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from octop.api.deps import get_server, require_permission
from octop.infra.db.repos._base import UNSET
from octop.infra.db.repos.project_tags import ProjectTagRow
from octop.infra.projects.service import ProjectActor
from octop.infra.projects.tags import ProjectTagService
from octop.infra.server import OctopServer
from octop.infra.users.identity import User

router = APIRouter(prefix="/projects")


# ── request / response models ────────────────────────────────────────────────


class TagOut(BaseModel):
    tag_id: str
    name: str
    color: str
    created_at: int

    @classmethod
    def of(cls, row: ProjectTagRow) -> TagOut:
        return cls(
            tag_id=row.tag_id,
            name=row.name,
            color=row.color,
            created_at=row.created_at,
        )


class TagCreate(BaseModel):
    name: str = Field(min_length=1, description="Tag name, unique inside the project.")
    color: str = Field(default="", description="Empty, or an opaque '#RRGGBB'.")


class TagPatch(BaseModel):
    name: str | None = Field(default=None, description="New name; omit to keep it.")
    color: str | None = Field(default=None, description="New colour; omit to keep it.")


class TaskTagsPut(BaseModel):
    tags: list[str] = Field(
        default_factory=list,
        description="The task's complete tag set; an omitted tag is detached.",
    )


class TaskTagsOut(BaseModel):
    task_id: str
    tags: list[TagOut]


# ── helpers ──────────────────────────────────────────────────────────────────


def _service(server: OctopServer) -> ProjectTagService:
    assert server.services is not None
    return ProjectTagService(server.services)


def _actor(user: User) -> ProjectActor:
    """``User`` already satisfies :class:`ProjectActor`; this keeps mypy honest."""
    return user


# ── tag definitions ──────────────────────────────────────────────────────────


@router.get("/{project_id}/tags", summary="List a project's tag definitions")
async def list_tags(
    project_id: str,
    server: OctopServer = Depends(get_server),
    user: User = Depends(require_permission("projects")),
) -> list[TagOut]:
    rows = _service(server).list_tags(project_id, user=_actor(user))
    return [TagOut.of(row) for row in rows]


@router.post(
    "/{project_id}/tags",
    summary="Create a tag definition",
    status_code=status.HTTP_201_CREATED,
)
async def create_tag(
    project_id: str,
    body: TagCreate,
    server: OctopServer = Depends(get_server),
    user: User = Depends(require_permission("projects")),
) -> TagOut:
    """``name`` is unique per project; a duplicate is ``PROJECT_TASK_TAG_INVALID``."""
    row = _service(server).create_tag(
        project_id,
        user=_actor(user),
        name=body.name,
        color=body.color,
    )
    return TagOut.of(row)


@router.patch("/{project_id}/tags/{tag_id}", summary="Rename or recolour a tag")
async def patch_tag(
    project_id: str,
    tag_id: str,
    body: TagPatch,
    server: OctopServer = Depends(get_server),
    user: User = Depends(require_permission("projects")),
) -> TagOut:
    """Omitted fields are left alone; an empty ``color`` clears the colour."""
    service = _service(server)
    row = service.update_tag(
        project_id,
        tag_id,
        user=_actor(user),
        name=body.name if body.name is not None else UNSET,
        color=body.color if body.color is not None else UNSET,
    )
    return TagOut.of(row)


@router.delete("/{project_id}/tags/{tag_id}", summary="Delete a tag definition")
async def delete_tag(
    project_id: str,
    tag_id: str,
    server: OctopServer = Depends(get_server),
    user: User = Depends(require_permission("projects")),
) -> dict[str, bool]:
    """Links on tasks disappear with the definition (``ON DELETE CASCADE``)."""
    deleted = _service(server).delete_tag(project_id, tag_id, user=_actor(user))
    return {"deleted": deleted}


# ── task links ───────────────────────────────────────────────────────────────


@router.put("/{project_id}/tasks/{task_id}/tags", summary="Replace a task's tags")
async def put_task_tags(
    project_id: str,
    task_id: str,
    body: TaskTagsPut,
    server: OctopServer = Depends(get_server),
    user: User = Depends(require_permission("projects")),
) -> TaskTagsOut:
    """The body is the task's **whole** tag set, not a delta.

    Every id must name a tag of this project; a tag from another project is
    rejected exactly like an unknown one. Sending the same tag twice in one
    request is rejected rather than silently collapsed.
    """
    rows = _service(server).set_task_tags(
        project_id,
        task_id,
        user=_actor(user),
        tag_ids=body.tags,
    )
    return TaskTagsOut(task_id=task_id, tags=[TagOut.of(row) for row in rows])
