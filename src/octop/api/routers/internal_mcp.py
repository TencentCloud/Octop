"""Internal HTTP MCP endpoints for Octop-hosted connector gateways."""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
from typing import Any

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from mcp.shared.version import SUPPORTED_PROTOCOL_VERSIONS

from octop.api.deps import get_server
from octop.infra.connectors.gateway.protocol import handle_mcp_request
from octop.infra.connectors.service import ConnectorService
from octop.infra.errors import ErrorCode, OctopError

logger = logging.getLogger(__name__)

router = APIRouter()

MCP_SESSION_HEADER = "mcp-session-id"
MCP_PROTOCOL_HEADER = "mcp-protocol-version"


def _service(server: Any) -> ConnectorService:
    return ConnectorService(
        repo=server.services.repos.connector_repo,
        secret_repo=server.services.secret_repo,
        settings_repo=server.services.settings_repo,
        config=server.services.config,
    )


def _negotiate_initialize_result(body: dict[str, Any], resp: dict[str, Any]) -> dict[str, Any]:
    if body.get("method") != "initialize":
        return resp
    result = resp.get("result")
    if not isinstance(result, dict):
        return resp
    params = body.get("params") or {}
    requested = str(params.get("protocolVersion") or "").strip()
    if requested in SUPPORTED_PROTOCOL_VERSIONS:
        result["protocolVersion"] = requested
    return resp


@router.post("/internal/mcp/{kind}/{instance_id}")
async def internal_mcp_post(
    kind: str,
    instance_id: str,
    request: Request,
    token: str = Query(...),
    server: Any = Depends(get_server),
) -> Response:
    inst = server.services.repos.connector_repo.get(instance_id)
    if inst is None or inst.kind != kind or inst.status != "active":
        raise OctopError(ErrorCode.CONNECTOR_NOT_FOUND, "instance not found")

    svc = _service(server)
    creds = svc.verify_internal_token(instance_id, token)
    if creds is None:
        raise OctopError(ErrorCode.AUTH_FAILED, "invalid internal token")

    try:
        body = await request.json()
    except json.JSONDecodeError as exc:
        raise OctopError(ErrorCode.CONNECTOR_INVALID_CREDENTIALS, "invalid JSON body") from exc
    if not isinstance(body, dict):
        raise OctopError(ErrorCode.CONNECTOR_INVALID_CREDENTIALS, "expected JSON object")

    method = str(body.get("method") or "")
    if method == "notifications/initialized":
        return Response(status_code=202)

    session_id = request.headers.get(MCP_SESSION_HEADER)
    if method == "initialize":
        session_id = secrets.token_urlsafe(16)

    if kind == "qcc":
        resp = await svc.handle_qcc_request(instance_id, body)
    else:
        resp = await asyncio.to_thread(handle_mcp_request, kind=kind, creds=creds, body=body)
    if not resp:
        return Response(status_code=202)

    resp = _negotiate_initialize_result(body, resp)
    headers = {"content-type": "application/json"}
    if session_id:
        headers[MCP_SESSION_HEADER] = session_id
    protocol = request.headers.get(MCP_PROTOCOL_HEADER)
    if protocol:
        headers[MCP_PROTOCOL_HEADER] = protocol
    return JSONResponse(content=resp, headers=headers)


@router.get("/internal/mcp/{kind}/{instance_id}")
async def internal_mcp_get(
    kind: str,
    instance_id: str,
    request: Request,
    token: str = Query(...),
    server: Any = Depends(get_server),
) -> Response:
    """Streamable HTTP clients open a long-lived GET SSE channel after initialize."""
    inst = server.services.repos.connector_repo.get(instance_id)
    if inst is None or inst.kind != kind:
        raise OctopError(ErrorCode.CONNECTOR_NOT_FOUND, "instance not found")

    svc = _service(server)
    creds = svc.verify_internal_token(instance_id, token)
    if creds is None:
        raise OctopError(ErrorCode.AUTH_FAILED, "invalid internal token")

    if not request.headers.get(MCP_SESSION_HEADER):
        return JSONResponse(
            status_code=405,
            content={"error": "missing mcp-session-id"},
        )

    async def _sse_keepalive() -> Any:
        # Priming event so streamable-http clients attach successfully.
        yield "event: message\ndata: \n\n"
        while True:
            await asyncio.sleep(3600)

    return StreamingResponse(
        _sse_keepalive(),
        media_type="text/event-stream",
        headers={"cache-control": "no-cache", "connection": "keep-alive"},
    )


