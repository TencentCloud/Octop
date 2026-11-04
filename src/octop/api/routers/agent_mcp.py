"""Authenticated Streamable HTTP MCP endpoint for Octop expert agents."""

from __future__ import annotations

import asyncio
import json
import secrets
from typing import Any

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse

from octop.api.deps import current_user, get_server
from octop.infra.agent_mcp.protocol import handle_agent_mcp_request
from octop.infra.agent_mcp.service import AgentMcpGatewayService
from octop.infra.errors import ErrorCode, OctopError

router = APIRouter()

MCP_SESSION_HEADER = "mcp-session-id"
MCP_PROTOCOL_HEADER = "mcp-protocol-version"


def _service(server: Any) -> AgentMcpGatewayService:
    if server.app_runtime is None:
        raise OctopError(ErrorCode.INTERNAL_ERROR, "server runtime is not ready")
    return AgentMcpGatewayService(
        agent_manager=server.app_runtime.agent_registry,
        gateway=server.app_runtime.gateway,
    )


@router.post("/mcp/agents", summary="Call Octop experts through MCP")
async def agent_mcp_post(
    request: Request,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> Response:
    """Handle MCP initialize, tools/list, tools/call, notifications, and ping."""
    try:
        body = await request.json()
    except (json.JSONDecodeError, ValueError) as exc:
        raise OctopError(ErrorCode.SLASH_BAD_ARGS, "invalid JSON body") from exc
    if not isinstance(body, dict):
        raise OctopError(ErrorCode.SLASH_BAD_ARGS, "expected JSON object")

    method = str(body.get("method") or "")
    if method == "notifications/initialized":
        return Response(status_code=202)

    response = await handle_agent_mcp_request(
        service=_service(server),
        user=user,
        body=body,
    )
    headers = {"content-type": "application/json"}
    session_id = request.headers.get(MCP_SESSION_HEADER)
    if method == "initialize":
        session_id = secrets.token_urlsafe(16)
    if session_id:
        headers[MCP_SESSION_HEADER] = session_id
    protocol = request.headers.get(MCP_PROTOCOL_HEADER)
    if protocol:
        headers[MCP_PROTOCOL_HEADER] = protocol
    return JSONResponse(content=response, headers=headers)


@router.get("/mcp/agents", summary="Open the Octop Agent MCP event stream")
async def agent_mcp_get(
    request: Request,
    _user: Any = Depends(current_user),
) -> Response:
    """Open the optional SSE channel used by Streamable HTTP MCP clients."""
    if not request.headers.get(MCP_SESSION_HEADER):
        return JSONResponse(status_code=405, content={"error": "missing mcp-session-id"})

    async def _keepalive() -> Any:
        yield "event: message\ndata: \n\n"
        while True:
            await asyncio.sleep(3600)

    return StreamingResponse(
        _keepalive(),
        media_type="text/event-stream",
        headers={"cache-control": "no-cache", "connection": "keep-alive"},
    )


@router.delete("/mcp/agents", status_code=204, summary="Close an Octop Agent MCP session")
async def agent_mcp_delete(_user: Any = Depends(current_user)) -> Response:
    """Acknowledge Streamable HTTP session cleanup."""
    return Response(status_code=204)
