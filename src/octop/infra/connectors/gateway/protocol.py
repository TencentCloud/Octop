"""MCP JSON-RPC protocol handlers for internal gateway endpoints."""

from __future__ import annotations

import logging
from typing import Any

from octop.infra.connectors.gateway.registry import call_gateway_tool, mcp_tools_for_kind

logger = logging.getLogger(__name__)

MCP_PROTOCOL_VERSION = "2024-11-05"


def handle_mcp_request(
    *,
    kind: str,
    creds: dict[str, Any],
    body: dict[str, Any],
) -> dict[str, Any]:
    method = body.get("method")
    req_id = body.get("id")
    params = body.get("params") or {}

    if method == "initialize":
        return _ok(
            req_id,
            {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": f"octop-{kind}", "version": "0.1.0"},
            },
        )

    if isinstance(method, str) and method.startswith("notifications/"):
        return {}

    if method == "tools/list":
        return _ok(req_id, {"tools": mcp_tools_for_kind(kind)})

    if method == "tools/call":
        name = (params.get("name") or "") if isinstance(params, dict) else ""
        arguments = (params.get("arguments") or {}) if isinstance(params, dict) else {}
        if isinstance(arguments, dict):
            nested = arguments.get("kwargs")
            if (
                nested is not None
                and set(arguments.keys()) == {"kwargs"}
                and isinstance(nested, dict)
            ):
                arguments = nested
        try:
            text = call_gateway_tool(kind, creds, str(name), arguments)
            return _ok(
                req_id,
                {"content": [{"type": "text", "text": text}], "isError": False},
            )
        except Exception as exc:
            logger.exception("internal mcp tool %s failed", name)
            return _ok(
                req_id,
                {"content": [{"type": "text", "text": str(exc)}], "isError": True},
            )

    if method == "ping":
        return _ok(req_id, {})

    return _err(req_id, -32601, f"Method not found: {method}")


def _ok(req_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    if req_id is None:
        return {}
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _err(req_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}
