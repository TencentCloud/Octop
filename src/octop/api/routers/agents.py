"""Agents router."""

from __future__ import annotations

import json
import logging
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query

from octop.api.common.agent import assert_agent_access_row, assert_agent_owner
from octop.api.common.agent_runtime import AgentRuntimeFields, runtime_field_updates
from octop.api.deps import current_user, get_server
from octop.infra.agents.runtime_limits import (
    AGENT_RUNTIME_CONFIG_KEYS,
    agent_runtime_values,
)
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.users.permissions import user_has_permission

logger = logging.getLogger(__name__)

router = APIRouter()


class AgentCreateBody(AgentRuntimeFields):
    name: str
    description: str | None = None
    persona_mbti: str | None = None
    default_model: str | None = None
    system_prompt: str | None = None
    config: dict[str, Any] = {}
    icon: str | None = None
    template_name: str | None = None
    is_shared: bool = False


class AgentPatchBody(AgentRuntimeFields):
    name: str | None = None
    description: str | None = None
    persona_mbti: str | None = None
    default_model: str | None = None
    system_prompt: str | None = None
    config: dict[str, Any] | None = None
    icon: str | None = None
    template_name: str | None = None
    is_shared: bool | None = None


def _attach_unread_counts(
    server: Any, user_id: int, payloads: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    agent_ids = [p["agent_id"] for p in payloads]
    totals = server.services.session_repo.unread_totals_by_agent(user_id, agent_ids)
    for payload in payloads:
        payload["unread_count"] = totals.get(payload["agent_id"], 0)
    return payloads


def _bootstrap_pending_for(server: Any, agent_id: str) -> bool:
    return not server.app_runtime.agent_registry.is_bootstrapped(agent_id)


def _memory_maintenance_status(server: Any, agent_id: str) -> dict[str, Any] | None:
    """Phase snapshot while this agent's SQLite is being slimmed. None if idle/unloaded."""
    try:
        agent = server.app_runtime.agent_registry.get_agent(agent_id)
    except OctopError:
        return None
    except Exception:
        logger.debug("memory_maintenance status unavailable for %s", agent_id, exc_info=True)
        return None
    fn = getattr(agent, "memory_maintenance_status", None)
    if not callable(fn):
        return None
    try:
        status = fn()
    except Exception:
        logger.debug("memory_maintenance status failed for %s", agent_id, exc_info=True)
        return None
    # ``fn`` is reached through getattr, so its result is untyped: only hand a
    # real mapping to the JSON response, never whatever the duck-typed call returned.
    return status if isinstance(status, dict) else None


def _owner_username(server: Any, row: Any) -> str | None:
    if row.user_id is None:
        return None
    owner = server.services.user_repo.get(row.user_id)
    return owner.username if owner is not None else None


def _row_dict(
    row: Any,
    *,
    viewer_user_id: int | None = None,
    owner_username: str | None = None,
    bootstrap_pending: bool | None = None,
) -> dict[str, Any]:
    try:
        cfg = json.loads(row.config_json or "{}")
    except (json.JSONDecodeError, AttributeError):
        cfg = {}
    if not isinstance(cfg, dict):
        cfg = {}
    public_cfg = {key: value for key, value in cfg.items() if key not in AGENT_RUNTIME_CONFIG_KEYS}
    payload: dict[str, Any] = {
        "id": row.id,
        "agent_id": row.agent_id,
        "user_id": row.user_id,
        "name": row.name,
        "description": row.description,
        "persona_mbti": row.persona_mbti,
        "default_model": row.default_model,
        "system_prompt": row.system_prompt,
        "state": row.last_state or "unknown",
        "last_error": row.last_error,
        "config": public_cfg,
        "icon": row.icon,
        "template_name": row.template_name,
        "icon_name": cfg.get("icon_name"),
        "color": cfg.get("color"),
        "is_shared": bool(int(getattr(row, "is_shared", 0) or 0)),
        "is_owner": row.user_id is not None and row.user_id == viewer_user_id,
        "owner_username": owner_username,
        **agent_runtime_values(cfg),
    }
    if bootstrap_pending is not None:
        payload["bootstrap_pending"] = bootstrap_pending
    return payload


@router.get("", summary="List agents")
async def list_agents(
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
    scope: Literal["mine", "all"] = Query(
        "mine",
        description="mine: agents owned by the current user; all: every agent (admin only)",
    ),
) -> list[dict[str, Any]]:
    """List agents for the dashboard.

    Default ``scope=mine`` returns agents owned by the authenticated user plus
    agents other users have explicitly shared.
    Holders of the ``users`` permission (and admins) may pass ``scope=all``.
    """
    if scope == "all" and not user_has_permission(user, "users"):
        raise OctopError(
            ErrorCode.FORBIDDEN,
            "permission required",
            details={"permission": "users"},
        )

    assert server.app_runtime is not None
    registry = server.app_runtime.agent_registry
    if scope == "all":
        rows = registry.list_rows()
        user_ids = {r.user_id for r in rows if r.user_id is not None}
        username_by_id: dict[int, str] = {}
        for uid in user_ids:
            owner = server.services.user_repo.get(uid)
            if owner is not None:
                username_by_id[uid] = owner.username
        payloads = [
            _row_dict(
                r,
                viewer_user_id=user.id,
                owner_username=username_by_id.get(r.user_id) if r.user_id is not None else None,
                bootstrap_pending=_bootstrap_pending_for(server, r.agent_id),
            )
            for r in rows
        ]
        return _attach_unread_counts(server, user.id, payloads)

    owned = registry.list_agents(user.id)
    shared = server.services.agent_repo.list_shared(exclude_user_id=user.id)
    rows = list({row.agent_id: row for row in [*shared, *owned]}.values())
    shared_owner_username_by_id: dict[int, str] = {}
    for row in shared:
        if row.user_id is None or row.user_id in shared_owner_username_by_id:
            continue
        owner = server.services.user_repo.get(row.user_id)
        if owner is not None:
            shared_owner_username_by_id[row.user_id] = owner.username
    return _attach_unread_counts(
        server,
        user.id,
        [
            _row_dict(
                r,
                viewer_user_id=user.id,
                owner_username=(
                    shared_owner_username_by_id.get(r.user_id) if r.user_id is not None else None
                ),
                bootstrap_pending=_bootstrap_pending_for(server, r.agent_id),
            )
            for r in rows
        ],
    )


@router.post("", status_code=201, summary="Create agent")
async def create_agent(
    body: AgentCreateBody,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Create a new agent from a template or custom config for the current user."""
    from octop.infra.agents.manager import AgentCreateSpec  # noqa: PLC0415

    assert server.app_runtime is not None
    spec = AgentCreateSpec(
        name=body.name,
        user_id=user.id,
        description=body.description,
        persona_mbti=body.persona_mbti,
        default_model=body.default_model,
        system_prompt=body.system_prompt,
        config=body.config,
        runtime_config=runtime_field_updates(body, exclude_unset=True),
        icon=body.icon,
        template_name=body.template_name,
        is_shared=body.is_shared,
    )
    row = await server.app_runtime.agent_registry.create(spec)
    return _row_dict(
        row,
        viewer_user_id=user.id,
        owner_username=user.username,
        bootstrap_pending=_bootstrap_pending_for(server, row.agent_id),
    )


@router.post("/{agent_id}/read", status_code=204, summary="Mark agent read")
async def mark_agent_read(
    agent_id: str,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> None:
    """Clear unread counts for all of the user's sessions under this agent."""
    assert server.app_runtime is not None
    row = server.app_runtime.agent_registry.get_row(agent_id)
    if row is None:
        raise OctopError(ErrorCode.AGENT_NOT_FOUND, f"agent {agent_id!r} not found")
    _assert_agent_owner(row, user)
    server.services.session_repo.clear_unread_for_agent(agent_id, user.id)


@router.get("/{agent_id}", summary="Get agent")
async def get_agent(
    agent_id: str,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Return full configuration and runtime state for one agent."""
    assert server.app_runtime is not None
    row = server.app_runtime.agent_registry.get_row(agent_id)
    if row is None:
        raise OctopError(ErrorCode.AGENT_NOT_FOUND, f"agent {agent_id!r} not found")
    assert_agent_access_row(row, user)
    return _row_dict(
        row,
        viewer_user_id=user.id,
        owner_username=_owner_username(server, row),
        bootstrap_pending=_bootstrap_pending_for(server, agent_id),
    )


_assert_agent_owner = assert_agent_owner


@router.patch("/{agent_id}", summary="Update agent")
async def patch_agent(
    agent_id: str,
    body: AgentPatchBody,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Partially update agent fields. Owner or admin only."""
    assert server.app_runtime is not None
    row = server.app_runtime.agent_registry.get_row(agent_id)
    if row is None:
        raise OctopError(ErrorCode.AGENT_NOT_FOUND, f"agent {agent_id!r} not found")
    _assert_agent_owner(row, user)
    updates = {
        key: value
        for key, value in body.model_dump(exclude_unset=True).items()
        if key not in {"config", "is_shared"}
    }
    if body.config is not None:
        updates["config_json"] = json.dumps(body.config)
    if updates:
        row = await server.app_runtime.agent_registry.update(agent_id, **updates)
    if body.is_shared is not None:
        row = await server.app_runtime.agent_registry.set_shared(agent_id, body.is_shared)
    return _row_dict(
        row,
        viewer_user_id=user.id,
        owner_username=user.username,
        bootstrap_pending=_bootstrap_pending_for(server, agent_id),
    )


@router.delete("/{agent_id}", status_code=204, summary="Delete agent")
async def delete_agent(
    agent_id: str,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> None:
    """Permanently remove an agent and its runtime. Owner or admin."""
    assert server.app_runtime is not None
    row = server.app_runtime.agent_registry.get_row(agent_id)
    if row is None:
        raise OctopError(ErrorCode.AGENT_NOT_FOUND, f"agent {agent_id!r} not found")
    _assert_agent_owner(row, user)
    await server.app_runtime.agent_registry.delete(agent_id)


@router.post("/{agent_id}/start", status_code=204, summary="Start agent")
async def start_agent(
    agent_id: str,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> None:
    """Load a stopped agent into the harness runtime."""
    assert server.app_runtime is not None
    row = server.app_runtime.agent_registry.get_row(agent_id)
    if row is None:
        raise OctopError(ErrorCode.AGENT_NOT_FOUND, f"agent {agent_id!r} not found")
    _assert_agent_owner(row, user)
    await server.app_runtime.agent_registry.start(agent_id)


@router.post("/{agent_id}/stop", status_code=204, summary="Stop agent")
async def stop_agent(
    agent_id: str,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> None:
    """Unload agent from harness runtime; persists ``last_state=stopped``."""
    assert server.app_runtime is not None
    row = server.app_runtime.agent_registry.get_row(agent_id)
    if row is None:
        raise OctopError(ErrorCode.AGENT_NOT_FOUND, f"agent {agent_id!r} not found")
    _assert_agent_owner(row, user)
    await server.app_runtime.agent_registry.stop(agent_id)


@router.post("/{agent_id}/reload", status_code=204, summary="Reload agent")
async def reload_agent(
    agent_id: str,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> None:
    """Hot-reload agent config, skills, and MCP connectors without restarting the server."""
    assert server.app_runtime is not None
    row = server.app_runtime.agent_registry.get_row(agent_id)
    if row is None:
        raise OctopError(ErrorCode.AGENT_NOT_FOUND, f"agent {agent_id!r} not found")
    _assert_agent_owner(row, user)
    await server.app_runtime.agent_registry.reload(agent_id)


@router.get("/{agent_id}/status", summary="Agent runtime status")
async def agent_status(
    agent_id: str,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Runtime state plus attached IM channels and cron jobs for the agent."""
    assert server.app_runtime is not None
    row = server.app_runtime.agent_registry.get_row(agent_id)
    if row is None:
        raise OctopError(ErrorCode.AGENT_NOT_FOUND, f"agent {agent_id!r} not found")
    _assert_agent_owner(row, user)
    channels = server.app_runtime.gateway.list_channels(agent_id)
    cron_jobs = server.app_runtime.cron_manager.list_by_agent(agent_id)
    return {
        "state": row.last_state or "unknown",
        "last_error": row.last_error,
        "channels": [{"id": c.channel_id, "kind": c.kind, "name": c.name} for c in channels],
        "cron_jobs": [
            {"id": j.cron_id, "prompt": j.prompt, "trigger": j.trigger} for j in cron_jobs
        ],
        "memory_maintenance": _memory_maintenance_status(server, agent_id),
    }
