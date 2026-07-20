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
    if inst is None or inst.kind != kind:
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