@router.delete("/internal/mcp/{kind}/{instance_id}")
async def internal_mcp_delete(
    kind: str,
    instance_id: str,
    token: str = Query(...),
    server: Any = Depends(get_server),
) -> Response:
    """Streamable HTTP clients may DELETE to end a session."""
    inst = server.services.repos.connector_repo.get(instance_id)
    if inst is None or inst.kind != kind:
        raise OctopError(ErrorCode.CONNECTOR_NOT_FOUND, "instance not found")
    svc = _service(server)
    if svc.verify_internal_token(instance_id, token) is None:
        raise OctopError(ErrorCode.AUTH_FAILED, "invalid internal token")
    return Response(status_code=204)


def _mcp_json(
    request: Request,
    body: dict[str, Any],
    resp: dict[str, Any],
    *,
    session_id: str | None,
) -> Response:
    if not resp:
        return Response(status_code=202)
    resp = _negotiate_initialize_result(body, resp)
    headers = {"content-type": "application/json"}
    if session_id:
        headers[MCP_SESSION_HEADER] = session_id
    protocol = request.headers.get(MCP_PROTOCOL_HEADER)
    if protocol:
        headers[MCP_PROTOCOL_HEADER] = protocol
    return JSONResponse(content=resp, headers=headers)


@router.post("/internal/mcp/knowledge")
async def knowledge_mcp_post(
    request: Request,
    token: str = Query(...),
    server: Any = Depends(get_server),
) -> Response:
    """Search the knowledge bases selected for one managed-agent turn."""
    from octop.infra.agents.acp.turn import knowledge_scope
    from octop.infra.knowledge.mcp_gateway import handle_knowledge_mcp
    from octop.infra.knowledge.tools import KnowledgeToolServices

    scope = knowledge_scope(token)
    if scope is None:
        raise OctopError(ErrorCode.AUTH_FAILED, "invalid internal token")
    try:
        body = await request.json()
    except json.JSONDecodeError as exc:
        raise OctopError(ErrorCode.CONNECTOR_INVALID_CREDENTIALS, "invalid JSON body") from exc
    if not isinstance(body, dict):
        raise OctopError(ErrorCode.CONNECTOR_INVALID_CREDENTIALS, "expected JSON object")

    method = str(body.get("method") or "")
    if method == "notifications/initialized":
        return Response(status_code=202)
    session_id = request.headers.get(MCP_SESSION_HEADER)
    if method == "initialize":
        session_id = secrets.token_urlsafe(16)
    resp = await handle_knowledge_mcp(
        body,
        user_id=scope.user_id,
        is_admin=scope.is_admin,
        knowledge_base_ids=list(scope.knowledge_base_ids),
        locale=scope.locale,
        catalog=scope.catalog_rows(),
        services=KnowledgeToolServices(server.app_runtime.agent_registry),
    )
    return _mcp_json(request, body, resp, session_id=session_id)


@router.get("/internal/mcp/knowledge")
async def knowledge_mcp_get(
    request: Request,
    token: str = Query(...),
) -> Response:
    """Keep a streamable-HTTP session open after initialize."""
    from octop.infra.agents.acp.turn import knowledge_scope

    if knowledge_scope(token) is None:
        raise OctopError(ErrorCode.AUTH_FAILED, "invalid internal token")
    if not request.headers.get(MCP_SESSION_HEADER):
        return JSONResponse(status_code=405, content={"error": "missing mcp-session-id"})

    async def _sse_keepalive() -> Any:
        yield "event: message\ndata: \n\n"
        while True:
            await asyncio.sleep(3600)

    return StreamingResponse(
        _sse_keepalive(),
        media_type="text/event-stream",
        headers={"cache-control": "no-cache", "connection": "keep-alive"},
    )


@router.delete("/internal/mcp/knowledge")
async def knowledge_mcp_delete(token: str = Query(...)) -> Response:
    from octop.infra.agents.acp.turn import knowledge_scope

    if knowledge_scope(token) is None:
        raise OctopError(ErrorCode.AUTH_FAILED, "invalid internal token")
    return Response(status_code=204)


