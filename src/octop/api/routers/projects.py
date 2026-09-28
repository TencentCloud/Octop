"""HTTP API for projects, members, and the task board.

Thin layer: validate the request, call :class:`ProjectService`, map the result.
Every route is gated by the coarse ``projects`` permission key; the per-project
role check lives in the service (§4.6).

Note that ``DELETE /projects/{id}`` **archives** — that is the contract the plan
specifies, and it is why archiving is owner-only while the project row survives.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field, field_validator

from octop.api.deps import get_server, require_permission
from octop.api.routers.project_attachments import AttachmentOut
from octop.infra.db.repos.project_content import (
    COMMENT_NODE_CONCLUSION,
    ProjectCommentRow,
)
from octop.infra.db.repos.project_tasks import ProjectTaskRow, TimelineEventRow
from octop.infra.db.repos.projects import ProjectMemberRow, ProjectRow
from octop.infra.projects.custom_fields import ProjectCustomFieldService
from octop.infra.projects.discussion import ProjectDiscussion
from octop.infra.projects.service import ProjectActor, ProjectService
from octop.infra.projects.tags import ProjectTagService
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
    name: str | None = Field(
        default=None,
        description=(
            "Display name of the subject (agents.name / users.display_name, "
            "username as the fallback). Null when it cannot be resolved — the UI "
            "then falls back to subject_id."
        ),
    )

    @classmethod
    def of(cls, row: ProjectMemberRow, name: str | None = None) -> MemberOut:
        return cls(
            subject_type=row.subject_type,
            subject_id=row.subject_id,
            user_id=row.user_id,
            role=row.role,
            created_at=row.created_at,
            name=name,
        )


class TaskTagOut(BaseModel):
    """A tag as resolved on a task (PLAN.md §4): ``tag_id`` / ``name`` / ``color``."""

    tag_id: str
    name: str
    color: str


class TaskCustomFieldValueOut(BaseModel):
    """A stored custom-field value plus the definition it belongs to (§6.3)."""

    field_id: str
    key: str
    label: str
    type: str = Field(description="text | number | date | select")
    value: str = Field(description="Normalised stored value; '' when empty.")


class TaskOut(BaseModel):
    task_id: str
    project_id: str
    parent_id: str | None
    title: str
    description: str
    status: str = Field(description="planning | todo | doing | review | done | blocked | cancelled")
    assignee_type: str | None
    assignee_id: str | None
    priority: int
    deps: list[str]
    thread_id: str | None
    origin_node_id: str | None
    start_at: int | None
    due_at: int | None
    tags: list[TaskTagOut] = Field(
        default_factory=list, description="Resolved tags, oldest link first (never null)."
    )
    custom_fields: list[TaskCustomFieldValueOut] = Field(
        default_factory=list,
        description="Stored values in field display order (never null).",
    )
    attachments: list[AttachmentOut] = Field(
        default_factory=list, description="Attachments bound to this task (never null)."
    )
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
            start_at=row.start_at,
            due_at=row.due_at,
            sort_order=row.sort_order,
            created_by=row.created_by,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


class CommentOut(BaseModel):
    """One message on a project (or task) discussion line."""

    comment_id: str
    project_id: str
    task_id: str | None = Field(description="Null for a project-level comment.")
    thread_id: str | None
    author_type: str = Field(description="user | agent")
    author_id: str
    body: str
    source: str
    node_type: str = Field(description="none | conclusion")
    concluded: bool = Field(description="True when this comment is the conclusion.")
    created_at: int
    updated_at: int
    name: str | None = Field(
        default=None,
        description=(
            "Author display name resolved from author_type/author_id (agents.name, "
            "users.display_name then username). Null when it cannot be resolved — the "
            "UI falls back to author_id."
        ),
    )

    @classmethod
    def of(cls, row: ProjectCommentRow, name: str | None = None) -> CommentOut:
        return cls(
            comment_id=row.id,
            project_id=row.project_id,
            task_id=row.task_id,
            thread_id=row.thread_id,
            author_type=row.author_type,
            author_id=row.author_id,
            body=row.body,
            source=row.source,
            node_type=row.node_type,
            concluded=row.node_type == COMMENT_NODE_CONCLUSION,
            created_at=row.created_at,
            updated_at=row.updated_at,
            name=name,
        )


class CommentCreate(BaseModel):
    body: str = Field(min_length=1, description="Comment text; blank is rejected as 422.")
    task_id: str | None = Field(default=None, description="Attach to a task's line.")

    @field_validator("body")
    @classmethod
    def _body_is_not_blank(cls, value: str) -> str:
        """``"   "`` is not a comment: reject it in the request layer (422), exactly
        like ``_title_is_not_blank`` does for tasks."""
        if not value.strip():
            raise ValueError("body must not be blank")
        return value


class TimelineEventOut(BaseModel):
    actor: str = Field(description="Actor reference, e.g. user:12 (stable identifier).")
    actor_name: str | None = Field(
        default=None,
        description=(
            "Display name for `actor`; null when it cannot be resolved. `actor` keeps "
            "its existing `type:id` format — this field is only the readable side."
        ),
    )
    action: str = Field(description="task.created | task.updated | task.status_changed | …")
    task_id: str | None
    payload: dict[str, Any]
    at: int

    @classmethod
    def of(cls, row: TimelineEventRow, actor_name: str | None = None) -> TimelineEventOut:
        return cls(
            actor=row.actor,
            actor_name=actor_name,
            action=row.action,
            task_id=row.task_id,
            payload=row.payload,
            at=row.at,
        )


# ── request bodies ───────────────────────────────────────────────────────────


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, description="Project name; also names its knowledge base.")
    goal: str = Field(default="", description="What the project is meant to achieve.")
    status: str | None = Field(
        default=None,
        description=(
            "Initial status; defaults to draft. One of "
            "draft | active | paused | completed | cancelled | archived."
        ),
    )
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
    kb_id: str | None = Field(
        default=None,
        description=(
            "Knowledge base to bind; null unbinds. Omitting the key leaves it as is. "
            "Sending it raises the whole request to the config permission level."
        ),
    )


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
    status: str | None = Field(
        default=None,
        description="Initial status; defaults to planning. Must be one of the seven task states.",
    )
    start_at: int | None = Field(default=None, description="Planned start, unix seconds.")
    due_at: int | None = Field(default=None, description="Planned finish, unix seconds.")
    tags: list[str] = Field(default_factory=list, description="Tag ids to apply on creation.")
    custom_fields: dict[str, object] | None = Field(
        default=None,
        description="Custom-field id to value; null skips required-field validation.",
    )
    attachment_ids: list[str] = Field(
        default_factory=list,
        description="Pending attachment ids to bind once the task row exists.",
    )

    @field_validator("title")
    @classmethod
    def _title_is_not_blank(cls, value: str) -> str:
        """``"   "`` is not a title: reject it as a validation error (422)."""
        if not value.strip():
            raise ValueError("title must not be blank")
        return value


class TaskPatch(BaseModel):
    title: str | None = None
    description: str | None = None
    parent_id: str | None = None
    assignee_type: str | None = None
    assignee_id: str | None = None
    priority: int | None = None
    deps: list[str] | None = None
    start_at: int | None = Field(default=None, description="Planned start, unix seconds.")
    due_at: int | None = None
    tags: list[str] | None = Field(default=None, description="Tag ids; replaces the whole set.")
    custom_fields: dict[str, object] | None = Field(
        default=None,
        description="Custom-field id to value; null skips required-field validation.",
    )
    status: str | None = Field(
        default=None,
        description=(
            "Target status; routed through the task state machine. One of "
            "planning | todo | doing | review | done | blocked | cancelled."
        ),
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


def _tasks_out(
    server: OctopServer,
    service: ProjectService,
    project_id: str,
    rows: Sequence[ProjectTaskRow],
) -> list[TaskOut]:
    """Assemble task payloads with their tags, field values and attachments.

    The whole page is resolved with **four batch reads** (tag join, values,
    definitions, attachments) regardless of row count — the board renders every
    task at once, so reading per task would be N+1. All three collections are
    always present and may be empty, never ``null``.
    """
    payload = [TaskOut.of(row) for row in rows]
    if not payload:
        return payload
    assert server.services is not None
    task_ids = [row.id for row in rows]
    tags_by_task = ProjectTagService(server.services, project_service=service).resolve_task_tags(
        task_ids
    )
    values_by_task = ProjectCustomFieldService(
        server.services, project_service=service
    ).resolve_task_values(task_ids)
    definitions = {
        definition.field_id: definition
        for definition in server.services.project_custom_field_repo.list_by_project(project_id)
    }
    attachments_by_task = server.services.project_artifact_repo.list_by_tasks(
        project_id=project_id, task_ids=task_ids
    )
    for out, row in zip(payload, rows, strict=True):
        out.tags = [
            TaskTagOut(tag_id=tag.tag_id, name=tag.name, color=tag.color)
            for tag in tags_by_task.get(row.id, [])
        ]
        entries = [
            (
                definitions[field_id].sort_order,
                field_id,
                TaskCustomFieldValueOut(
                    field_id=field_id,
                    key=definitions[field_id].key,
                    label=definitions[field_id].label,
                    type=definitions[field_id].type,
                    value=value,
                ),
            )
            for field_id, value in (values_by_task.get(row.id) or {}).items()
            if field_id in definitions
        ]
        entries.sort(key=lambda entry: (entry[0], entry[1]))
        out.custom_fields = [entry[2] for entry in entries]
        out.attachments = [AttachmentOut.of(row) for row in attachments_by_task.get(row.id, [])]
    return payload


def _task_out(server: OctopServer, service: ProjectService, row: ProjectTaskRow) -> TaskOut:
    """One task with its metadata attached (same batch path as the board)."""
    return _tasks_out(server, service, row.project_id, [row])[0]


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
    rolled back and nothing is left behind.

    ``status`` is an initial value (all six states are selectable, SPEC S-10), not
    a transition; an unknown value is a 409, never a silent drop."""
    project = _service(server).create_project(
        owner_user=_actor(user),
        name=body.name,
        goal=body.goal,
        status=body.status,
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
    sent = body.model_dump(exclude_unset=True)
    if "kb_id" in sent:
        # Three states: absent (untouched) / null (unbind) / value (rebind). Passing
        # it in the same call is what makes the whole request MANAGE_CONFIG.
        fields["kb_id"] = body.kb_id

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
    rows = _service(server).list_members_with_names(project_id, user=_actor(user))
    return [MemberOut.of(row, name) for row, name in rows]


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
    service = _service(server)
    rows = service.list_tasks(project_id, user=_actor(user), status=status_filter)
    return _tasks_out(server, service, project_id, rows)


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
    """Create a task. ``status`` defaults to ``planning``; any of the seven states
    may be chosen up front (the board creates straight into its column), and later
    moves go through PATCH.

    ``tags`` / ``custom_fields`` / ``attachment_ids`` are applied by the four-step
    orchestration in :meth:`ProjectService.create_task` (PLAN.md §2.3): a refused
    request rolls back the whole task rather than silently dropping the metadata.
    """
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
        status=body.status,
        start_at=body.start_at,
        due_at=body.due_at,
        tags=body.tags,
        custom_fields=body.custom_fields,
        attachment_ids=body.attachment_ids,
    )
    return _task_out(server, _service(server), task)


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
    does not.

    ``tags`` / ``custom_fields`` carry the same meaning as on create (the whole
    set, not a merge) and are applied through their own services — a patch that
    includes them must not return 200 while dropping them. ``exclude_unset`` is
    what makes "omitted" different from "explicitly empty".
    """
    service = _service(server)
    actor = _actor(user)

    if body.status is not None:
        service.transition_task(project_id, task_id, user=actor, target=body.status)

    fields = body.model_dump(exclude_unset=True, exclude={"status", "tags", "custom_fields"})
    if fields:
        service.update_task(project_id, task_id, user=actor, **fields)
    if body.tags is not None:
        service.set_task_tags(project_id, task_id, user=actor, tag_ids=body.tags)
    if body.custom_fields is not None:
        service.set_task_values(project_id, task_id, user=actor, values=body.custom_fields)
    return _task_out(server, service, service.get_task(project_id, task_id, user=actor))


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
    service = _service(server)
    task = await service.dispatch_task(project_id, task_id, user=_actor(user))
    return _task_out(server, service, task)


# ── timeline ─────────────────────────────────────────────────────────────────


@router.get("/{project_id}/timeline", summary="Read the project timeline")
async def list_timeline(
    project_id: str,
    limit: int | None = Query(default=None, ge=1, le=500),
    task_id: str | None = Query(
        default=None, description="Only this task's events; omit for the whole project."
    ),
    server: OctopServer = Depends(get_server),
    user: User = Depends(require_permission("projects")),
) -> list[TimelineEventOut]:
    """Oldest first, so the response reads as a replay of what happened."""
    service = _service(server)
    rows = service.list_timeline(project_id, user=_actor(user), limit=limit, task_id=task_id)
    return [TimelineEventOut.of(r, service.resolve_actor_ref_name(r.actor)) for r in rows]


def _actor(user: User) -> ProjectActor:
    """``User`` already satisfies :class:`ProjectActor`; this keeps mypy honest."""
    return user


# ── comments (discussion) ────────────────────────────────────────────────────


def _discussion(server: OctopServer) -> ProjectDiscussion:
    assert server.services is not None
    return ProjectDiscussion(server.services)


@router.get("/{project_id}/comments", summary="List a project's comments")
async def list_comments(
    project_id: str,
    task_id: str | None = Query(default=None, description="Only this task's line."),
    concluded: bool | None = Query(
        default=None, description="true = only the conclusion; false = everything else."
    ),
    server: OctopServer = Depends(get_server),
    user: User = Depends(require_permission("projects")),
) -> list[CommentOut]:
    """Oldest first. Domain rules live in ``ProjectDiscussion``; this is an adapter."""
    discussion = _discussion(server)
    rows = discussion.list_comments(
        project_id, user=_actor(user), task_id=task_id, concluded=concluded
    )
    service = _service(server)
    return [
        CommentOut.of(row, service.resolve_actor_name(row.author_type, row.author_id))
        for row in rows
    ]


@router.post(
    "/{project_id}/comments",
    summary="Add a comment to a project",
    status_code=status.HTTP_201_CREATED,
)
async def create_comment(
    project_id: str,
    body: CommentCreate,
    server: OctopServer = Depends(get_server),
    user: User = Depends(require_permission("projects")),
) -> CommentOut:
    """Requires ``write``. A blank body stays the existing 400, not an empty row."""
    row = _discussion(server).add_comment(
        project_id, user=_actor(user), body=body.body, task_id=body.task_id
    )
    return CommentOut.of(row)


@router.post(
    "/{project_id}/comments/{comment_id}/conclude",
    summary="Mark a comment as the discussion conclusion",
)
async def conclude_comment(
    project_id: str,
    comment_id: str,
    server: OctopServer = Depends(get_server),
    user: User = Depends(require_permission("projects")),
) -> CommentOut:
    """Idempotent: adopting the same comment twice keeps one conclusion."""
    row = _discussion(server).set_conclusion(
        project_id, comment_id, user=_actor(user), concluded=True
    )
    return CommentOut.of(row)


@router.delete(
    "/{project_id}/comments/{comment_id}/conclude",
    summary="Remove the conclusion mark from a comment",
)
async def unconclude_comment(
    project_id: str,
    comment_id: str,
    server: OctopServer = Depends(get_server),
    user: User = Depends(require_permission("projects")),
) -> CommentOut:
    """Idempotent: removing a mark that is not set still answers 200."""
    row = _discussion(server).set_conclusion(
        project_id, comment_id, user=_actor(user), concluded=False
    )
    return CommentOut.of(row)
