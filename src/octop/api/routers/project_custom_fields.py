"""HTTP API for project custom fields (PLAN.md §6.3).

Thin layer: validate the request shape, call
:class:`ProjectCustomFieldService`, map the result. Every route is gated by the
coarse ``projects`` permission key; the per-project role check lives in the
service, so there is exactly one permission implementation
(``assert_project_role``).

The six routes cover rings ① definition, ② entry, and ③ read; ring ④
(rendering) belongs to the dashboard.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from octop.api.deps import get_server, require_permission
from octop.infra.db.repos._base import UNSET
from octop.infra.db.repos.project_custom_fields import ProjectCustomFieldRow
from octop.infra.projects.custom_fields import ProjectCustomFieldService
from octop.infra.projects.service import ProjectActor
from octop.infra.server import OctopServer
from octop.infra.users.identity import User

router = APIRouter(prefix="/projects")


# ── request / response models ────────────────────────────────────────────────


class CustomFieldOut(BaseModel):
    field_id: str
    key: str
    label: str
    type: str = Field(description="text | number | date | select")
    required: bool
    options: list[str] = Field(description="Only a 'select' field has options.")
    sort_order: int
    created_at: int

    @classmethod
    def of(cls, row: ProjectCustomFieldRow) -> CustomFieldOut:
        return cls(
            field_id=row.field_id,
            key=row.key,
            label=row.label,
            type=row.type,
            required=row.required,
            options=row.options,
            sort_order=row.sort_order,
            created_at=row.created_at,
        )


class CustomFieldCreate(BaseModel):
    key: str = Field(min_length=1, description="Stable identifier: ^[a-z][a-z0-9_]{0,31}$.")
    label: str = Field(min_length=1, description="Shown to users.")
    type: str = Field(description="text | number | date | select")
    required: bool = False
    options: list[str] = Field(
        default_factory=list,
        description="Required and non-empty for 'select'; must be empty otherwise.",
    )
    sort_order: int | None = None


class CustomFieldPatch(BaseModel):
    """``type`` / ``key`` are accepted only so they can be refused with 409."""

    label: str | None = None
    required: bool | None = None
    options: list[str] | None = None
    sort_order: int | None = None
    type: str | None = Field(default=None, description="Immutable; sending it is a 409.")
    key: str | None = Field(default=None, description="Immutable; sending it is a 409.")


class TaskFieldValuesIn(BaseModel):
    values: dict[str, Any] = Field(
        default_factory=dict,
        description="field_id -> value. This is the task's complete value set.",
    )


class TaskFieldValuesOut(BaseModel):
    task_id: str
    definitions: list[CustomFieldOut]
    values: dict[str, str] = Field(description="Stored, normalised value per field_id.")


# ── helpers ──────────────────────────────────────────────────────────────────


def _service(server: OctopServer) -> ProjectCustomFieldService:
    assert server.services is not None
    return ProjectCustomFieldService(server.services)


def _actor(user: User) -> ProjectActor:
    """``User`` already satisfies :class:`ProjectActor`; this keeps mypy honest."""
    return user


# ── definitions (ring ①) ─────────────────────────────────────────────────────


@router.get("/{project_id}/custom-fields", summary="List a project's custom field definitions")
async def list_custom_fields(
    project_id: str,
    server: OctopServer = Depends(get_server),
    user: User = Depends(require_permission("projects")),
) -> list[CustomFieldOut]:
    rows = _service(server).list_fields(project_id, user=_actor(user))
    return [CustomFieldOut.of(row) for row in rows]


@router.post(
    "/{project_id}/custom-fields",
    summary="Create a custom field definition",
    status_code=status.HTTP_201_CREATED,
)
async def create_custom_field(
    project_id: str,
    body: CustomFieldCreate,
    server: OctopServer = Depends(get_server),
    user: User = Depends(require_permission("projects")),
) -> CustomFieldOut:
    """``key`` is unique per project; a bad definition is ``PROJECT_CUSTOM_FIELD_INVALID``."""
    row = _service(server).create_field(
        project_id,
        user=_actor(user),
        key=body.key,
        label=body.label,
        type=body.type,
        required=body.required,
        options=body.options,
        sort_order=body.sort_order,
    )
    return CustomFieldOut.of(row)


@router.patch(
    "/{project_id}/custom-fields/{field_id}",
    summary="Edit a custom field definition",
)
async def patch_custom_field(
    project_id: str,
    field_id: str,
    body: CustomFieldPatch,
    server: OctopServer = Depends(get_server),
    user: User = Depends(require_permission("projects")),
) -> CustomFieldOut:
    """Updates ``label`` / ``required`` / ``options`` / ``sort_order``.

    ``type`` and ``key`` are immutable: sending either is refused with 409 rather
    than ignored. Dropping a ``select`` option that stored values still use is
    refused as well — no value is rewritten.
    """
    row = _service(server).update_field(
        project_id,
        field_id,
        user=_actor(user),
        label=body.label if body.label is not None else UNSET,
        required=body.required if body.required is not None else UNSET,
        options=body.options if body.options is not None else UNSET,
        sort_order=body.sort_order if body.sort_order is not None else UNSET,
        type=body.type if body.type is not None else UNSET,
        key=body.key if body.key is not None else UNSET,
    )
    return CustomFieldOut.of(row)


@router.delete(
    "/{project_id}/custom-fields/{field_id}",
    summary="Delete a custom field definition",
)
async def delete_custom_field(
    project_id: str,
    field_id: str,
    server: OctopServer = Depends(get_server),
    user: User = Depends(require_permission("projects")),
) -> dict[str, bool]:
    """Values on tasks disappear with the definition (``ON DELETE CASCADE``)."""
    deleted = _service(server).delete_field(project_id, field_id, user=_actor(user))
    return {"deleted": deleted}


# ── task values (rings ② ③) ──────────────────────────────────────────────────


@router.get(
    "/{project_id}/tasks/{task_id}/custom-fields",
    summary="Read one task's custom field values",
)
async def get_task_custom_fields(
    project_id: str,
    task_id: str,
    server: OctopServer = Depends(get_server),
    user: User = Depends(require_permission("projects")),
) -> TaskFieldValuesOut:
    """Returns the definitions *and* the stored values, so the UI needs one call."""
    definitions, values = _service(server).get_task_fields(project_id, task_id, user=_actor(user))
    return TaskFieldValuesOut(
        task_id=task_id,
        definitions=[CustomFieldOut.of(row) for row in definitions],
        values=values,
    )


@router.put(
    "/{project_id}/tasks/{task_id}/custom-fields",
    summary="Replace one task's custom field values",
)
async def put_task_custom_fields(
    project_id: str,
    task_id: str,
    body: TaskFieldValuesIn,
    server: OctopServer = Depends(get_server),
    user: User = Depends(require_permission("projects")),
) -> TaskFieldValuesOut:
    """The body carries the task's **whole** value set.

    Every ``required`` definition is validated on each call. A value that does
    not match its definition is ``PROJECT_CUSTOM_FIELD_VALUE_INVALID`` (400); a
    ``field_id`` this project does not define is ``PROJECT_CUSTOM_FIELD_NOT_FOUND``
    (404), exactly like one that was never created.
    """
    service = _service(server)
    values = service.set_task_values(
        project_id,
        task_id,
        user=_actor(user),
        values=body.values,
    )
    definitions = service.list_fields(project_id, user=_actor(user))
    return TaskFieldValuesOut(
        task_id=task_id,
        definitions=[CustomFieldOut.of(row) for row in definitions],
        values=values,
    )
