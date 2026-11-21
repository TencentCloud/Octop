"""Loopback MCP so a managed runner can call ``ask_agent`` like a native expert."""

from __future__ import annotations

from typing import Any

from octop.infra.agents.acp.delegation import AgentScope

_PROTOCOL = "2024-11-05"

_ASK = {
    "name": "ask_agent",
    "description": (
        "Ask another expert and wait for the answer. "
        "When the user writes @Name, call this with expert set to that name "
        "and do not answer in their place."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "expert": {"type": "string", "description": "Expert name from the user's @mention."},
            "message": {"type": "string", "description": "What to ask that expert."},
        },
        "required": ["expert", "message"],
    },
}

_LIST = {
    "name": "agent_list",
    "description": "List other experts the current user can call by name.",
    "inputSchema": {"type": "object", "properties": {}},
}


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


def _peer_lines(team: Any, scope: AgentScope) -> str:
    from octop_harness.teams.team_manager import TeamManager

    peers = team.list_peers(scope.user_id, exclude_agent_id=scope.from_agent_id)
    lines: list[str] = []
    for entry in peers:
        name = TeamManager.peer_display_name(entry)
        description = str((entry.metadata or {}).get("description") or "").strip()
        lines.append(f"- {name}: {description}" if description else f"- {name}")
    return "\n".join(lines) if lines else "No other experts are available."


async def handle_agents_mcp(
    body: dict[str, Any],
    *,
    scope: AgentScope,
    team: Any,
) -> dict[str, Any]:
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
                "serverInfo": {"name": "octop-agents", "version": "0.1.0"},
            },
        )
    if method == "notifications/initialized":
        return {}
    if method == "tools/list":
        allowed = set(scope.tools)
        cards = [card for card in (_LIST, _ASK) if card["name"] in allowed]
        return _ok(req_id, {"tools": cards})
    if method == "ping":
        return _ok(req_id, {})
    if method != "tools/call":
        return _err(req_id, -32601, f"Method not found: {method}")

    arguments = _arguments(params)
    name = str(params.get("name") or "") if isinstance(params, dict) else ""
    if name not in set(scope.tools):
        return _text_result(req_id, f"Unknown tool: {name}", failed=True)
    if name == "agent_list":
        return _text_result(req_id, _peer_lines(team, scope))
    if name != "ask_agent":
        return _text_result(req_id, f"Unknown tool: {name}", failed=True)

    expert = str(arguments.get("expert") or "").strip().lstrip("@")
    message = str(arguments.get("message") or "").strip()
    if not expert or not message:
        return _text_result(req_id, "expert and message are required.", failed=True)
    entry = team.resolve_peer(scope.user_id, expert, exclude_agent_id=scope.from_agent_id)
    if entry is None:
        return _text_result(req_id, f"expert not found: {expert}", failed=True)
    try:
        result = await team.call_peer(
            from_agent_id=scope.from_agent_id,
            to_agent_id=entry.agent_id,
            message=message,
            user_id=scope.user_id,
            source_thread_id=scope.thread_id or None,
            session_key=scope.session_key or None,
        )
    except Exception as exc:
        return _text_result(req_id, f"ask_agent failed: {exc}", failed=True)
    answer = str(getattr(result, "response", "") or "").strip() or "No answer."
    who = str(getattr(result, "name", "") or expert)
    return _text_result(req_id, f"{who}: {answer}")
