"""Loopback MCP for memory tools. Attached only when this expert enables memory."""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Any

from octop.infra.agents.acp.mcp_tools import dispatch

_SCOPES: dict[str, MemoryScope] = {}
_TOKENS: dict[tuple[str, tuple[str, ...]], str] = {}


@dataclass(frozen=True)
class MemoryScope:
    agent_id: str
    tools: tuple[str, ...] = ()


def memory_scope(token: str) -> MemoryScope | None:
    return _SCOPES.get(token)


def retain_memory_scope(agent_id: str, tools: tuple[str, ...] = ()) -> str:
    """Reuse one token per expert and enabled tool set."""
    key = (agent_id, tools)
    token = _TOKENS.get(key)
    if token is None:
        token = secrets.token_urlsafe(32)
        _TOKENS[key] = token
    _SCOPES[token] = MemoryScope(agent_id=agent_id, tools=tools)
    return token


def memory_enabled(config: Any) -> bool:
    """True only when the stored expert config explicitly turns memory on."""
    if not isinstance(config, dict):
        return False
    memory = config.get("memory")
    return isinstance(memory, dict) and memory.get("memory_enabled") is True


async def handle_memory_mcp(
    body: dict[str, Any],
    *,
    service: Any,
    tools_allowed: tuple[str, ...] = (),
) -> dict[str, Any]:
    from octop_harness.builtin.tools.memory_tools import build_memory_tools

    from octop.infra.agents.acp.mcp_tools import text_result

    if service is None and str(body.get("method") or "") == "tools/call":
        return text_result(
            body.get("id"),
            "memory is enabled but this expert has not reloaded yet",
            failed=True,
        )
    tools = build_memory_tools(service) if service is not None else []
    if tools_allowed:
        allowed = set(tools_allowed)
        tools = [tool for tool in tools if str(getattr(tool, "name", "")) in allowed]
    return await dispatch(body, server_name="octop-memory", tools=tools)
