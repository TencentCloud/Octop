"""HTTP API for projects, members, and the task board.

Thin layer: validate the request, call :class:`ProjectService`, map the result.
Every route is gated by the coarse ``projects`` permission key; the per-project
role check lives in the service (§4.6).

Note that ``DELETE /projects/{id}`` **archives** — that is the contract the plan
specifies, and it is why archiving is owner-only while the project row survives.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field

from octop.api.deps import get_server, require_permission
from octop.infra.db.repos.project_tasks import ProjectTaskRow, TimelineEventRow
from octop.infra.db.repos.projects import ProjectMemberRow, ProjectRow
from octop.infra.projects.service import ProjectActor, ProjectService
from octop.infra.server import OctopServer
from octop.infra.users.identity import User

router = APIRouter(prefix="/projects")


# ── response models ──────────────────────────────────────────────────────────


class ProjectOut(BaseModel):
    project_id: str = Field(description="Public project id (use this in URLs).")
    name: str
    goal: str
    status: str = Field(description="draft | active | paused | archived")
    owner_user_id: int
    memory_namespace: str = Field(description="Memory namespace owned by this project.")
    kb_id: str | None = Field(description="Knowledge base bound at creation time.")
    start_at: int | None
    due_at: int | None
    created_at: int
    updated_at: int

    @classmethod
    def of(cls, row: ProjectRow) -> ProjectOut:
        return cls(
            project_id=row.id,
            name=row.name,
            goal=row.goal,
            status=row.status,
            owner_user_id=row.owner_user_id,
            memory_namespace=row.memory_namespace,
            kb_id=row.kb_id,
            start_at=row.start_at,
            due_at=row.due_at,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


class MemberOut(BaseModel):
    subject_type: str = Field(description="user | agent | team")
    subject_id: str
    user_id: int | None
    role: str = Field(description="owner | admin | member | viewer")
    created_at: int

    @classmethod
    def of(cls, row: ProjectMemberRow) -> MemberOut:
        return cls(
            subject_type=row.subject_type,
            subject_id=row.subject_id,
            user_id=row.user_id,
            role=row.role,
            created_at=row.created_at,
        )


class TaskOut(BaseModel):
    task_id: str
    project_id: str
    parent_id: str | None
    title: str
    description: str
    status: str = Field(description="todo | doing | review | done | blocked | cancelled")
    assignee_type: str | None
    assignee_id: str | None
    priority: int
    deps: list[str]
    thread_id: str | None
    origin_node_id: str | None
    due_at: int | None
    sort_order: int
    created_by: int
    created_at: int
    updated_at: int

    @classmethod
    def of(cls, row: ProjectTaskRow) -> TaskOut:
        return cls(
            task_id=row.id,
            project_id=row.project_id,
            parent_id=row.parent_id,
            title=row.title,
            description=row.description,
            status=row.status,
            assignee_type=row.assignee_type,
            assignee_id=row.assignee_id,
            priority=row.priority,
            deps=list(row.deps),
            thread_id=row.thread_id,
            origin_node_id=row.origin_node_id,
            due_at=row.due_at,
            sort_order=row.sort_order,
            created_by=row.created_by,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


class TimelineEventOut(BaseModel):
    actor: str = Field(description="Actor reference, e.g. user:12.")
    action: str = Field(description="task.created | task.updated | task.status_changed | …")
    task_id: str | None
    payload: dict[str, Any]
    at: int

    @classmethod
    def of(cls, row: TimelineEventRow) -> TimelineEventOut:
        return cls(
            actor=row.actor,
            action=row.action,
            task_id=row.task_id,
            payload=row.payload,
            at=row.at,
        )


# ── request bodies ───────────────────────────────────────────────────────────


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, description="Project name; also names its knowledge base.")
    goal: str = Field(default="", description="What the project is meant to achieve.")
    start_at: int | None = Field(default=None, description="Planned start, unix seconds.")
    due_at: int | None = Field(default=None, description="Planned finish, unix seconds.")


class ProjectPatch(BaseModel):
    name: str | None = None
    goal: str | None = None
    status: str | None = Field(
        default=None,
        description="Move the project along its state machine (draft|active|paused|archived).",
    )
    start_at: int | None = None
    due_at: int | None = None
    clear_start_at: bool = Field(default=False, description="Set start_at to NULL.")
    clear_due_at: bool = Field(default=False, description="Set due_at to NULL.")


class MemberCreate(BaseModel):
    subject_type: str = Field(default="user", description="user | agent | team")
    subject_id: str = Field(min_length=1)
    role: str = Field(default="member", description="owner | admin | member | viewer")


class TaskCreate(BaseModel):
    title: str = Field(min_length=1)
    description: str = ""
    parent_id: str | None = None
    assignee_type: str | None = Field(default=None, description="user | agent | team")
    assignee_id: str | None = None
    priority: int = 0
    deps: list[str] = Field(default_factory=list)
    due_at: int | None = None


class TaskPatch(BaseModel):
    title: str | None = None
    description: str | None = None
    parent_id: str | None = None
    assignee_type: str | None = None
    assignee_id: str | None = None
    priority: int | None = None
    deps: list[str] | None = None
    due_at: int | None = None
    status: str | None = Field(
        default=None,
        description="Target status; routed through the task state machine.",
    )


# ── helpers ──────────────────────────────────────────────────────────────────


def _service(server: OctopServer) -> ProjectService:
    assert server.services is not None
    runtime = server.app_runtime
    return ProjectService(
        server.services,
        agent_manager=runtime.agent_registry if runtime is not None else None,
        gateway=runtime.gateway if runtime is not None else None,
    )


# ── projects ─────────────────────────────────────────────────────────────────


@router.get("", summary="List the projects I can see")
async def list_projects(
    server: OctopServer = Depends(get_server),
    user: User = Depends(require_permission("projects")),
) -> list[ProjectOut]:
    projects = _service(server).list_projects(user=_actor(user))
    return [ProjectOut.of(p) for p in projects]


@router.post("", summary="Create a project", status_code=status.HTTP_201_CREATED)
async def create_project(
    body: ProjectCreate,
    server: OctopServer = Depends(get_server),
    user: User = Depends(require_permission("projects")),
) -> ProjectOut:
    """Creates the project, its owner membership, and a knowledge base of the
    same name. If the knowledge base cannot be created or bound, the project is
    rolled back and nothing is left behind."""
    project = _service(server).create_project(
        owner_user=_actor(user),
        name=body.name,
        goal=body.goal,
        start_at=body.start_at,
        due_at=body.due_at,
    )
    return ProjectOut.of(project)


@router.get("/{project_id}", summary="Get one project")
async def get_project(
    project_id: str,
    server: OctopServer = Depends(get_server),
    user: User = Depends(require_permission("projects")),
) -> ProjectOut:
    return ProjectOut.of(_service(server).get_project(project_id, user=_actor(user)))


@router.patch("/{project_id}", summary="Edit a project or move its status")
async def patch_project(
    project_id: str,
    body: ProjectPatch,
    server: OctopServer = Depends(get_server),
    user: User = Depends(require_permission("projects")),
) -> ProjectOut:
    service = _service(server)
    actor = _actor(user)

    if body.status is not None:
        service.transition_project(project_id, user=actor, target=body.status)

    fields: dict[str, Any] = {}
    for key in ("name", "goal"):
        value = getattr(body, key)
        if value is not None:
            fields[key] = value
    for key, clear in (("start_at", body.clear_start_at), ("due_at", body.clear_due_at)):
        value = getattr(body, key)
        if clear:
            fields[key] = None
        elif value is not None:
            fields[key] = value

    if fields:
        service.update_project(project_id, user=actor, **fields)
    return ProjectOut.of(service.get_project(project_id, user=actor))


@router.delete("/{project_id}", summary="Archive a project (owner only)")
async def archive_project(
    project_id: str,
    server: OctopServer = Depends(get_server),
    user: User = Depends(require_permission("projects")),
) -> ProjectOut:
    """Archives rather than deletes: the project becomes read-only and keeps its
    tasks, timeline, and knowledge base. Only the owner may do this."""
    service = _service(server)
    actor = _actor(user)
    service.transition_project(project_id, user=actor, target="archived")
    return ProjectOut.of(service.get_project(project_id, user=actor))


# ── members ──────────────────────────────────────────────────────────────────


@router.get("/{project_id}/members", summary="List project members")
async def list_members(
    project_id: str,
    server: OctopServer = Depends(get_server),
    user: User = Depends(require_permission("projects")),
) -> list[MemberOut]:
    rows = _service(server).list_members(project_id, user=_actor(user))
    return [MemberOut.of(r) for r in rows]


@router.post(
    "/{project_id}/members",
    summary="Add a member or change a role",
    status_code=status.HTTP_201_CREATED,
)
async def add_member(
    project_id: str,
    body: MemberCreate,
    server: OctopServer = Depends(get_server),
    user: User = Depends(require_permission("projects")),
) -> MemberOut:
    """Idempotent per (subject_type, subject_id): adding an existing subject
    changes its role. The project owner must keep the owner role."""
    member = _service(server).add_member(
        project_id,
        user=_actor(user),
        subject_type=body.subject_type,
        subject_id=body.subject_id,
        role=body.role,
    )
    return MemberOut.of(member)


@router.delete("/{project_id}/members/{subject_type}/{subject_id}", summary="Remove a member")
async def remove_member(
    project_id: str,
    subject_type: str,
    subject_id: str,
    server: OctopServer = Depends(get_server),
    user: User = Depends(require_permission("projects")),
) -> dict[str, bool]:
    removed = _service(server).remove_member(
        project_id, user=_actor(user), subject_type=subject_type, subject_id=subject_id
    )
    return {"removed": removed}


# ── tasks ────────────────────────────────────────────────────────────────────


@router.get("/{project_id}/tasks", summary="List tasks (board source)")
async def list_tasks(
    project_id: str,
    status_filter: str | None = Query(
        default=None,
        alias="status",
        description="Return only tasks in this status column.",
    ),
    server: OctopServer = Depends(get_server),
    user: User = Depends(require_permission("projects")),
) -> list[TaskOut]:
    rows = _service(server).list_tasks(project_id, user=_actor(user), status=status_filter)
    return [TaskOut.of(r) for r in rows]


@router.post(
    "/{project_id}/tasks",
    summary="Create a task",
    status_code=status.HTTP_201_CREATED,
)
async def create_task(
    project_id: str,
    body: TaskCreate,
    server: OctopServer = Depends(get_server),
    user: User = Depends(require_permission("projects")),
) -> TaskOut:
    """New tasks always start in ``todo``; move them with PATCH."""
    task = _service(server).create_task(
        project_id,
        user=_actor(user),
        title=body.title,
        description=body.description,
        parent_id=body.parent_id,
        assignee_type=body.assignee_type,
        assignee_id=body.assignee_id,
        priority=body.priority,
        deps=body.deps,
        due_at=body.due_at,
    )
    return TaskOut.of(task)


@router.patch("/{project_id}/tasks/{task_id}", summary="Edit a task or drag it to a column")
async def patch_task(
    project_id: str,
    task_id: str,
    body: TaskPatch,
    server: OctopServer = Depends(get_server),
    user: User = Depends(require_permission("projects")),
) -> TaskOut:
    """``status`` goes through the task state machine; every other field is a
    plain patch. Changing either one appends to the project timeline. The task must
    belong to ``project_id``; the service answers ``PROJECT_TASK_NOT_FOUND`` when it
    does not."""
    service = _service(server)
    actor = _actor(user)

    if body.status is not None:
        service.transition_task(project_id, task_id, user=actor, target=body.status)

    fields = body.model_dump(exclude_unset=True, exclude={"status"})
    if fields:
        service.update_task(project_id, task_id, user=actor, **fields)
    return TaskOut.of(service.get_task(project_id, task_id, user=actor))


@router.delete("/{project_id}/tasks/{task_id}", summary="Delete a task")
async def delete_task(
    project_id: str,
    task_id: str,
    server: OctopServer = Depends(get_server),
    user: User = Depends(require_permission("projects")),
) -> dict[str, bool]:
    """The deletion stays in the timeline: history outlives the row. The task must
    belong to ``project_id``, like every other task route."""
    deleted = _service(server).delete_task(project_id, task_id, user=_actor(user))
    return {"deleted": deleted}


@router.post(
    "/{project_id}/tasks/{task_id}:dispatch",
    summary="Dispatch a task to its agent or team",
)
async def dispatch_task(
    project_id: str,
    task_id: str,
    server: OctopServer = Depends(get_server),
    user: User = Depends(require_permission("projects")),
) -> TaskOut:
    """Run one agent turn for the task's assignee and bind its thread to the task.

    The assignee must be an ``agent`` or a ``team`` (a team is dispatched through
    its host, which opens the team room); a human assignee has no runtime to run.
    The turn executes in the background — this endpoint returns the updated task
    rather than streaming, and the conversation can be followed through
    ``thread_id``. ``assignee_type`` outside agent/team is rejected.
    """
    task = await _service(server).dispatch_task(project_id, task_id, user=_actor(user))
    return TaskOut.of(task)


# ── timeline ─────────────────────────────────────────────────────────────────


@router.get("/{project_id}/timeline", summary="Read the project timeline")
async def list_timeline(
    project_id: str,
    limit: int | None = Query(default=None, ge=1, le=500),
    server: OctopServer = Depends(get_server),
    user: User = Depends(require_permission("projects")),
) -> list[TimelineEventOut]:
    """Oldest first, so the response reads as a replay of what happened."""
    rows = _service(server).list_timeline(project_id, user=_actor(user), limit=limit)
    return [TimelineEventOut.of(r) for r in rows]


def _actor(user: User) -> ProjectActor:
    """``User`` already satisfies :class:`ProjectActor`; this keeps mypy honest."""
    return user
