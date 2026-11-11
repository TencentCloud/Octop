"""MCP JSON-RPC protocol for the external Octop Agent Gateway."""

from __future__ import annotations

import json
import logging
from importlib.metadata import PackageNotFoundError, version
from typing import TYPE_CHECKING, Any

from mcp.shared.version import SUPPORTED_PROTOCOL_VERSIONS

from octop.infra.errors import OctopError

if TYPE_CHECKING:
    from octop.infra.agent_mcp.service import AgentMcpGatewayService
    from octop.infra.users.identity import User

logger = logging.getLogger(__name__)


def _server_version() -> str:
    try:
        return version("octop")
    except PackageNotFoundError:
        return "0.0.0"


TOOLS: list[dict[str, Any]] = [
    {
        "name": "list_octop_experts",
        "description": "List Octop experts that the authenticated user can call.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "call_octop_expert",
        "description": (
            "Send one task to an Octop expert. Omit thread_id for a new isolated conversation. "
            "Pass the returned thread_id to continue that conversation."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "expert_id": {"type": "string", "minLength": 1},
                "message": {"type": "string", "minLength": 1, "maxLength": 100000},
                "thread_id": {"type": "string", "minLength": 1},
            },
            "required": ["expert_id", "message"],
            "additionalProperties": False,
        },
    },
    {
        "name": "resume_octop_expert",
        "description": "Resume an MCP expert thread that is waiting for tool approval or input.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "expert_id": {"type": "string", "minLength": 1},
                "thread_id": {"type": "string", "minLength": 1},
                "decisions": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 16,
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {
                                "type": "string",
                                "enum": ["approve", "edit", "reject", "respond"],
                            },
                            "message": {"type": "string"},
                            "edited_action": {"type": "object"},
                        },
                        "required": ["type"],
                        "additionalProperties": True,
                    },
                },
            },
            "required": ["expert_id", "thread_id", "decisions"],
            "additionalProperties": False,
        },
    },
]


async def handle_agent_mcp_request(
    *,
    service: AgentMcpGatewayService,
    user: User,
    body: dict[str, Any],
) -> dict[str, Any]:
    method = body.get("method")
    request_id = body.get("id")
    params = body.get("params") or {}

    if method == "initialize":
        requested = str(params.get("protocolVersion") or "") if isinstance(params, dict) else ""
        protocol = (
            requested
            if requested in SUPPORTED_PROTOCOL_VERSIONS
            else SUPPORTED_PROTOCOL_VERSIONS[-1]
        )
        return _ok(
            request_id,
            {
                "protocolVersion": protocol,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {
                    "name": "octop-agent-mcp-gateway",
                    "version": _server_version(),
                },
            },
        )

    if method == "notifications/initialized":
        return {}
    if method == "ping":
        return _ok(request_id, {})
    if method == "tools/list":
        return _ok(request_id, {"tools": TOOLS})
    if method != "tools/call":
        return _error(request_id, -32601, f"Method not found: {method}")

    if not isinstance(params, dict):
        return _error(request_id, -32602, "tools/call params must be an object")
    name = str(params.get("name") or "")
    arguments = params.get("arguments") or {}
    if not isinstance(arguments, dict):
        return _tool_result(request_id, {"error": "arguments must be an object"}, is_error=True)
    nested = arguments.get("kwargs")
    if set(arguments) == {"kwargs"} and isinstance(nested, dict):
        arguments = nested

    try:
        if name == "list_octop_experts":
            result = service.list_experts(user)
        elif name == "call_octop_expert":
            result = await service.call_expert(
                user,
                expert_id=str(arguments.get("expert_id") or ""),
                message=str(arguments.get("message") or ""),
                thread_id=(str(arguments["thread_id"]) if arguments.get("thread_id") else None),
            )
        elif name == "resume_octop_expert":
            raw_decisions = arguments.get("decisions")
            if not isinstance(raw_decisions, list):
                raise ValueError("decisions must be an array")
            result = await service.resume_expert(
                user,
                expert_id=str(arguments.get("expert_id") or ""),
                thread_id=str(arguments.get("thread_id") or ""),
                decisions=raw_decisions,
            )
        else:
            return _tool_result(
                request_id,
                {"error": f"unknown tool: {name}"},
                is_error=True,
            )
    except (OctopError, ValueError) as exc:
        return _tool_result(request_id, {"error": str(exc)}, is_error=True)
    except Exception:
        logger.exception("agent MCP tool %s failed", name)
        return _tool_result(request_id, {"error": "internal error"}, is_error=True)

    return _tool_result(request_id, result, is_error=result.get("status") == "failed")


def _ok(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    if request_id is None:
        return {}
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }


def _tool_result(request_id: Any, result: dict[str, Any], *, is_error: bool) -> dict[str, Any]:
    return _ok(
        request_id,
        {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(result, ensure_ascii=False, separators=(",", ":")),
                }
            ],
            "structuredContent": result,
            "isError": is_error,
        },
    )
