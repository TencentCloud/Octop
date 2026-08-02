"""Plugin install and agent tool configuration."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from octop.api.common.agent import assert_agent_owner as _assert_agent_owner
from octop.api.deps import current_user, get_server
from octop.infra.agents.plugins.manager import PluginManager
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.server import OctopServer

router = APIRouter(prefix="/plugins", tags=["plugins"])


class PluginInstallBody(BaseModel):
    url: str = Field(..., description="HTTP(S) URL to a plugin ZIP archive")


class AgentPluginToolBody(BaseModel):
    enabled: bool | None = None
    config: dict[str, Any] | None = None


class AgentPluginToolsPatch(BaseModel):
    """Patch per-agent plugin tool settings under ``config_json.plugins``."""

    plugins: dict[str, dict[str, Any]]


def _plugin_manager(server: OctopServer) -> PluginManager:
    mgr = server.plugin_manager
    if mgr is None:
        raise OctopError(ErrorCode.INTERNAL_ERROR, "plugin manager not initialized")
    return mgr


def _require_admin(user: Any) -> None:
    if not getattr(user, "is_admin", False):
        raise OctopError(ErrorCode.FORBIDDEN, "admin only")


@router.get("", summary="List installed plugins")
async def list_plugins(
    server: OctopServer = Depends(get_server),
    _user: Any = Depends(current_user),
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = _plugin_manager(server).list_installed()
    return items


@router.post("/install", summary="Install plugin from URL (admin)")
async def install_plugin(
    body: PluginInstallBody,
    server: OctopServer = Depends(get_server),
    user: Any = Depends(current_user),
) -> dict[str, Any]:
    _require_admin(user)
    mgr = _plugin_manager(server)
    try:
        loaded = mgr.install_url(body.url)
    except OctopError:
        raise
    except Exception as exc:
        raise OctopError(
            ErrorCode.PLUGIN_INSTALL_FAILED,
            f"plugin install failed: {exc}",
            details={"reason": str(exc)},
        ) from exc
    if server.app_runtime is not None:
        mgr.load_installed(install_deps=False)
        await server.app_runtime.agent_registry.reload_all()
    return {
        "id": loaded.manifest.id,
        "version": loaded.manifest.version,
        "name": loaded.manifest.name,
        "kind": loaded.manifest.kind,
    }


@router.delete("/{plugin_id}", summary="Uninstall plugin (admin)")
async def uninstall_plugin(
    plugin_id: str,
    server: OctopServer = Depends(get_server),
    user: Any = Depends(current_user),
) -> dict[str, str]:
    _require_admin(user)
    _plugin_manager(server).uninstall(plugin_id)
    if server.app_runtime is not None:
        await server.app_runtime.agent_registry.reload_all()
    return {"status": "ok", "id": plugin_id}


@router.get("/agents/{agent_id}/tools", summary="List plugin tools for an agent")
async def list_agent_plugin_tools(
    agent_id: str,
    server: OctopServer = Depends(get_server),
    user: Any = Depends(current_user),
) -> dict[str, Any]:
    assert server.app_runtime is not None
    row = server.app_runtime.agent_registry.get_row(agent_id)
    if row is None:
        raise OctopError(ErrorCode.AGENT_NOT_FOUND, f"agent {agent_id!r} not found")
    _assert_agent_owner(row, user)
    mgr = _plugin_manager(server)
    agent_cfg = server.app_runtime.agent_registry.get_config(agent_id)
    raw_plugins = agent_cfg.get("plugins")
    plugins_cfg: dict[str, Any] = raw_plugins if isinstance(raw_plugins, dict) else {}
    tools_out: list[dict[str, Any]] = []
    for plugin in mgr.list_installed():
        if plugin.get("error"):
            continue
        plugin_id = str(plugin["id"])
        for tool in plugin.get("tools") or []:
            name = str(tool["name"])
            tool_cfg: dict[str, Any] = {}
            plugin_entry = plugins_cfg.get(plugin_id)
            if isinstance(plugin_entry, dict):
                tools_map = plugin_entry.get("tools")
                if isinstance(tools_map, dict):
                    raw_tool = tools_map.get(name)
                    if isinstance(raw_tool, dict):
                        tool_cfg = raw_tool
            tools_out.append(
                {
                    "plugin_id": plugin_id,
                    "name": name,
                    "description": tool.get("description"),
                    "config_fields": tool.get("config_fields") or [],
                    "enabled": bool(tool_cfg.get("enabled")) if tool_cfg else False,
                    "config": tool_cfg.get("config")
                    if isinstance(tool_cfg.get("config"), dict)
                    else {},
                },
            )
    return {"tools": tools_out}


@router.patch("/agents/{agent_id}/tools", summary="Update agent plugin tool settings")
async def patch_agent_plugin_tools(
    agent_id: str,
    body: AgentPluginToolsPatch,
    server: OctopServer = Depends(get_server),
    user: Any = Depends(current_user),
) -> dict[str, str]:
    assert server.app_runtime is not None
    row = server.app_runtime.agent_registry.get_row(agent_id)
    if row is None:
        raise OctopError(ErrorCode.AGENT_NOT_FOUND, f"agent {agent_id!r} not found")
    _assert_agent_owner(row, user)
    cfg = server.app_runtime.agent_registry.get_config(agent_id)
    cfg["plugins"] = body.plugins
    await server.app_runtime.agent_registry.update_config_json(
        agent_id,
        json.dumps(cfg, ensure_ascii=False),
    )
    return {"status": "ok"}
