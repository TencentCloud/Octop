"""HTTP API for the project instruction (PLAN.md §5, Q19).

The instruction is **display-only reference text**. It is deliberately *not*
injected into any agent prompt, dispatch context, system message or tool
context — see ``infra/projects/dispatch.py``, which has no ``instruction``
reference at all. Treat that as the contract of this module: a future "just pass
it along" edit here would be a security regression, not a feature.

The write route is the only writer of the column and it is gated on the
per-project ``PROJECT_MANAGE_CONFIG`` action (owner + admin). It must **not** be
folded into ``PATCH /api/projects/{pid}``: that route checks ``PROJECT_WRITE``,
which ``member`` also holds, so folding it in would bypass the config level
(PLAN.md §5, R18).

``""`` is a legal value (S12: clearing the field), and an empty value is a 200
with an empty read-back — only text that is too long or carries control
characters is rejected, with ``400 PROJECT_INSTRUCTION_INVALID``.
"""

from __future__ import annotations

import unicodedata

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from octop.api.deps import get_server, require_permission
from octop.infra.db.repos.projects import PROJECT_INSTRUCTION_MAX_LENGTH, ProjectRow
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.projects.service import PROJECT_MANAGE_CONFIG, ProjectActor, ProjectService
from octop.infra.server import OctopServer
from octop.infra.users.identity import User

router = APIRouter(prefix="/projects")

#: Line breaks and tabs are legitimate in a multi-line spec. Every other ``Cc``
#: control character (``\x00``, ``\r``, ESC sequences, …) is rejected: the text
#: is rendered in the dashboard and must not carry terminal/markup controls.
_ALLOWED_CONTROL_CHARS = frozenset({"\n", "\t"})


# ── request / response models ────────────────────────────────────────────────


class InstructionOut(BaseModel):
    project_id: str
    instruction: str = Field(description="Display-only text; empty means not set.")


class InstructionUpdate(BaseModel):
    instruction: str = Field(
        description=(
            "Replacement text (max "
            f"{PROJECT_INSTRUCTION_MAX_LENGTH} characters). An empty string clears it."
        )
    )


# ── helpers ──────────────────────────────────────────────────────────────────


def _invalid_instruction() -> OctopError:
    """The one refusal shape of this feature; the envelope localizes the code."""
    return OctopError(
        ErrorCode.PROJECT_INSTRUCTION_INVALID,
        "the project instruction is too long or contains control characters",
    )


def validate_instruction(value: str) -> str:
    """Return the text to store, or raise ``400 PROJECT_INSTRUCTION_INVALID``.

    ``""`` passes: S12 makes clearing the field a normal write, not an error.
    """
    if len(value) > PROJECT_INSTRUCTION_MAX_LENGTH:
        raise _invalid_instruction()
    if any(
        unicodedata.category(char) == "Cc" and char not in _ALLOWED_CONTROL_CHARS for char in value
    ):
        raise _invalid_instruction()
    return value


def _service(server: OctopServer) -> ProjectService:
    assert server.services is not None
    runtime = server.app_runtime
    return ProjectService(
        server.services,
        agent_manager=runtime.agent_registry if runtime is not None else None,
        gateway=runtime.gateway if runtime is not None else None,
    )


def _actor(user: User) -> ProjectActor:
    """``User`` already satisfies :class:`ProjectActor`; this keeps mypy honest."""
    return user


# ── instruction ──────────────────────────────────────────────────────────────


@router.get("/{project_id}/instruction", summary="Read a project's instruction")
async def get_instruction(
    project_id: str,
    server: OctopServer = Depends(get_server),
    user: User = Depends(require_permission("projects")),
) -> InstructionOut:
    """Readable by every project member (``PROJECT_READ``)."""
    project: ProjectRow = _service(server).get_project(project_id, user=_actor(user))
    return InstructionOut(project_id=project.id, instruction=project.instruction)


@router.put("/{project_id}/instruction", summary="Replace a project's instruction")
async def put_instruction(
    project_id: str,
    body: InstructionUpdate,
    server: OctopServer = Depends(get_server),
    user: User = Depends(require_permission("projects")),
) -> InstructionOut:
    """Owner / admin only (``PROJECT_MANAGE_CONFIG``).

    Rejections: a non-member gets ``PROJECT_FORBIDDEN``, a member or viewer gets
    ``PROJECT_ROLE_FORBIDDEN``, and text over the cap or with control characters
    gets ``PROJECT_INSTRUCTION_INVALID`` — all 4xx, never a 500.
    """
    service = _service(server)
    # The role gate comes first, so an unauthorized caller cannot probe the
    # validation rules (and never reaches the write).
    service.assert_project_role(project_id, user=_actor(user), required=PROJECT_MANAGE_CONFIG)
    instruction = validate_instruction(body.instruction)

    assert server.services is not None
    row = server.services.project_repo.update(project_id, instruction=instruction)
    # The role check above already proved the project exists.
    assert row is not None
    return InstructionOut(project_id=row.id, instruction=row.instruction)