@router.post("/internal/mcp/agents")
async def agents_mcp_post(
    request: Request,
    token: str = Query(...),
    server: Any = Depends(get_server),
) -> Response:
    """Let a managed runner call another expert with ``ask_agent``."""
    from octop.infra.agents.acp.agents_mcp import handle_agents_mcp
    from octop.infra.agents.acp.delegation import agent_scope

    scope = agent_scope(token)
    if scope is None:
        raise OctopError(ErrorCode.AUTH_FAILED, "invalid internal token")
    registry = server.app_runtime.agent_registry
    team = getattr(getattr(registry, "_harness_manager", None), "team", None)
    if team is None:
        raise OctopError(ErrorCode.NOT_FOUND, "expert calls are not available")
    try:
        body = await request.json()
    except json.JSONDecodeError as exc:
        raise OctopError(ErrorCode.CONNECTOR_INVALID_CREDENTIALS, "invalid JSON body") from exc
    if not isinstance(body, dict):
        raise OctopError(ErrorCode.CONNECTOR_INVALID_CREDENTIALS, "expected JSON object")

    method = str(body.get("method") or "")
    if method == "notifications/initialized":
        return Response(status_code=202)
    session_id = request.headers.get(MCP_SESSION_HEADER)
    if method == "initialize":
        session_id = secrets.token_urlsafe(16)
    resp = await handle_agents_mcp(body, scope=scope, team=team)
    return _mcp_json(request, body, resp, session_id=session_id)


@router.get("/internal/mcp/agents")
async def agents_mcp_get(request: Request, token: str = Query(...)) -> Response:
    from octop.infra.agents.acp.delegation import agent_scope

    if agent_scope(token) is None:
        raise OctopError(ErrorCode.AUTH_FAILED, "invalid internal token")
    if not request.headers.get(MCP_SESSION_HEADER):
        return JSONResponse(status_code=405, content={"error": "missing mcp-session-id"})

    async def _sse_keepalive() -> Any:
        yield "event: message\ndata: \n\n"
        while True:
            await asyncio.sleep(3600)

    return StreamingResponse(
        _sse_keepalive(),
        media_type="text/event-stream",
        headers={"cache-control": "no-cache", "connection": "keep-alive"},
    )


@router.delete("/internal/mcp/agents")
async def agents_mcp_delete(token: str = Query(...)) -> Response:
    from octop.infra.agents.acp.delegation import agent_scope

    if agent_scope(token) is None:
        raise OctopError(ErrorCode.AUTH_FAILED, "invalid internal token")
    return Response(status_code=204)


def _mcp_keepalive(request: Request, *, authorized: bool) -> Response:
    if not authorized:
        raise OctopError(ErrorCode.AUTH_FAILED, "invalid internal token")
    if not request.headers.get(MCP_SESSION_HEADER):
        return JSONResponse(status_code=405, content={"error": "missing mcp-session-id"})

    async def _sse_keepalive() -> Any:
        yield "event: message\ndata: \n\n"
        while True:
            await asyncio.sleep(3600)

    return StreamingResponse(
        _sse_keepalive(),
        media_type="text/event-stream",
        headers={"cache-control": "no-cache", "connection": "keep-alive"},
    )


async def _mcp_body(request: Request) -> dict[str, Any]:
    try:
        body = await request.json()
    except json.JSONDecodeError as exc:
        raise OctopError(ErrorCode.CONNECTOR_INVALID_CREDENTIALS, "invalid JSON body") from exc
    if not isinstance(body, dict):
        raise OctopError(ErrorCode.CONNECTOR_INVALID_CREDENTIALS, "expected JSON object")
    return body


def _mcp_session(request: Request, body: dict[str, Any]) -> str | None:
    session_id = request.headers.get(MCP_SESSION_HEADER)
    if str(body.get("method") or "") == "initialize":
        return secrets.token_urlsafe(16)
    return session_id


@router.post("/internal/mcp/cron")
async def cron_mcp_post(
    request: Request,
    token: str = Query(...),
    server: Any = Depends(get_server),
) -> Response:
    """Let a managed runner manage this expert's scheduled jobs."""
    from octop.infra.agents.acp.cron_mcp import cron_scope, handle_cron_mcp

    scope = cron_scope(token)
    if scope is None:
        raise OctopError(ErrorCode.AUTH_FAILED, "invalid internal token")
    body = await _mcp_body(request)
    if str(body.get("method") or "") == "notifications/initialized":
        return Response(status_code=202)
    registry = server.app_runtime.agent_registry
    resp = await handle_cron_mcp(body, scope=scope, cron_manager=registry._cron_manager)
    return _mcp_json(request, body, resp, session_id=_mcp_session(request, body))


@router.get("/internal/mcp/cron")
async def cron_mcp_get(request: Request, token: str = Query(...)) -> Response:
    from octop.infra.agents.acp.cron_mcp import cron_scope

    return _mcp_keepalive(request, authorized=cron_scope(token) is not None)


@router.delete("/internal/mcp/cron")
async def cron_mcp_delete(token: str = Query(...)) -> Response:
    from octop.infra.agents.acp.cron_mcp import cron_scope

    if cron_scope(token) is None:
        raise OctopError(ErrorCode.AUTH_FAILED, "invalid internal token")
    return Response(status_code=204)


