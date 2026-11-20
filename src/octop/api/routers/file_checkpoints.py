"""Per-turn file checkpoints: turn summary, diff, and rewind."""

from __future__ import annotations

import asyncio
import logging
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
    latest_message_id,
    load_turn_state,
    mark_turn_reverted,
    turn_diff,
    turn_summary,
)
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.utils.paths import PathLayout

router = APIRouter()
logger = logging.getLogger(__name__)


def _turn_state(agent_id: str, thread_id: str, message_id: str) -> dict[str, Any]:
    return load_turn_state(PathLayout.from_env().root, agent_id, thread_id, message_id)


class TurnSummaryFileModel(BaseModel):
    path: str
    added: int = Field(..., description="Added lines in this turn")
    removed: int = Field(..., description="Removed lines in this turn")
    write_count: int = Field(1, description="Writes to this file during the turn")
    tool_names: list[str] = Field(default_factory=list, description="Tools that touched it")


class TurnSummaryModel(BaseModel):
    files: list[TurnSummaryFileModel] = Field(default_factory=list)
    additions: int = 0
    deletions: int = 0
    reverted: bool = Field(False, description="This turn's files were already rewound")


class LatestCheckpointModel(BaseModel):
    message_id: str | None = Field(
        None, description="Newest checkpointed assistant message id, if any"
    )


class TurnDiffModel(BaseModel):
    path: str
    diff: str = Field(..., description="Unified diff of this turn's before→after")


class RewindFileModel(BaseModel):
    path: str
    before: str | None = None
    after: str | None = None
    reason: str | None = None
    write_count: int | None = None
    tool_names: list[str] | None = None


class RewindPreviewModel(BaseModel):
    safe: list[RewindFileModel] = Field(default_factory=list)
    unsafe: list[RewindFileModel] = Field(default_factory=list)
    ignored: list[RewindFileModel] = Field(default_factory=list)
    can_apply: bool = Field(
        ..., description="True only when at least one file is safe and none are unsafe"
    )


class RewindApplyModel(BaseModel):
    applied: list[str] = Field(default_factory=list)
    blocked: list[str] = Field(
        default_factory=list,
        description="Unsafe paths that prevented the rewind (rewind is all-or-nothing)",
    )


def _rf(g: dict[str, Any]) -> RewindFileModel:
    return RewindFileModel(
        path=g["path"],
        before=g.get("before"),
        after=g.get("after"),
        reason=g.get("reason"),
        write_count=g.get("write_count"),
        tool_names=g.get("tool_names"),
    )


