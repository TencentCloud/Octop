"""Generic settings dispatch. Plugins own forms, schemas and persistence."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from octop.api.deps import get_server, require_permission
from octop.infra.agents.plugins.channel_catalog import channels, groups, load_group_names
from octop.infra.server import OctopServer

router = APIRouter()


def _provider(plugin_id: str) -> Any:
    from octop_harness.plugins import PluginRegistry

    plugin = PluginRegistry().get(plugin_id)
    provider = getattr(plugin, "settings", None)
    if provider is None:
        raise HTTPException(status_code=404, detail="Plugin settings provider is not loaded")
    return provider


async def _context(server: OctopServer, *, resolve_names: bool = False) -> dict[str, Any]:
    instances = await asyncio.to_thread(channels, server)
    conversations = await asyncio.to_thread(groups, server)
    if resolve_names:
        await load_group_names(server, conversations)
    configured = None
    try:
        if server.app_runtime is not None:
            decision = await asyncio.to_thread(server.app_runtime.agent_registry.decision.load)
            configured = decision.active
    except Exception:
        pass  # Optional model availability must not block plugin settings.
    return {"channels": instances, "groups": conversations, "decisionModelConfigured": configured}


@router.get("/{plugin_id}/settings", summary="Read settings from an installed plugin")
async def get_plugin_settings(
    plugin_id: str,
    server: OctopServer = Depends(get_server),
    _user: Any = Depends(require_permission("plugins")),
) -> dict[str, Any]:
    provider = _provider(plugin_id)
    result = await provider.get_settings(await _context(server, resolve_names=True))
    if not isinstance(result, dict):
        raise HTTPException(
            status_code=500, detail="Plugin settings provider must return an object"
        )
    return result


@router.put(
    "/{plugin_id}/settings", summary="Validate and save settings through an installed plugin"
)
async def put_plugin_settings(
    plugin_id: str,
    values: dict[str, Any],
    server: OctopServer = Depends(get_server),
    _user: Any = Depends(require_permission("plugins")),
) -> dict[str, str]:
    provider = _provider(plugin_id)
    try:
        await provider.save_settings(await _context(server), values)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "ok"}
