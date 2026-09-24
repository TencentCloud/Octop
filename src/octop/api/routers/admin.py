"""Admin overview/audit/metrics router."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from octop.api.deps import get_server, require_permission

router = APIRouter()


@router.get("/overview")
async def overview(
    _: Any = Depends(require_permission("admin_console")), server: Any = Depends(get_server)
) -> dict[str, Any]:
    assert server.app_runtime is not None
    users = []
    for user in server.user_manager.list():
        users.append(
            {
                "username": user.username,
                "role": user.role.value,
                "agents": [],  # agents are now global, not per-user
            }
        )
    agents = [
        {
            "id": r.id,
            "agent_id": r.agent_id,
            "name": r.name,
            "state": r.last_state or "unknown",
        }
        for r in server.app_runtime.agent_registry.list_rows()
    ]
    return {
        "users": users,
        "agents": agents,
        "totals": {
            "users": len(users),
            "agents": len(agents),
        },
    }


# The largest page the Settings → Security audit panel offers.
AUDIT_LOG_MAX_LIMIT = 500


@router.get("/audit-log")
async def audit_log(
    since: int | None = None,
    actor: str | None = None,
    action: str | None = None,
    limit: int = Query(
        default=100,
        ge=1,
        le=AUDIT_LOG_MAX_LIMIT,
        description=f"Maximum rows to return, between 1 and {AUDIT_LOG_MAX_LIMIT}.",
    ),
    _: Any = Depends(require_permission("admin_console")),
    server: Any = Depends(get_server),
) -> list[dict[str, Any]]:
    rows = server.services.audit_repo.query(since=since, actor=actor, action=action, limit=limit)
    return [
        {
            "id": r.id,
            "ts": r.ts,
            "actor": r.actor,
            "action": r.action,
            "target": r.target,
            "payload": r.payload,
        }
        for r in rows
    ]


@router.get("/metrics")
async def metrics(
    _: Any = Depends(require_permission("admin_console")), server: Any = Depends(get_server)
) -> dict[str, Any]:
    from octop.infra.metrics import METRICS

    assert server.app_runtime is not None
    METRICS.set(
        "agent_active",
        len(server.app_runtime.agent_registry.list_rows()),
    )
    return METRICS.snapshot()
