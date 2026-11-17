"""Loopback MCP so a managed runner can call ``send_file_to_user``.

The runner is another process, so it cannot use the in-process tool. This
server reads the file through that expert's workspace and returns the same
media block the chat and IM channels already push.
"""

from __future__ import annotations

import asyncio
import json
import secrets
from dataclasses import dataclass
from typing import Any

_PROTOCOL = "2024-11-05"
_DELIVERY = "send_file_to_user"

_SCOPES: dict[str, FileScope] = {}
_TOKENS: dict[str, str] = {}

_TOOL = {
    "name": _DELIVERY,
    "description": (
        "Send an existing workspace file to the user in this chat and on "
        "connected messaging channels. Pass the path the file was written to."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Workspace path of a file that already exists.",
            },
        },
        "required": ["file_path"],
    },
}


@dataclass(frozen=True)
class FileScope:
    agent_id: str


def file_scope(token: str) -> FileScope | None:
    return _SCOPES.get(token)


def retain_file_scope(agent_id: str) -> str:
    """Reuse one token per expert so the ACP session is not reloaded each turn."""
    token = _TOKENS.get(agent_id)
    if token is None:
        token = secrets.token_urlsafe(32)
        _TOKENS[agent_id] = token
    _SCOPES[token] = FileScope(agent_id=agent_id)
    return token


def _ok(req_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    if req_id is None:
        return {}
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _err(req_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def _arguments(params: Any) -> dict[str, Any]:
    if not isinstance(params, dict):
        return {}
    raw = params.get("arguments") or {}
    if not isinstance(raw, dict):
        return {}
    nested = raw.get("kwargs")
    if nested is not None and set(raw.keys()) == {"kwargs"} and isinstance(nested, dict):
        return nested
    return raw


def _text_result(req_id: Any, text: str, *, failed: bool = False) -> dict[str, Any]:
    return _ok(req_id, {"content": [{"type": "text", "text": text}], "isError": failed})


async def handle_files_mcp(body: dict[str, Any], *, workspace: Any) -> dict[str, Any]:
    """Answer one JSON-RPC request. An empty dict means the caller should return 202."""
    method = str(body.get("method") or "")
    req_id = body.get("id")
    params = body.get("params") or {}

    if method == "initialize":
        return _ok(
            req_id,
            {
                "protocolVersion": _PROTOCOL,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "octop-files", "version": "0.1.0"},
            },
        )
    if method == "notifications/initialized":
        return {}
    if method == "tools/list":
        return _ok(req_id, {"tools": [_TOOL]})
    if method == "ping":
        return _ok(req_id, {})
    if method != "tools/call":
        return _err(req_id, -32601, f"Method not found: {method}")

    name = str(params.get("name") or "") if isinstance(params, dict) else ""
    if name != _DELIVERY:
        return _text_result(req_id, f"Unknown tool: {name}", failed=True)
    file_path = str(_arguments(params).get("file_path") or "").strip()
    if not file_path:
        return _text_result(req_id, "file_path is required.", failed=True)

    from octop_harness.builtin.tools.send_file import build_send_file_to_user_tool

    tool = build_send_file_to_user_tool(workspace)
    result = await asyncio.to_thread(tool.invoke, {"file_path": file_path})
    if not isinstance(result, dict):
        return _text_result(req_id, str(result), failed=True)
    marked = {**result, "octop_delivery": _DELIVERY}
    return _text_result(req_id, json.dumps(marked, ensure_ascii=False))
