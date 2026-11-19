"""Git status/diff/log and staging endpoints for an agent workspace."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from octop.api.common.agent import require_agent_owner_row
from octop.api.common.agent_workspace import resolve_agent_workspace_dir
from octop.api.deps import current_user, get_server
from octop.infra.git import (
    commit_paths,
    discard_paths,
    get_diff,
    get_log,
    get_status,
    stage_paths,
    unstage_paths,
)

router = APIRouter()


def _git_workspace(
    agent_id: str,
    *,
    user: Any,
    as_user: int | None,
    server: Any,
) -> Path:
    require_agent_owner_row(agent_id, user=user, as_user=as_user, server=server)
    return resolve_agent_workspace_dir(server, agent_id)


class GitFileChangeModel(BaseModel):
    path: str = Field(..., description="Repo-relative file path")
    status: Literal[
        "modified",
        "added",
        "deleted",
        "renamed",
        "copied",
        "typechange",
        "untracked",
        "conflicted",
    ] = Field(..., description="Change kind")
    staged: bool = Field(..., description="True when the change is in the index")
    added: int | None = Field(None, description="Added lines (null for binary/dirs)")
    removed: int | None = Field(None, description="Removed lines (null for binary/dirs)")
    orig_path: str | None = Field(None, description="Original path for renames/copies")


class GitStatusModel(BaseModel):
    is_repo: bool = Field(..., description="False when the workspace has no ``.git``")
    git_available: bool = Field(..., description="False when the git CLI is missing")
    branch: str | None = None
    upstream: str | None = None
    ahead: int = 0
    behind: int = 0
    head_short: str | None = None
    files: list[GitFileChangeModel] = Field(default_factory=list)
    added: int = 0
    removed: int = 0


class GitDiffModel(BaseModel):
    path: str
    diff: str = Field(..., description="Unified diff text (empty when identical)")
    truncated: bool = Field(..., description="True when the diff hit the size cap")


class GitCommitModel(BaseModel):
    sha: str
    short: str
    author: str
    date: str = Field(..., description="ISO-8601 author date")
    subject: str


class GitCommitResultModel(BaseModel):
    commit: str = Field(..., description="Short SHA of the new commit")


class GitPathsBody(BaseModel):
    paths: list[str] = Field(..., min_length=1, description="Repo-relative paths")


class GitCommitBody(BaseModel):
    message: str = Field(..., min_length=1, description="Commit message")


@router.get(
    "/agents/{agent_id}/git/status",
    summary="Workspace git status",
    response_model=GitStatusModel,
)
async def workspace_git_status(
    agent_id: str,
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> Any:
    """Porcelain status, branch summary and per-file line stats.

    Returns ``is_repo=false`` (no git commands run) when the workspace root has
    no ``.git``; remote-backend workspaces therefore report not-a-repo.
    """
    ws_dir = _git_workspace(agent_id, user=user, as_user=as_user, server=server)
    snapshot = await get_status(ws_dir)
    return GitStatusModel(
        is_repo=snapshot.is_repo,
        git_available=snapshot.git_available,
        branch=snapshot.branch,
        upstream=snapshot.upstream,
        ahead=snapshot.ahead,
        behind=snapshot.behind,
        head_short=snapshot.head_short,
        files=[
            GitFileChangeModel(
                path=f.path,
                status=f.status,  # type: ignore[arg-type]
                staged=f.staged,
                added=f.added,
                removed=f.removed,
                orig_path=f.orig_path,
            )
            for f in snapshot.files
        ],
        added=snapshot.added,
        removed=snapshot.removed,
    )


@router.get(
    "/agents/{agent_id}/git/diff",
    summary="Single-file workspace diff",
    response_model=GitDiffModel,
)
async def workspace_git_diff(
    agent_id: str,
    path: str = Query(..., description="Repo-relative file path"),
    staged: bool = Query(default=False, description="Diff the index instead of the worktree"),
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> Any:
    """Unified diff for one file; untracked files diff against ``/dev/null``."""
    ws_dir = _git_workspace(agent_id, user=user, as_user=as_user, server=server)
    result = await get_diff(ws_dir, path, staged=staged)
    return GitDiffModel(
        path=str(result["path"]),
        diff=str(result["diff"]),
        truncated=bool(result["truncated"]),
    )


@router.get(
    "/agents/{agent_id}/git/log",
    summary="Recent workspace commits",
    response_model=list[GitCommitModel],
)
async def workspace_git_log(
    agent_id: str,
    limit: int = Query(default=30, ge=1, le=200),
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> Any:
    """Most recent commits on the current branch (newest first)."""
    ws_dir = _git_workspace(agent_id, user=user, as_user=as_user, server=server)
    commits = await get_log(ws_dir, limit=limit)
    return [
        GitCommitModel(sha=c.sha, short=c.short, author=c.author, date=c.date, subject=c.subject)
        for c in commits
    ]


@router.post(
    "/agents/{agent_id}/git/stage",
    summary="Stage workspace files",
)
async def workspace_git_stage(
    agent_id: str,
    body: GitPathsBody,
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, bool]:
    ws_dir = _git_workspace(agent_id, user=user, as_user=as_user, server=server)
    await stage_paths(ws_dir, body.paths)
    return {"ok": True}


@router.post(
    "/agents/{agent_id}/git/unstage",
    summary="Unstage workspace files",
)
async def workspace_git_unstage(
    agent_id: str,
    body: GitPathsBody,
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, bool]:
    ws_dir = _git_workspace(agent_id, user=user, as_user=as_user, server=server)
    await unstage_paths(ws_dir, body.paths)
    return {"ok": True}


@router.post(
    "/agents/{agent_id}/git/discard",
    summary="Discard workspace changes",
    description=(
        "Destructive: tracked files are restored from the index, untracked "
        "files and directories are deleted. Callers must confirm first."
    ),
)
async def workspace_git_discard(
    agent_id: str,
    body: GitPathsBody,
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, bool]:
    ws_dir = _git_workspace(agent_id, user=user, as_user=as_user, server=server)
    await discard_paths(ws_dir, body.paths)
    return {"ok": True}


@router.post(
    "/agents/{agent_id}/git/commit",
    summary="Commit staged workspace changes",
    response_model=GitCommitResultModel,
)
async def workspace_git_commit(
    agent_id: str,
    body: GitCommitBody,
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> Any:
    ws_dir = _git_workspace(agent_id, user=user, as_user=as_user, server=server)
    result = await commit_paths(ws_dir, body.message)
    return GitCommitResultModel(commit=result["commit"])
