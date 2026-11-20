"""Git status/diff/log and staging endpoints for an agent workspace."""

from __future__ import annotations

import asyncio
import json
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from octop.api.common.agent import require_agent_owner_row
from octop.api.common.agent_workspace import resolve_agent_workspace_dir
from octop.api.common.workspace import require_running_workspace
from octop.api.deps import current_user, get_server
from octop.infra.git import (
    MIN_GIT_VERSION,
    HostGitTarget,
    SandboxGitTarget,
    commit_paths,
    discard_paths,
    get_diff,
    get_history,
    get_log,
    get_status,
    push_branch,
    resolve_git_binary,
    spec_uses_docker,
    stage_paths,
    unstage_paths,
)
from octop.infra.git.message import generate_commit_message
from octop.infra.text_assist import require_host_models
from octop.infra.utils.locale import resolve_request_locale

router = APIRouter()


def _agent_config(row: Any) -> dict[str, Any]:
    try:
        data = json.loads(row.config_json or "{}")
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _configured_git(server: Any) -> str | None:
    config = getattr(server, "config", None)
    value = getattr(config, "git_binary", "") if config is not None else ""
    return str(value or "").strip() or None


async def _git_target(
    agent_id: str,
    *,
    user: Any,
    as_user: int | None,
    server: Any,
    row: Any = None,
) -> Any:
    """Git target that runs where the workspace files live."""
    if row is None:
        row = require_agent_owner_row(agent_id, user=user, as_user=as_user, server=server)
    config = _agent_config(row)
    if spec_uses_docker(config.get("backend")):
        workspace = await require_running_workspace(
            agent_id, user=user, as_user=as_user, server=server, owner_only=True
        )
        return SandboxGitTarget(workspace)
    ws_dir = resolve_agent_workspace_dir(server, agent_id)
    binary = resolve_git_binary(_configured_git(server))
    return HostGitTarget(ws_dir, binary)


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
    message: str = Field(..., description="Commit message used (generated when empty)")
    pushed: bool = Field(False, description="True when the commit was followed by a push")


class GitPathsBody(BaseModel):
    paths: list[str] = Field(..., min_length=1, description="Repo-relative paths")


class GitCommitBody(BaseModel):
    message: str = Field(
        "",
        description="Commit message; leave empty to generate one with the current model",
    )
    include_unstaged: bool = Field(
        False, description="Stage all worktree changes before committing"
    )
    push: bool = Field(False, description="Push the current branch after committing")


class GitMessageBody(BaseModel):
    include_unstaged: bool = Field(
        True, description="Include worktree changes when summarising for the model"
    )


class GitMessageResultModel(BaseModel):
    message: str


class GitPushResultModel(BaseModel):
    branch: str
    remote: str
    upstream: str
    set_upstream: bool
    output: str = Field("", description="Tail of git push output")


class GitHistoryRowModel(BaseModel):
    graph: str = Field(..., description="Graph prefix (merge lanes) for this row")
    sha: str | None = None
    short: str | None = None
    author: str | None = None
    date: str | None = None
    refs: str | None = None
    signature: str | None = Field(None, description="git %G? signature status: G/B/U/X/Y/R/E/N")
    signer: str | None = None
    subject: str | None = None


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
    target = await _git_target(agent_id, user=user, as_user=as_user, server=server)
    snapshot = await get_status(target)
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
    target = await _git_target(agent_id, user=user, as_user=as_user, server=server)
    result = await get_diff(target, path, staged=staged)
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
    target = await _git_target(agent_id, user=user, as_user=as_user, server=server)
    commits = await get_log(target, limit=limit)
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
    target = await _git_target(agent_id, user=user, as_user=as_user, server=server)
    await stage_paths(target, body.paths)
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
    target = await _git_target(agent_id, user=user, as_user=as_user, server=server)
    await unstage_paths(target, body.paths)
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
    target = await _git_target(agent_id, user=user, as_user=as_user, server=server)
    await discard_paths(target, body.paths)
    return {"ok": True}


