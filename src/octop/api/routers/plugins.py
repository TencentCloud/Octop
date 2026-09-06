"""Plugin install and agent tool configuration."""

from __future__ import annotations

import mimetypes
import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from octop.api.common.agent import assert_agent_owner as _assert_agent_owner
from octop.api.deps import current_user, get_server, require_permission
from octop.infra.agents.plugin_tool_defaults import (
    agent_plugin_enabled,
    merge_plugins_enabled_settings,
    merge_plugins_tool_settings,
)
from octop.infra.agents.plugins.manager import PluginManager
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.server import OctopServer

router = APIRouter(prefix="/plugins", tags=["plugins"])

_UI_CONTENT_TYPES = {
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".map": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
}


class PluginInstallBody(BaseModel):
    url: str = Field(..., description="HTTP(S) URL to a plugin ZIP archive")


class AgentPluginToolBody(BaseModel):
    enabled: bool | None = None
    config: dict[str, Any] | None = None


class AgentPluginToolsPatch(BaseModel):
    """Patch per-agent plugin tool settings under ``config_json.plugins``."""

    plugins: dict[str, dict[str, Any]]


class PluginToolMeta(BaseModel):
    name: str
    description: str | None = None
    config_fields: list[dict[str, Any]] = Field(default_factory=list)


class AgentPluginItem(BaseModel):
    id: str
    version: str | None = None
    name: str | None = None
    kind: str | None = None
    description: str | None = None
    icon: str | None = None
    loaded: bool = False
    global_enabled: bool = True
    agent_enabled: bool = True
    enabled: bool = True
    tools: list[PluginToolMeta] = Field(default_factory=list)


class AgentPluginsResponse(BaseModel):
    plugins: list[AgentPluginItem]


class AgentPluginEnabledPatch(BaseModel):
    enabled: bool


class AgentPluginsPatch(BaseModel):
    plugins: dict[str, AgentPluginEnabledPatch]


def _plugin_manager(server: OctopServer) -> PluginManager:
    mgr = server.plugin_manager
    if mgr is None:
        raise OctopError(ErrorCode.INTERNAL_ERROR, "plugin manager not initialized")
    return mgr


@router.get("", summary="List installed plugins")
async def list_plugins(
    server: OctopServer = Depends(get_server),
    _user: Any = Depends(current_user),
) -> list[dict[str, Any]]:
    return _plugin_manager(server).list_installed()


@router.post("/reload", summary="Reload plugins from disk (admin)")
async def reload_plugins(
    server: OctopServer = Depends(get_server),
    _user: Any = Depends(require_permission("plugins")),
) -> dict[str, Any]:
    """Re-read ``~/.octop/plugins`` into the process registry and reload agents.

    Use after a CLI ``octop plugin install`` while ``octop run`` is already up —
    disk install does not update the running server until reload or restart.
    """
    mgr = _plugin_manager(server)
    loaded = mgr.load_installed(install_deps=True)
    if server.app_runtime is not None:
        await server.app_runtime.agent_registry.reload_all()
    return {
        "status": "ok",
        "loaded": [
            {
                "id": p.manifest.id,
                "version": p.manifest.version,
                "kind": p.manifest.kind,
            }
            for p in loaded
        ],
    }


@router.post("/install", summary="Install plugin from URL (admin)")
async def install_plugin(
    body: PluginInstallBody,
    server: OctopServer = Depends(get_server),
    _user: Any = Depends(require_permission("plugins")),
) -> dict[str, Any]:
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


@router.post("/upload", summary="Install plugin from an uploaded ZIP (admin)")
async def upload_plugin(
    file: UploadFile = File(...),
    force: bool = Form(default=False),
    server: OctopServer = Depends(get_server),
    _user: Any = Depends(require_permission("plugins")),
) -> dict[str, Any]:
    """Install a plugin from a locally-uploaded ZIP archive.

    ``force=True`` overwrites an already-installed plugin with the same id.
    """
    mgr = _plugin_manager(server)
    raw = await file.read()
    if not raw:
        raise OctopError(ErrorCode.PLUGIN_INVALID_ARCHIVE, "empty plugin archive")
    try:
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
            tmp.write(raw)
            tmp_path = Path(tmp.name)
        try:
            loaded = mgr.install_archive(tmp_path, force=force)
        finally:
            tmp_path.unlink(missing_ok=True)
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


class PluginPatchBody(BaseModel):
    enabled: bool = Field(..., description="Global enable switch for this plugin")


@router.patch("/{plugin_id}", summary="Update plugin settings (admin)")
async def patch_plugin(
    plugin_id: str,
    body: PluginPatchBody,
    server: OctopServer = Depends(get_server),
    _user: Any = Depends(require_permission("plugins")),
) -> dict[str, Any]:
    """Enable or disable an installed plugin server-wide.

    Disabled plugins are unloaded from the process registry so their tools /
    skills / hooks are unavailable to all agents until re-enabled.
    """
    mgr = _plugin_manager(server)
    item = mgr.set_enabled(plugin_id, body.enabled)
    if server.app_runtime is not None:
        await server.app_runtime.agent_registry.reload_all()
    return item


@router.delete("/{plugin_id}", summary="Uninstall plugin (admin)")
async def uninstall_plugin(
    plugin_id: str,
    server: OctopServer = Depends(get_server),
    _user: Any = Depends(require_permission("plugins")),
) -> dict[str, str]:
    _plugin_manager(server).uninstall(plugin_id)
    if server.app_runtime is not None:
        await server.app_runtime.agent_registry.reload_all()
    return {"status": "ok", "id": plugin_id}


