"""Per-agent Memory + Heartbeat endpoints.

Two related concerns share this module because they both surface
*files* in the agent's workspace plus *configuration* on the agent
row:

  GET  /api/agents/{aid}/heartbeat-config
  PUT  /api/agents/{aid}/heartbeat-config
  GET/PUT /api/agents/{aid}/memory/strong
  GET/PUT /api/agents/{aid}/memory/user
  GET  /api/agents/{aid}/memory/daily
  GET  /api/agents/{aid}/memory/daily/{filename}
  DELETE /api/agents/{aid}/memory/daily/{filename}

Heartbeat config lives at ``agent.config_json["heartbeat"]`` — the
column stores the *whole* config blob serialised, so partial updates
read-modify-write through ``agent_repo.update_config(config_json=...)``
to avoid clobbering unrelated keys (skills_disabled, backend, etc.).

Daily memory files live at ``daily/YYYY-MM-DD.md`` inside the agent's
workspace backend. Reads use the protocol surface (``aread`` / ``als``);
delete falls back to the filesystem path because
``BackendProtocol`` exposes no delete method (see
``routers/workspace.py`` for the same caveat). For backends that aren't
filesystem-rooted (S3 etc.) delete will raise — that's acceptable for
the v1 dashboard which only ever runs against ``local_shell``.

``MEMORY.md`` and ``USER.md`` are user-maintained documents exposed through
owner-only ``memory/strong`` and ``memory/user`` endpoints, including stopped agents.
The full file is snapshotted once per session; edits apply to new sessions. ``HEARTBEAT.md`` uses
the general workspace file endpoints.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field

from octop.api.common.agent import require_agent_owner_row
from octop.api.common.agent_workspace import resolve_agent_workspace_dir
from octop.api.common.memory_client import call_memory_rpc
from octop.api.common.workspace import require_agent_workspace, require_running_workspace
from octop.api.deps import current_user, get_server, require_permission
from octop.infra.errors import ErrorCode, OctopError

logger = logging.getLogger(__name__)

router = APIRouter()


class StrongMemoryBody(BaseModel):
    content: str = Field(
        description="Complete user-maintained MEMORY.md content; an empty string clears it."
    )


class StrongMemoryFile(StrongMemoryBody):
    exists: bool = Field(description="Whether MEMORY.md exists in this agent's workspace.")


class UserProfileBody(BaseModel):
    content: str = Field(
        description="Complete user-maintained USER.md content; an empty string clears it."
    )


class UserProfileFile(UserProfileBody):
    exists: bool = Field(description="Whether USER.md exists in this agent's workspace.")


@router.get(
    "/agents/{agent_id}/memory/strong",
    response_model=StrongMemoryFile,
    summary="Read strong memory",
    description="Read the current user-maintained MEMORY.md. New sessions snapshot its full content once; existing sessions keep their snapshot. Available to the owner even when the agent is stopped.",
)
async def get_strong_memory(
    agent_id: str,
    as_user: int | None = None,
    user: Any = Depends(require_permission("memory")),
    server: Any = Depends(get_server),
) -> StrongMemoryFile:
    ws = await require_agent_workspace(
        agent_id, user=user, as_user=as_user, server=server, owner_only=True
    )
    data = await ws.adownload_bytes("MEMORY.md")
    return StrongMemoryFile(
        content=data.decode("utf-8") if data is not None else "", exists=data is not None
    )


@router.put(
    "/agents/{agent_id}/memory/strong",
    response_model=StrongMemoryFile,
    summary="Save strong memory",
    description="Replace the owner's MEMORY.md with the supplied text. Edits apply to new sessions; existing sessions keep their snapshot. Ordinary remember requests are saved separately to octop-memory.",
)
async def put_strong_memory(
    agent_id: str,
    body: StrongMemoryBody,
    as_user: int | None = None,
    user: Any = Depends(require_permission("memory")),
    server: Any = Depends(get_server),
) -> StrongMemoryFile:
    require_agent_owner_row(agent_id, user=user, as_user=as_user, server=server)
    await server.app_runtime.agent_registry.save_manual_memory_document(
        agent_id, "MEMORY.md", body.content
    )
    return StrongMemoryFile(content=body.content, exists=True)


@router.get(
    "/agents/{agent_id}/memory/user",
    response_model=UserProfileFile,
    summary="Read user-maintained profile",
    description="Read USER.md for manual editing, including stopped agents. New sessions load its full content once; existing sessions keep their snapshot.",
)
async def get_user_profile(
    agent_id: str,
    as_user: int | None = None,
    user: Any = Depends(require_permission("memory")),
    server: Any = Depends(get_server),
) -> UserProfileFile:
    ws = await require_agent_workspace(
        agent_id, user=user, as_user=as_user, server=server, owner_only=True
    )
    data = await ws.adownload_bytes("USER.md")
    return UserProfileFile(
        content=data.decode("utf-8") if data is not None else "", exists=data is not None
    )


@router.put(
    "/agents/{agent_id}/memory/user",
    response_model=UserProfileFile,
    summary="Save user-maintained profile",
    description="Replace the owner's USER.md. Agents cannot edit this document. Edits apply to new sessions; remember requests use octop-memory.",
)
async def put_user_profile(
    agent_id: str,
    body: UserProfileBody,
    as_user: int | None = None,
    user: Any = Depends(require_permission("memory")),
    server: Any = Depends(get_server),
) -> UserProfileFile:
    require_agent_owner_row(agent_id, user=user, as_user=as_user, server=server)
    await server.app_runtime.agent_registry.save_manual_memory_document(
        agent_id, "USER.md", body.content
    )
    return UserProfileFile(content=body.content, exists=True)


class ManualMemoryReview(BaseModel):
    status: str = Field(
        description="complete / partial / uncertain / unavailable / failed / stale / disabled / too_large / not_checked"
    )
    conflicts: int = 0
    duplicates: int = 0
    checked: int = 0
    remaining: int = 0
    candidate_ids: list[str] = Field(default_factory=list)


@router.post(
    "/agents/{agent_id}/memory/manual-review",
    response_model=ManualMemoryReview,
    summary="Reconcile manual documents with ordinary memory",
    description="Compare the current USER.md and MEMORY.md with ordinary memories. Manual documents take priority; conflicts become review candidates and old facts stop automatic recall. Duplicate facts remain stored and are suppressed against matching chat snapshots. Partial or unavailable semantic checks are reported explicitly.",
)
async def review_manual_memory(
    agent_id: str,
    as_user: int | None = None,
    user: Any = Depends(require_permission("memory")),
    server: Any = Depends(get_server),
) -> ManualMemoryReview:
    require_agent_owner_row(agent_id, user=user, as_user=as_user, server=server)
    result = await server.app_runtime.agent_registry.review_manual_memory_documents(agent_id)
    return ManualMemoryReview.model_validate(result)


@router.get(
    "/agents/{agent_id}/memory/manual-review",
    response_model=ManualMemoryReview,
    summary="Read manual-document review status",
    description="Read the last reconciliation status for the current documents without modifying memory or invoking a model.",
)
async def get_manual_memory_review(
    agent_id: str,
    as_user: int | None = None,
    user: Any = Depends(require_permission("memory")),
    server: Any = Depends(get_server),
) -> ManualMemoryReview:
    ws = await require_agent_workspace(
        agent_id, user=user, as_user=as_user, server=server, owner_only=True
    )
    documents = {}
    for filename in ("USER.md", "MEMORY.md"):
        data = await ws.adownload_bytes(filename)
        documents[filename] = data.decode("utf-8") if data is not None else ""
    result = await asyncio.to_thread(
        call_memory_rpc,
        agent_id=agent_id,
        method="manual_document_review_status",
        params={"documents": documents},
        user=user,
        as_user=as_user,
        server=server,
    )
    return ManualMemoryReview.model_validate(result)


# --- shared agent resolution -----------------------------------------------


def _resolve_runtime(agent_id: str, *, user: Any, as_user: int | None, server: Any) -> Any:
    """Return the AgentRow for the given agent_id after auth."""
    return require_agent_owner_row(agent_id, user=user, as_user=as_user, server=server)


# --- heartbeat config ------------------------------------------------------


class HeartbeatConfigBody(BaseModel):
    enabled: bool
    every: str
    target: str
    active_hours_enabled: bool
    active_hours_start: str
    active_hours_end: str


_HEARTBEAT_DEFAULT: dict[str, Any] = {
    "enabled": False,
    "every": "30m",
    "target": "main",
    "active_hours_enabled": False,
    "active_hours_start": "08:00",
    "active_hours_end": "22:00",
}


def _load_full_config(server: Any, agent_id: str) -> dict[str, Any]:
    """Read agent.config_json as a dict via AgentManager."""
    assert server.app_runtime is not None
    cfg = server.app_runtime.agent_registry.get_config(agent_id)
    return cfg if isinstance(cfg, dict) else {}


@router.get("/agents/{agent_id}/heartbeat-config")
async def get_heartbeat_config(
    agent_id: str,
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    # Resolve runtime first — this enforces user ownership before we
    # peek at the config row.
    _resolve_runtime(agent_id, user=user, as_user=as_user, server=server)
    cfg = _load_full_config(server, agent_id)
    raw_hb = cfg.get("heartbeat")
    hb = raw_hb if isinstance(raw_hb, dict) else {}
    # Spread defaults under any missing keys so the frontend never has
    # to handle a half-populated config.
    return {**_HEARTBEAT_DEFAULT, **hb}


@router.put("/agents/{agent_id}/heartbeat-config")
async def put_heartbeat_config(
    agent_id: str,
    body: HeartbeatConfigBody,
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    _resolve_runtime(agent_id, user=user, as_user=as_user, server=server)
    cfg = _load_full_config(server, agent_id)
    # Merge — never replace the whole config_json: skills_disabled,
    # backend spec, proactive config etc. live alongside heartbeat in
    # the same blob.
    cfg["heartbeat"] = body.model_dump()
    await server.app_runtime.agent_registry.update_config_json(agent_id, json.dumps(cfg))
    saved = cfg.get("heartbeat")
    return saved if isinstance(saved, dict) else body.model_dump()


# --- daily memory ----------------------------------------------------------

# YYYY-MM-DD.md — anchored regex prevents path traversal in filename inputs.
_DAILY_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.md$")


def _validate_filename(filename: str) -> str:
    m = _DAILY_RE.match(filename)
    if not m:
        raise OctopError(
            ErrorCode.NOT_FOUND,
            f"invalid daily memory filename {filename!r} (expected YYYY-MM-DD.md)",
        )
    return m.group(1)


@router.get("/agents/{agent_id}/memory/daily")
async def list_daily_memory(
    agent_id: str,
    as_user: int | None = None,
    user: Any = Depends(require_permission("memory")),
    server: Any = Depends(get_server),
) -> list[dict[str, Any]]:
    rt = _resolve_runtime(agent_id, user=user, as_user=as_user, server=server)
    ws = await require_running_workspace(rt.agent_id, user=user, as_user=as_user, server=server)
    result = await ws.als("daily")
    if result is None:
        return []
    err = getattr(result, "error", None)
    if err:
        return []
    entries = getattr(result, "entries", None) or []
    out: list[dict[str, Any]] = []
    for info in entries:
        # ``FileInfo`` is a TypedDict; use .get to stay loose.
        path = info.get("path") if isinstance(info, dict) else None
        if not path:
            continue
        # ``als`` returns paths *relative* on some backends and
        # *absolute* on others — normalise to bare filename.
        filename = path.rsplit("/", 1)[-1]
        m = _DAILY_RE.match(filename)
        if not m:
            continue
        item: dict[str, Any] = {
            "filename": filename,
            "date": m.group(1),
            "size": int(info.get("size") or 0),
        }
        if "modified_at" in info:
            item["modified_at"] = info["modified_at"]
        out.append(item)
    out.sort(key=lambda d: d["date"], reverse=True)
    return out


@router.get("/agents/{agent_id}/memory/daily/{filename}")
async def read_daily_memory(
    agent_id: str,
    filename: str,
    as_user: int | None = None,
    user: Any = Depends(require_permission("memory")),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    date = _validate_filename(filename)
    rt = _resolve_runtime(agent_id, user=user, as_user=as_user, server=server)
    ws = await require_running_workspace(rt.agent_id, user=user, as_user=as_user, server=server)
    target = f"daily/{filename}"
    content = await ws.aread_text(target)
    if content is None:
        raise OctopError(ErrorCode.NOT_FOUND, f"cannot read {target!r}")
    return {"date": date, "filename": filename, "content": str(content)}


@router.delete("/agents/{agent_id}/memory/daily/{filename}", status_code=204)
async def delete_daily_memory(
    agent_id: str,
    filename: str,
    as_user: int | None = None,
    user: Any = Depends(require_permission("memory")),
    server: Any = Depends(get_server),
) -> Response:
    _validate_filename(filename)
    rt = _resolve_runtime(agent_id, user=user, as_user=as_user, server=server)
    # ``BackendProtocol`` has no delete — fall back to the filesystem
    # path we know lives behind the local_shell / filesystem backends.
    workspace = resolve_agent_workspace_dir(server, rt.agent_id)
    target = (workspace / "daily" / filename).resolve()
    # Belt-and-suspenders: regex already pinned the format, but resolve()
    # + relative_to() guarantees we stay inside the workspace if anyone
    # ever loosens the regex.
    try:
        target.relative_to(workspace.resolve())
    except ValueError as exc:
        raise OctopError(ErrorCode.FORBIDDEN, "path escapes workspace") from exc
    if not target.exists():
        raise OctopError(ErrorCode.NOT_FOUND, f"daily memory {filename!r} not found")
    target.unlink()
    return Response(status_code=204)
