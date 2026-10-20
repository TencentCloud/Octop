"""Bind the current ``thread_id`` for session-header HTTP injection."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse

from octop_harness.llm.session_header import session_header_scope
from octop_harness.middleware.runtime import runtime_config


def thread_id_from_request(request: ModelRequest) -> str | None:
    """Read ``configurable.thread_id`` from the live graph config."""
    cfg = runtime_config(request)
    configurable = cfg.get("configurable") if isinstance(cfg, dict) else None
    if not isinstance(configurable, dict):
        return None
    raw = configurable.get("thread_id")
    return raw if isinstance(raw, str) and raw.strip() else None


class SessionHeaderMiddleware(AgentMiddleware[Any, Any]):
    """Keep ``session_header_scope`` active around each graph model call.

    ``HarnessAgent.call`` / ``stream`` already open a scope for the whole
    invocation (including auxiliary LLM calls). This middleware covers paths
    that never enter those methods, such as ``stream_events``. When the graph
    config has no ``thread_id``, the handler runs without a new scope so an
    outer invocation id is preserved.
    """

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        thread_id = thread_id_from_request(request)
        if thread_id is None:
            return handler(request)
        with session_header_scope(thread_id):
            return handler(request)

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        thread_id = thread_id_from_request(request)
        if thread_id is None:
            return await handler(request)
        with session_header_scope(thread_id):
            return await handler(request)


__all__ = ["SessionHeaderMiddleware", "thread_id_from_request"]