@router.post(
    "/agents/{agent_id}/git/commit",
    summary="Commit workspace changes",
    response_model=GitCommitResultModel,
)
async def workspace_git_commit(
    agent_id: str,
    body: GitCommitBody,
    request: Request,
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> Any:
    """Commit staged changes, optionally all worktree changes, then push.

    An empty ``message`` is generated from the current turn's diffs with the
    host model (Conventional Commit, same language as the request).
    """
    row = require_agent_owner_row(agent_id, user=user, as_user=as_user, server=server)
    target = await _git_target(agent_id, user=user, as_user=as_user, server=server, row=row)
    message = body.message.strip()
    if not message:
        message = await generate_commit_message(
            models=require_host_models(server),
            target=target,
            include_unstaged=body.include_unstaged,
            locale=resolve_request_locale(request),
            default_model=getattr(row, "default_model", None),
        )
    result = await commit_paths(target, message, include_unstaged=body.include_unstaged)
    pushed = False
    if body.push:
        await push_branch(target)
        pushed = True
    return GitCommitResultModel(commit=result["commit"], message=message, pushed=pushed)


@router.post(
    "/agents/{agent_id}/git/message",
    summary="Generate a commit message",
    response_model=GitMessageResultModel,
)
async def workspace_git_message(
    agent_id: str,
    body: GitMessageBody,
    request: Request,
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> Any:
    """Generate a Conventional Commit message for the pending changes."""
    row = require_agent_owner_row(agent_id, user=user, as_user=as_user, server=server)
    target = await _git_target(agent_id, user=user, as_user=as_user, server=server, row=row)
    message = await generate_commit_message(
        models=require_host_models(server),
        target=target,
        include_unstaged=body.include_unstaged,
        locale=resolve_request_locale(request),
        default_model=getattr(row, "default_model", None),
    )
    return GitMessageResultModel(message=message)


@router.post(
    "/agents/{agent_id}/git/push",
    summary="Push the current branch",
    response_model=GitPushResultModel,
)
async def workspace_git_push(
    agent_id: str,
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> Any:
    """Push the current branch (never forces; sets upstream on first push)."""
    target = await _git_target(agent_id, user=user, as_user=as_user, server=server)
    result = await push_branch(target)
    return GitPushResultModel(
        branch=str(result["branch"]),
        remote=str(result["remote"]),
        upstream=str(result["upstream"]),
        set_upstream=bool(result["set_upstream"]),
        output=str(result["output"]),
    )


@router.get(
    "/agents/{agent_id}/git/history",
    summary="Commit history with graph and signatures",
    response_model=list[GitHistoryRowModel],
)
async def workspace_git_history(
    agent_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> Any:
    """``git log --graph`` rows; ``signature`` carries git's ``%G?`` status."""
    target = await _git_target(agent_id, user=user, as_user=as_user, server=server)
    rows = await get_history(target, limit=limit)
    return [
        GitHistoryRowModel(
            graph=str(row["graph"]),
            sha=row.get("sha"),  # type: ignore[arg-type]
            short=row.get("short"),  # type: ignore[arg-type]
            author=row.get("author"),  # type: ignore[arg-type]
            date=row.get("date"),  # type: ignore[arg-type]
            refs=row.get("refs"),  # type: ignore[arg-type]
            signature=row.get("signature"),  # type: ignore[arg-type]
            signer=row.get("signer"),  # type: ignore[arg-type]
            subject=row.get("subject"),  # type: ignore[arg-type]
        )
        for row in rows
    ]


class GitRuntimeModel(BaseModel):
    available: bool = Field(..., description="A usable host git binary was found")
    path: str | None = Field(None, description="Resolved executable path")
    version: str | None = Field(None, description="Resolved git version")
    source: str | None = Field(
        None, description="Where it came from: config / env / path / fallback"
    )
    min_required: str = Field(..., description="Minimum supported git version")


@router.get(
    "/settings/git",
    summary="Host git runtime",
    response_model=GitRuntimeModel,
)
async def settings_git(
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> Any:
    """Resolved host git for self-hosted diagnostics.

    Sandbox workspaces run git inside their container; this reports the host
    binary used by local workspaces (and by the workspace file tree).
    """
    binary = await asyncio.to_thread(resolve_git_binary, _configured_git(server))
    return GitRuntimeModel(
        available=binary is not None,
        path=binary.path if binary else None,
        version=binary.version_text if binary else None,
        source=binary.source if binary else None,
        min_required=".".join(str(part) for part in MIN_GIT_VERSION),
    )
