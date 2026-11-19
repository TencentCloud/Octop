"""Per-turn file checkpoints: turn diff and ZCode-style rewind."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from octop.api.common.workspace import (
    coerce_read_content,
    require_agent_workspace,
    workspace_api_path,
)
from octop.api.deps import current_user, get_server
from octop.infra.agents.file_checkpoints import (
    apply_rewind,
    classify_rewind,
    load_checkpoints,
    turn_diff,
)
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.utils.paths import PathLayout

router = APIRouter()


def _changes(agent_id: str, thread_id: str, message_id: str) -> list[dict[str, Any]]:
    return load_checkpoints(PathLayout.from_env().root, agent_id, thread_id, message_id)


class TurnDiffModel(BaseModel):
    path: str
    diff: str = Field(..., description="Unified diff of this turn's before→after")


class RewindFileModel(BaseModel):
    path: str
    before: str | None = None
    after: str | None = None
    reason: str | None = None


class RewindPreviewModel(BaseModel):
    safe: list[RewindFileModel] = Field(default_factory=list)
    unsafe: list[RewindFileModel] = Field(default_factory=list)
    ignored: list[RewindFileModel] = Field(default_factory=list)


class RewindApplyModel(BaseModel):
    applied: list[str] = Field(default_factory=list)


def _rf(g: dict[str, Any]) -> RewindFileModel:
    return RewindFileModel(
        path=g["path"],
        before=g.get("before"),
        after=g.get("after"),
        reason=g.get("reason"),
    )


@router.get(
    "/agents/{agent_id}/threads/{thread_id}/messages/{message_id}/files/diff",
    summary="Per-turn file diff",
    response_model=TurnDiffModel,
)
async def turn_file_diff(
    agent_id: str,
    thread_id: str,
    message_id: str,
    path: str = Query(..., description="Workspace-relative file path"),
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> Any:
    await require_agent_workspace(
        agent_id, user=user, server=server, as_user=as_user, owner_only=True
    )
    rel = workspace_api_path(path)
    for ch in _changes(agent_id, thread_id, message_id):
        if ch["path"] == rel:
            return TurnDiffModel(path=rel, diff=turn_diff(ch.get("before"), ch.get("after"), rel))
    raise OctopError(ErrorCode.NOT_FOUND, f"no checkpoint for {rel!r} in this turn")


@router.get(
    "/agents/{agent_id}/threads/{thread_id}/messages/{message_id}/files/rewind/preview",
    summary="Preview which files can be rewound",
    response_model=RewindPreviewModel,
)
async def rewind_preview(
    agent_id: str,
    thread_id: str,
    message_id: str,
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> Any:
    workspace = await require_agent_workspace(
        agent_id, user=user, server=server, as_user=as_user, owner_only=True
    )
    changes = _changes(agent_id, thread_id, message_id)
    current: dict[str, str | None] = {}
    for ch in changes:
        p = ch["path"]
        try:
            current[p] = (
                coerce_read_content(workspace.read_text(p)) if workspace.exists(p) else None
            )
        except Exception:  # noqa: BLE001 - unreadable => unsafe
            current[p] = None
    groups = classify_rewind(changes, current)
    return RewindPreviewModel(
        safe=[_rf(g) for g in groups["safe"]],
        unsafe=[_rf(g) for g in groups["unsafe"]],
        ignored=[_rf(g) for g in groups["ignored"]],
    )


@router.post(
    "/agents/{agent_id}/threads/{thread_id}/messages/{message_id}/files/rewind/apply",
    summary="Rewind safe files to their pre-turn content",
    response_model=RewindApplyModel,
)
async def rewind_apply(
    agent_id: str,
    thread_id: str,
    message_id: str,
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> Any:
    workspace = await require_agent_workspace(
        agent_id, user=user, server=server, as_user=as_user, owner_only=True
    )
    changes = _changes(agent_id, thread_id, message_id)
    current: dict[str, str | None] = {}
    for ch in changes:
        p = ch["path"]
        try:
            current[p] = (
                coerce_read_content(workspace.read_text(p)) if workspace.exists(p) else None
            )
        except Exception:  # noqa: BLE001
            current[p] = None
    groups = classify_rewind(changes, current)
    applied = apply_rewind(workspace, groups["safe"])
    return RewindApplyModel(applied=applied)