def _memory_service(registry: Any, agent_id: str) -> Any:
    try:
        agent = registry.get_agent(agent_id)
    except Exception:
        return None
    runtime = getattr(agent, "_memory_runtime", None)
    return getattr(runtime, "service", None)


@router.post("/internal/mcp/memory")
async def memory_mcp_post(
    request: Request,
    token: str = Query(...),
    server: Any = Depends(get_server),
) -> Response:
    """Let a managed runner search and save memory when this expert has it on."""
    from octop.infra.agents.acp.memory_mcp import handle_memory_mcp, memory_scope

    scope = memory_scope(token)
    if scope is None:
        raise OctopError(ErrorCode.AUTH_FAILED, "invalid internal token")
    body = await _mcp_body(request)
    if str(body.get("method") or "") == "notifications/initialized":
        return Response(status_code=202)
    registry = server.app_runtime.agent_registry
    resp = await handle_memory_mcp(
        body,
        service=_memory_service(registry, scope.agent_id),
        tools_allowed=scope.tools,
    )
    return _mcp_json(request, body, resp, session_id=_mcp_session(request, body))


@router.get("/internal/mcp/memory")
async def memory_mcp_get(request: Request, token: str = Query(...)) -> Response:
    from octop.infra.agents.acp.memory_mcp import memory_scope

    return _mcp_keepalive(request, authorized=memory_scope(token) is not None)


@router.delete("/internal/mcp/memory")
async def memory_mcp_delete(token: str = Query(...)) -> Response:
    from octop.infra.agents.acp.memory_mcp import memory_scope

    if memory_scope(token) is None:
        raise OctopError(ErrorCode.AUTH_FAILED, "invalid internal token")
    return Response(status_code=204)


@router.post("/internal/mcp/plugins")
async def plugins_mcp_post(
    request: Request,
    token: str = Query(...),
    server: Any = Depends(get_server),
) -> Response:
    """Let a managed runner call the plugin tools enabled for this expert."""
    from octop.infra.agents.acp.plugins_mcp import (
        handle_plugins_mcp,
        plugin_scope,
        plugin_tool_configs,
        plugin_tools,
    )

    scope = plugin_scope(token)
    if scope is None:
        raise OctopError(ErrorCode.AUTH_FAILED, "invalid internal token")
    body = await _mcp_body(request)
    if str(body.get("method") or "") == "notifications/initialized":
        return Response(status_code=202)
    registry = server.app_runtime.agent_registry
    config = registry.get_config(scope.agent_id)
    resp = await handle_plugins_mcp(
        body,
        tools=plugin_tools(registry, config),
        tool_configs=plugin_tool_configs(config),
    )
    return _mcp_json(request, body, resp, session_id=_mcp_session(request, body))


@router.get("/internal/mcp/plugins")
async def plugins_mcp_get(request: Request, token: str = Query(...)) -> Response:
    from octop.infra.agents.acp.plugins_mcp import plugin_scope

    return _mcp_keepalive(request, authorized=plugin_scope(token) is not None)


@router.delete("/internal/mcp/plugins")
async def plugins_mcp_delete(token: str = Query(...)) -> Response:
    from octop.infra.agents.acp.plugins_mcp import plugin_scope

    if plugin_scope(token) is None:
        raise OctopError(ErrorCode.AUTH_FAILED, "invalid internal token")
    return Response(status_code=204)


@router.post("/internal/mcp/files")
async def files_mcp_post(
    request: Request,
    token: str = Query(...),
    server: Any = Depends(get_server),
) -> Response:
    """Let a managed runner deliver a workspace file with ``send_file_to_user``."""
    from octop.infra.agents.acp.files_mcp import file_scope, handle_files_mcp

    scope = file_scope(token)
    if scope is None:
        raise OctopError(ErrorCode.AUTH_FAILED, "invalid internal token")
    try:
        body = await request.json()
    except json.JSONDecodeError as exc:
        raise OctopError(ErrorCode.CONNECTOR_INVALID_CREDENTIALS, "invalid JSON body") from exc
    if not isinstance(body, dict):
        raise OctopError(ErrorCode.CONNECTOR_INVALID_CREDENTIALS, "expected JSON object")

    method = str(body.get("method") or "")
    if method == "notifications/initialized":
        return Response(status_code=202)
    session_id = request.headers.get(MCP_SESSION_HEADER)
    if method == "initialize":
        session_id = secrets.token_urlsafe(16)
    registry = server.app_runtime.agent_registry
    workspace = await asyncio.to_thread(registry.workspace_for_agent, scope.agent_id)
    if workspace is None:
        raise OctopError(ErrorCode.NOT_FOUND, "expert workspace is not available")
    resp = await handle_files_mcp(body, workspace=workspace)
    return _mcp_json(request, body, resp, session_id=session_id)


