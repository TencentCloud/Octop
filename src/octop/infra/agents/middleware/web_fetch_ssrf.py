"""Reject private-network targets before the harness ``web_fetch`` tool runs."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command

from octop.infra.utils.ssrf_guard import UnsafeOutboundUrl, validate_http_url_resolved

_WEB_FETCH_TOOL = "web_fetch"
_URL_ARG = "url"


def _url_from_tool_call(tool_call: Mapping[str, Any]) -> str | None:
    args = tool_call.get("args")
    if not isinstance(args, dict):
        return None
    raw_url = args.get(_URL_ARG)
    return raw_url.strip() if isinstance(raw_url, str) and raw_url.strip() else None


def _blocked_message(tool_call: Mapping[str, Any], reason: str) -> ToolMessage:
    return ToolMessage(
        content=f"web_fetch blocked: {reason}",
        tool_call_id=str(tool_call.get("id") or ""),
        status="error",
    )


class WebFetchSSRFGuardMiddleware(AgentMiddleware[Any, Any]):
    """Validate web-fetch URLs, including all DNS-resolved destination IPs."""

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]],
    ) -> ToolMessage | Command[Any]:
        tool_call = request.tool_call
        if str(tool_call.get("name") or "") != _WEB_FETCH_TOOL:
            return await handler(request)

        url = _url_from_tool_call(tool_call)
        if url is None:
            return await handler(request)
        try:
            await validate_http_url_resolved(url, field=_URL_ARG)
        except UnsafeOutboundUrl as exc:
            return _blocked_message(tool_call, str(exc))
        return await handler(request)


__all__ = ["WebFetchSSRFGuardMiddleware"]