@router.get(
    "/agents/{agent_id}/threads/{thread_id}/files/latest-message",
    summary="Resolve the newest checkpointed turn",
    response_model=LatestCheckpointModel,
)
async def latest_turn_message(
    agent_id: str,
    thread_id: str,
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> Any:
    """Newest checkpointed assistant message id for a thread.

    Live dashboard turns use a client-side message id, so the change card
    resolves the harness-recorded id here until the thread is reloaded.
    """
    await require_agent_workspace(
        agent_id, user=user, server=server, as_user=as_user, owner_only=True
    )
    message_id = await asyncio.to_thread(
        latest_message_id, PathLayout.from_env().root, agent_id, thread_id
    )
    return LatestCheckpointModel(message_id=message_id)


@router.get(
    "/agents/{agent_id}/threads/{thread_id}/messages/{message_id}/files/summary",
    summary="Per-turn file change summary",
    response_model=TurnSummaryModel,
)
async def turn_file_summary(
    agent_id: str,
    thread_id: str,
    message_id: str,
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> Any:
    """Authoritative per-turn stats computed from the captured checkpoints."""
    await require_agent_workspace(
        agent_id, user=user, server=server, as_user=as_user, owner_only=True
    )
    # JSON deserialization plus the per-file LCS are CPU-bound; keep them off
    # the event loop.
    state = await asyncio.to_thread(_turn_state, agent_id, thread_id, message_id)
    summary = await asyncio.to_thread(turn_summary, state["changes"])
    return TurnSummaryModel(
        files=[
            TurnSummaryFileModel(
                path=f["path"],
                added=f["added"],
                removed=f["removed"],
                write_count=f["write_count"],
                tool_names=f["tool_names"],
            )
            for f in summary["files"]
        ],
        additions=summary["additions"],
        deletions=summary["deletions"],
        reverted=state["reverted"],
    )


def _diff_sync(changes: list[dict[str, Any]], rel: str) -> str | None:
    for ch in changes:
        if ch["path"] == rel:
            return turn_diff(ch.get("before"), ch.get("after"), rel)
    return None


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
    state = await asyncio.to_thread(_turn_state, agent_id, thread_id, message_id)
    diff = await asyncio.to_thread(_diff_sync, state["changes"], rel)
    if diff is None:
        raise OctopError(ErrorCode.NOT_FOUND, f"no checkpoint for {rel!r} in this turn")
    return TurnDiffModel(path=rel, diff=diff)


def _current_contents(workspace: Any, changes: list[dict[str, Any]]) -> dict[str, str | None]:
    """Read the current content of every checkpointed path.

    Preview and apply must classify on the same normalization, so both go
    through this one helper.
    """
    current: dict[str, str | None] = {}
    for ch in changes:
        p = ch["path"]
        try:
            current[p] = (
                coerce_read_content(workspace.read_text(p)) if workspace.exists(p) else None
            )
        except Exception:  # noqa: BLE001 - unreadable => unsafe
            current[p] = None
    return current


def _preview_sync(workspace: Any, changes: list[dict[str, Any]]) -> RewindPreviewModel:
    current = _current_contents(workspace, changes)
    groups = classify_rewind(changes, current)
    return RewindPreviewModel(
        safe=[_rf(g) for g in groups["safe"]],
        unsafe=[_rf(g) for g in groups["unsafe"]],
        ignored=[_rf(g) for g in groups["ignored"]],
        can_apply=bool(groups["safe"]) and not groups["unsafe"],
    )


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
    state = await asyncio.to_thread(_turn_state, agent_id, thread_id, message_id)
    return await asyncio.to_thread(_preview_sync, workspace, state["changes"])


def _rewind_sync(workspace: Any, changes: list[dict[str, Any]]) -> RewindApplyModel:
    current = _current_contents(workspace, changes)
    groups = classify_rewind(changes, current)
    if groups["unsafe"]:
        return RewindApplyModel(applied=[], blocked=[f["path"] for f in groups["unsafe"]])
    return RewindApplyModel(applied=apply_rewind(workspace, groups["safe"]))


@router.post(
    "/agents/{agent_id}/threads/{thread_id}/messages/{message_id}/files/rewind/apply",
    summary="Rewind this turn's files to their pre-turn content",
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
    """All-or-nothing: when any file is unsafe, nothing is written.

    A partially applied rewind would mix restored and still-changed files, so
    the caller must resolve or accept the unsafe files first.
    """
    workspace = await require_agent_workspace(
        agent_id, user=user, server=server, as_user=as_user, owner_only=True
    )
    state = await asyncio.to_thread(_turn_state, agent_id, thread_id, message_id)
    result = await asyncio.to_thread(_rewind_sync, workspace, state["changes"])
    if result.applied:
        # Bookkeeping only: the workspace was already rewound, so a marker
        # failure must never turn a finished rewind into a 5xx (the caller
        # would retry and just get `blocked` for the already-restored files).
        try:
            await asyncio.to_thread(
                mark_turn_reverted,
                PathLayout.from_env().root,
                agent_id,
                thread_id,
                message_id,
            )
        except Exception:  # noqa: BLE001 - never report a finished rewind as failed
            logger.warning(
                "failed to mark turn reverted (agent=%s thread=%s msg=%s)",
                agent_id,
                thread_id,
                message_id,
                exc_info=True,
            )
    return result
