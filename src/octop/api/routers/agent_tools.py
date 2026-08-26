"""Per-agent tool settings — built-in denylist + plugin tool enable flags."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from octop.api.common.agent import assert_agent_owner as _assert_agent_owner
from octop.api.deps import current_user, get_server
from octop.i18n.domains.tools import tool_display_name
from octop.infra.agents.plugin_tool_defaults import merge_plugins_tool_settings
from octop.infra.agents.tool_catalog import (
    BUILTIN_TOOL_CATALOG,
    CRITICAL_TOOLS,
    builtin_tool_available,
    normalize_tools_disabled,
)
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.server import OctopServer
from octop.infra.utils.locale import resolve_request_locale

router = APIRouter(prefix="/agents", tags=["agents"])


class ToolSettingsItem(BaseModel):
    name: str
    source: Literal["builtin", "plugin"]
    category: str
    label: str
    description: str | None = None
    enabled: bool
    disableable: bool
    available: bool = True
    plugin_id: str | None = None


class ToolSettingsResponse(BaseModel):
    tools: list[ToolSettingsItem]


class ToolSettingsPutBody(BaseModel):
    disabled_builtin: list[str] = Field(
        default_factory=list,
        description="Built-in tool names to hide from the model (denylist).",
    )
    plugins: dict[str, dict[str, Any]] | None = Field(
        default=None,
        description=(
            "Optional plugin tools map (``enabled`` flags). Merged into "
            "``config.plugins`` without reloading the agent."
        ),
    )


class ToolSettingPatchBody(BaseModel):
    enabled: bool
    source: Literal["builtin", "plugin"] = "builtin"
    plugin_id: str | None = None


def _plugin_manager(server: OctopServer) -> Any:
    mgr = server.plugin_manager
    if mgr is None:
        raise OctopError(ErrorCode.INTERNAL_ERROR, "plugin manager not initialized")
    return mgr


def _plugin_tool_label(name: str, locale: str) -> str:
    """Use i18n label when present; otherwise keep the raw tool name."""
    labeled = tool_display_name(name, locale)
    return labeled if labeled != name else name


def _list_plugin_tool_items(
    server: OctopServer,
    agent_cfg: dict[str, Any],
    *,
    locale: str,
) -> list[ToolSettingsItem]:
    mgr = _plugin_manager(server)
    raw_plugins = agent_cfg.get("plugins")
    plugins_cfg: dict[str, Any] = raw_plugins if isinstance(raw_plugins, dict) else {}
    items: list[ToolSettingsItem] = []
    for plugin in mgr.list_installed():
        if plugin.get("error"):
            continue
        plugin_id = str(plugin["id"])
        globally_on = plugin.get("enabled", True) is not False
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
            desc = tool.get("description")
            enabled = bool(tool_cfg.get("enabled")) if tool_cfg and "enabled" in tool_cfg else True
            items.append(
                ToolSettingsItem(
                    name=name,
                    source="plugin",
                    category="plugin",
                    label=_plugin_tool_label(name, locale),
                    description=(
                        str(desc).strip() if isinstance(desc, str) and desc.strip() else None
                    ),
                    enabled=enabled,
                    disableable=True,
                    available=globally_on,
                    plugin_id=plugin_id,
                )
            )
    return items


@router.get(
    "/{agent_id}/tool-settings",
    summary="List built-in and plugin tools with enable state",
    response_model=ToolSettingsResponse,
)
async def get_tool_settings(
    agent_id: str,
    request: Request,
    server: OctopServer = Depends(get_server),
    user: Any = Depends(current_user),
) -> ToolSettingsResponse:
    assert server.app_runtime is not None
    row = server.app_runtime.agent_registry.get_row(agent_id)
    if row is None:
        raise OctopError(ErrorCode.AGENT_NOT_FOUND, f"agent {agent_id!r} not found")
    _assert_agent_owner(row, user)

    locale = resolve_request_locale(request)
    agent_cfg = server.app_runtime.agent_registry.get_config(agent_id)
    disabled = set(normalize_tools_disabled(agent_cfg.get("tools_disabled")))
    mobile_enabled = bool(server.config is not None and server.config.capabilities.mobile.enabled)

    tools: list[ToolSettingsItem] = []
    for entry in BUILTIN_TOOL_CATALOG:
        disableable = entry.name not in CRITICAL_TOOLS
        tools.append(
            ToolSettingsItem(
                name=entry.name,
                source="builtin",
                category=entry.category,
                label=tool_display_name(entry.name, locale),
                description=None,
                enabled=entry.name not in disabled if disableable else True,
                disableable=disableable,
                available=builtin_tool_available(
                    entry.name,
                    agent_cfg=agent_cfg,
                    mobile_enabled=mobile_enabled,
                ),
                plugin_id=None,
            )
        )
    tools.extend(_list_plugin_tool_items(server, agent_cfg, locale=locale))
    return ToolSettingsResponse(tools=tools)


@router.put(
    "/{agent_id}/tool-settings",
    summary="Update built-in tool denylist and optional plugin tool flags",
    response_model=ToolSettingsResponse,
)
async def put_tool_settings(
    agent_id: str,
    body: ToolSettingsPutBody,
    request: Request,
    server: OctopServer = Depends(get_server),
    user: Any = Depends(current_user),
) -> ToolSettingsResponse:
    assert server.app_runtime is not None
    row = server.app_runtime.agent_registry.get_row(agent_id)
    if row is None:
        raise OctopError(ErrorCode.AGENT_NOT_FOUND, f"agent {agent_id!r} not found")
    _assert_agent_owner(row, user)

    registry = server.app_runtime.agent_registry
    await registry.persist_tools_disabled(agent_id, set(body.disabled_builtin))

    if body.plugins is not None:
        cfg = registry.get_config(agent_id)
        merged = merge_plugins_tool_settings(cfg.get("plugins"), body.plugins)
        await registry.persist_plugin_tools_config(agent_id, merged)

    return await get_tool_settings(agent_id, request, server, user)


@router.patch(
    "/{agent_id}/tool-settings/{tool_name}",
    summary="Enable or disable a single built-in or plugin tool",
    response_model=ToolSettingsResponse,
)
async def patch_tool_setting(
    agent_id: str,
    tool_name: str,
    body: ToolSettingPatchBody,
    request: Request,
    server: OctopServer = Depends(get_server),
    user: Any = Depends(current_user),
) -> ToolSettingsResponse:
    assert server.app_runtime is not None
    row = server.app_runtime.agent_registry.get_row(agent_id)
    if row is None:
        raise OctopError(ErrorCode.AGENT_NOT_FOUND, f"agent {agent_id!r} not found")
    _assert_agent_owner(row, user)

    name = tool_name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="tool name is required")

    registry = server.app_runtime.agent_registry
    if body.source == "builtin":
        if name in CRITICAL_TOOLS:
            raise HTTPException(
                status_code=400,
                detail=f"tool {name!r} cannot be disabled",
            )
        cfg = registry.get_config(agent_id)
        disabled = set(normalize_tools_disabled(cfg.get("tools_disabled")))
        if body.enabled:
            disabled.discard(name)
        else:
            disabled.add(name)
        await registry.persist_tools_disabled(agent_id, disabled)
    else:
        plugin_id = (body.plugin_id or "").strip()
        if not plugin_id:
            raise HTTPException(
                status_code=400,
                detail="plugin_id is required for plugin tools",
            )
        cfg = registry.get_config(agent_id)
        merged = merge_plugins_tool_settings(
            cfg.get("plugins"),
            {plugin_id: {"tools": {name: {"enabled": body.enabled}}}},
        )
        await registry.persist_plugin_tools_config(agent_id, merged)

    return await get_tool_settings(agent_id, request, server, user)