@router.get("/internal/mcp/files")
async def files_mcp_get(request: Request, token: str = Query(...)) -> Response:
    from octop.infra.agents.acp.files_mcp import file_scope

    if file_scope(token) is None:
        raise OctopError(ErrorCode.AUTH_FAILED, "invalid internal token")
    if not request.headers.get(MCP_SESSION_HEADER):
        return JSONResponse(status_code=405, content={"error": "missing mcp-session-id"})

    async def _sse_keepalive() -> Any:
        yield "event: message\ndata: \n\n"
        while True:
            await asyncio.sleep(3600)

    return StreamingResponse(
        _sse_keepalive(),
        media_type="text/event-stream",
        headers={"cache-control": "no-cache", "connection": "keep-alive"},
    )


@router.delete("/internal/mcp/files")
async def files_mcp_delete(token: str = Query(...)) -> Response:
    from octop.infra.agents.acp.files_mcp import file_scope

    if file_scope(token) is None:
        raise OctopError(ErrorCode.AUTH_FAILED, "invalid internal token")
    return Response(status_code=204)


@router.post("/internal/mcp/team-workspace")
async def team_workspace_mcp_post(
    request: Request,
    token: str = Query(...),
    server: Any = Depends(get_server),
) -> Response:
    """Host-workspace file tools for one managed team-member turn."""
    from octop.infra.agents.acp.team_workspace_mcp import (
        handle_team_workspace_mcp,
        team_workspace_scope,
    )

    scope = team_workspace_scope(token)
    if scope is None:
        raise OctopError(ErrorCode.AUTH_FAILED, "invalid internal token")
    try:
        body = await request.json()
    except json.JSONDecodeError as exc:
        raise OctopError(ErrorCode.CONNECTOR_INVALID_CREDENTIALS, "invalid JSON body") from exc
    if not isinstance(body, dict):
        raise OctopError(ErrorCode.CONNECTOR_INVALID_CREDENTIALS, "expected JSON object")

    method = str(body.get("method") or "")
    if method == "notifications/initialized":
        return Response(status_code=202)
    session_id = request.headers.get(MCP_SESSION_HEADER)
    if method == "initialize":
        session_id = secrets.token_urlsafe(16)
    if scope.bridge_target_id:
        from octop.infra.bridge.local_workspace import lookup_peer_target

        target = lookup_peer_target(scope.bridge_target_id)
        if target is None:
            raise OctopError(ErrorCode.NOT_FOUND, "local workspace is not available")
        resp = await handle_team_workspace_mcp(
            body,
            scope=scope,
            workspace=target,
            backend=target,
        )
    else:
        registry = server.app_runtime.agent_registry
        try:
            agent = await asyncio.to_thread(registry.get_agent, scope.host_agent_id)
        except OctopError as exc:
            raise OctopError(ErrorCode.NOT_FOUND, "expert workspace is not available") from exc
        resp = await handle_team_workspace_mcp(
            body,
            scope=scope,
            workspace=agent.workspace,
            backend=agent.backend,
        )
    return _mcp_json(request, body, resp, session_id=session_id)


@router.get("/internal/mcp/team-workspace")
async def team_workspace_mcp_get(request: Request, token: str = Query(...)) -> Response:
    from octop.infra.agents.acp.team_workspace_mcp import team_workspace_scope

    if team_workspace_scope(token) is None:
        raise OctopError(ErrorCode.AUTH_FAILED, "invalid internal token")
    if not request.headers.get(MCP_SESSION_HEADER):
        return JSONResponse(status_code=405, content={"error": "missing mcp-session-id"})

    async def _sse_keepalive() -> Any:
        yield "event: message\ndata: \n\n"
        while True:
            await asyncio.sleep(3600)

    return StreamingResponse(
        _sse_keepalive(),
        media_type="text/event-stream",
        headers={"cache-control": "no-cache", "connection": "keep-alive"},
    )


@router.delete("/internal/mcp/team-workspace")
async def team_workspace_mcp_delete(token: str = Query(...)) -> Response:
    from octop.infra.agents.acp.team_workspace_mcp import team_workspace_scope

    if team_workspace_scope(token) is None:
        raise OctopError(ErrorCode.AUTH_FAILED, "invalid internal token")
    return Response(status_code=204)
