"""Agent secret-slot management (metadata only — values are never returned)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from octop.api.common.agent import require_agent_owner_row
from octop.api.deps import current_user, get_server
from octop.infra.errors import ErrorCode, OctopError

router = APIRouter()


def _slot_to_dict(row: Any) -> dict[str, Any]:
    return {
        "secret_id": row.secret_id,
        "slot_name": row.slot_name,
        "display_name": row.display_name,
        "created_at": row.created_at,
        "rotated_at": row.rotated_at,
    }


@router.get("/agents/{agent_id}/secrets", summary="List agent secret slots")
async def list_agent_secrets(
    agent_id: str,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Slot metadata for chat-collected secrets. Values are never returned."""
    require_agent_owner_row(agent_id, user=user, as_user=None, server=server)
    registry = server.app_runtime.agent_registry
    rows = registry.agent_secrets.list_slots(agent_id)
    return {"secrets": [_slot_to_dict(row) for row in rows]}


@router.delete("/agents/{agent_id}/secrets/{secret_id}", summary="Delete an agent secret slot")
async def delete_agent_secret(
    agent_id: str,
    secret_id: str,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Delete one stored slot and queue a harness reload to drop its env var."""
    require_agent_owner_row(agent_id, user=user, as_user=None, server=server)
    registry = server.app_runtime.agent_registry
    if not registry.agent_secrets.delete_slot(agent_id, secret_id):
        raise OctopError(ErrorCode.NOT_FOUND, f"secret slot {secret_id} not found")
    registry.schedule_reload(agent_id)
    return {"deleted": True}