@router.get(
    "/{plugin_id}/ui/{file_path:path}",
    summary="Serve an installed plugin UI asset",
    response_model=None,
)
async def get_plugin_ui_asset(
    plugin_id: str,
    file_path: str,
    server: OctopServer = Depends(get_server),
    _user: Any = Depends(current_user),
) -> Response:
    """Read-only static files from ``~/.octop/plugins/<id>/`` (typically ``ui/dist/``).

    Authenticated users only. Paths are traversal-checked in ``PluginManager``.
    """
    target = _plugin_manager(server).resolve_ui_file(plugin_id, file_path)
    suffix = target.suffix.lower()
    media_type = _UI_CONTENT_TYPES.get(suffix) or mimetypes.guess_type(target.name)[0]
    return FileResponse(
        path=target,
        media_type=media_type or "application/octet-stream",
        filename=target.name,
        content_disposition_type="inline",
    )


def _agent_row_and_config(
    server: OctopServer,
    agent_id: str,
    user: Any,
) -> tuple[Any, dict[str, Any]]:
    runtime = server.app_runtime
    assert runtime is not None
    registry = runtime.agent_registry
    row = registry.get_row(agent_id)
    if row is None:
        raise OctopError(ErrorCode.AGENT_NOT_FOUND, f"agent {agent_id!r} not found")
    _assert_agent_owner(row, user)
    return row, registry.get_config(agent_id)


def _agent_plugins_response(
    server: OctopServer,
    agent_cfg: dict[str, Any],
) -> AgentPluginsResponse:
    raw_plugins = agent_cfg.get("plugins")
    plugins_cfg = raw_plugins if isinstance(raw_plugins, dict) else {}
    items: list[AgentPluginItem] = []
    for plugin in _plugin_manager(server).list_installed():
        if plugin.get("error"):
            continue
        plugin_id = str(plugin["id"])
        global_enabled = plugin.get("enabled", True) is not False
        per_agent_enabled = agent_plugin_enabled(plugins_cfg, plugin_id)
        items.append(
            AgentPluginItem(
                id=plugin_id,
                version=plugin.get("version"),
                name=plugin.get("name"),
                kind=plugin.get("kind"),
                description=plugin.get("description"),
                icon=plugin.get("icon"),
                loaded=bool(plugin.get("loaded")),
                global_enabled=global_enabled,
                agent_enabled=per_agent_enabled,
                enabled=global_enabled and per_agent_enabled,
                tools=[PluginToolMeta.model_validate(tool) for tool in plugin.get("tools") or []],
            )
        )
    return AgentPluginsResponse(plugins=items)


@router.get(
    "/agents/{agent_id}",
    summary="List installed plugins for an agent",
    response_model=AgentPluginsResponse,
)
async def list_agent_plugins(
    agent_id: str,
    server: OctopServer = Depends(get_server),
    user: Any = Depends(current_user),
) -> AgentPluginsResponse:
    """List global and per-agent plugin state. Missing agent switches default on."""
    _, cfg = _agent_row_and_config(server, agent_id, user)
    return _agent_plugins_response(server, cfg)


@router.patch(
    "/agents/{agent_id}",
    summary="Update agent plugin enablement",
    response_model=AgentPluginsResponse,
)
async def patch_agent_plugins(
    agent_id: str,
    body: AgentPluginsPatch,
    server: OctopServer = Depends(get_server),
    user: Any = Depends(current_user),
) -> AgentPluginsResponse:
    """Merge plugin switches, preserve tool settings, and reload only this agent."""
    _, cfg = _agent_row_and_config(server, agent_id, user)
    installed = {
        str(item["id"])
        for item in _plugin_manager(server).list_installed()
        if not item.get("error")
    }
    unknown = sorted(set(body.plugins) - installed)
    if unknown:
        raise OctopError(ErrorCode.NOT_FOUND, f"plugin {unknown[0]!r} not found")

    runtime = server.app_runtime
    assert runtime is not None
    registry = runtime.agent_registry
    merged = merge_plugins_enabled_settings(
        cfg.get("plugins"),
        {plugin_id: patch.enabled for plugin_id, patch in body.plugins.items()},
    )
    await registry.persist_plugin_tools_config(agent_id, merged)
    await registry.reload(agent_id)
    return _agent_plugins_response(server, registry.get_config(agent_id))


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
            # Default on when the agent has no explicit override (matches
            # harness_agent.plugins.tools._tool_enabled).
            if tool_cfg and "enabled" in tool_cfg:
                tool_enabled = bool(tool_cfg.get("enabled"))
            else:
                tool_enabled = True
            tools_out.append(
                {
                    "plugin_id": plugin_id,
                    "name": name,
                    "description": tool.get("description"),
                    "config_fields": tool.get("config_fields") or [],
                    "enabled": tool_enabled,
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
    """Persist per-agent plugin tool enable flags and hot-sync the denylist.

    Same storage as Experts → Tools (``config.plugins``). Prefer this over a
    full agent reload so disable takes effect on the next model turn.
    """
    assert server.app_runtime is not None
    row = server.app_runtime.agent_registry.get_row(agent_id)
    if row is None:
        raise OctopError(ErrorCode.AGENT_NOT_FOUND, f"agent {agent_id!r} not found")
    _assert_agent_owner(row, user)
    registry = server.app_runtime.agent_registry
    cfg = registry.get_config(agent_id)
    merged = merge_plugins_tool_settings(cfg.get("plugins"), body.plugins)
    await registry.persist_plugin_tools_config(agent_id, merged)
    return {"status": "ok"}
