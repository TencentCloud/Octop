"""Loopback MCP for the cron tools a native expert already has."""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Any

from octop.infra.agents.acp.mcp_tools import dispatch

_SCOPES: dict[str, CronScope] = {}
_TOKENS: dict[tuple[int, str, str, str, tuple[str, ...]], str] = {}


@dataclass(frozen=True)
class CronScope:
    user_id: int
    agent_id: str
    thread_id: str
    session_key: str
    tools: tuple[str, ...] = ()


def cron_scope(token: str) -> CronScope | None:
    return _SCOPES.get(token)


def retain_cron_scope(scope: CronScope) -> str:
    """Reuse one token per expert, conversation, and enabled tool set."""
    key = (scope.user_id, scope.agent_id, scope.thread_id, scope.session_key, scope.tools)
    token = _TOKENS.get(key)
    if token is None:
        token = secrets.token_urlsafe(32)
        _TOKENS[key] = token
    _SCOPES[token] = scope
    return token


async def handle_cron_mcp(
    body: dict[str, Any],
    *,
    scope: CronScope,
    cron_manager: Any,
) -> dict[str, Any]:
    from octop.infra.cron.tools import build_cronjob_tools

    tools = build_cronjob_tools(cron_manager) if cron_manager is not None else []
    if scope.tools:
        allowed = set(scope.tools)
        tools = [tool for tool in tools if str(getattr(tool, "name", "")) in allowed]
    if cron_manager is None and str(body.get("method") or "") == "tools/call":
        from octop.infra.agents.acp.mcp_tools import text_result

        return text_result(body.get("id"), "cron jobs are not available", failed=True)
    return await dispatch(
        body,
        server_name="octop-cron",
        tools=tools,
        config={
            "agent_id": scope.agent_id,
            "user": scope.user_id,
            "thread_id": scope.thread_id,
            "session_key": scope.session_key,
        },
    )
