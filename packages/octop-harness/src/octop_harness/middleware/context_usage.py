"""Capture context-window usage from the final outbound model request."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.messages import AIMessage

from octop_harness.backends.utils import DEFENSIVE_OP_ERRORS
from octop_harness.context_usage import (
    CONTEXT_USAGE_KEY,
    ContextUsage,
    build_context_usage,
    empty_context_usage,
    shrink_context_usage,
)
from octop_harness.middleware.runtime import runtime_config
from octop_harness.middleware.turn_model import max_input_tokens_from_model

logger = logging.getLogger(__name__)


def _thread_id_from_request(request: ModelRequest) -> str | None:
    try:
        from langgraph.config import get_config

        config = get_config()
        if isinstance(config, dict):
            configurable = config.get("configurable")
            if isinstance(configurable, dict):
                tid = configurable.get("thread_id")
                if isinstance(tid, str) and tid:
                    return tid
    except (RuntimeError, ImportError):
        pass

    cfg = runtime_config(request)
    configurable = cfg.get("configurable") if isinstance(cfg, dict) else None
    if isinstance(configurable, dict):
        tid = configurable.get("thread_id")
        if isinstance(tid, str) and tid:
            return tid
    return None


def _stamp_ai_messages(response: ModelResponse, payload: dict[str, Any]) -> ModelResponse:
    result = list(getattr(response, "result", None) or [])
    if not result:
        return response
    stamped: list[Any] = []
    changed = False
    for msg in result:
        if isinstance(msg, AIMessage):
            kwargs = dict(getattr(msg, "additional_kwargs", None) or {})
            kwargs[CONTEXT_USAGE_KEY] = payload
            stamped.append(msg.model_copy(update={"additional_kwargs": kwargs}))
            changed = True
        else:
            stamped.append(msg)
    if not changed:
        return response
    return ModelResponse(
        result=stamped,
        structured_response=getattr(response, "structured_response", None),
    )


class ContextUsageMiddleware(AgentMiddleware[Any, Any]):
    """Estimate segments from the final ``ModelRequest`` and persist on the AIMessage.

    Snapshots are stored in:
    - process memory keyed by ``thread_id`` (fast path)
    - ``AIMessage.additional_kwargs["context_usage"]`` (checkpointer-durable)
    """

    def __init__(
        self,
        *,
        mcp_tool_names: frozenset[str] | None = None,
        max_tokens: int = 0,
    ) -> None:
        super().__init__()
        self._mcp_tool_names = mcp_tool_names or frozenset()
        self._max_tokens = max_tokens
        self._snapshots: dict[str, ContextUsage] = {}

    def get_snapshot(self, thread_id: str) -> ContextUsage | None:
        return self._snapshots.get(thread_id)

    def clear_snapshot(self, thread_id: str) -> None:
        self._snapshots.pop(thread_id, None)

    def shrink_snapshot(self, thread_id: str, *, removed_tokens: int) -> ContextUsage | None:
        """Subtract compacted-away history from the stored snapshot.

        Called after a forced compaction, which updates graph state without a
        model call. The snapshot is preferred over the message stamp by
        :func:`resolve_context_usage`, so without this the host keeps reading
        the pre-compaction total until the next turn.
        """
        snap = self._snapshots.get(thread_id)
        if snap is None or snap.source == "empty":
            return None
        updated = shrink_context_usage(snap, removed_tokens)
        self._snapshots[thread_id] = updated
        return updated

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        return self._capture(request, handler(request))

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        return self._capture(request, await handler(request))

    def _capture(self, request: ModelRequest, response: ModelResponse) -> ModelResponse:
        try:
            # Prefer the routed request model window (ModelRouter runs outer→inner
            # before this middleware) so the ring matches the turn's context cap.
            cap = max_input_tokens_from_model(getattr(request, "model", None), fallback=self._max_tokens)
            if cap <= 0:
                cap = self._max_tokens
            usage = build_context_usage(
                request,
                response_messages=list(getattr(response, "result", None) or []),
                mcp_tool_names=self._mcp_tool_names,
                max_tokens=cap,
            )
            thread_id = _thread_id_from_request(request)
            if thread_id:
                self._snapshots[thread_id] = usage
            if usage.source == "empty":
                return response
            return _stamp_ai_messages(response, usage.to_dict())
        except DEFENSIVE_OP_ERRORS:  # pragma: no cover - defensive
            logger.warning("ContextUsageMiddleware capture failed", exc_info=True)
            return response


def resolve_context_usage(
    *,
    thread_id: str,
    middleware: ContextUsageMiddleware | None,
    messages: list[Any] | None,
    max_tokens: int | None,
) -> ContextUsage:
    """Resolve usage: memory first, then message payload, else empty."""
    from octop_harness.context_usage import context_usage_from_messages

    if middleware is not None:
        snap = middleware.get_snapshot(thread_id)
        if snap is not None and snap.source != "empty":
            return snap if max_tokens is None else snap.with_max_tokens(max_tokens)
    if messages:
        from_msg = context_usage_from_messages(messages)
        if from_msg is not None and (
            from_msg.source != "empty" or from_msg.used_tokens > 0 or from_msg.input_tokens > 0
        ):
            return from_msg if max_tokens is None else from_msg.with_max_tokens(max_tokens)
    return empty_context_usage(max_tokens=max_tokens or 0)


__all__ = ["ContextUsageMiddleware", "resolve_context_usage"]
