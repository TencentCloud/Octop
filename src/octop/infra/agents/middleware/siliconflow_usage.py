"""Normalize SiliconFlow's repeated cumulative streaming usage metadata."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

_SILICONFLOW_HOST = "siliconflow.cn"
_USAGE_KEYS = ("token_usage", "usage")


def _model_candidates(model: Any) -> list[Any]:
    """Return a small, defensive chain of wrapped model objects."""
    candidates: list[Any] = []
    current = model
    for _ in range(4):
        if current is None or any(current is item for item in candidates):
            break
        candidates.append(current)
        current = getattr(current, "bound", None) or getattr(current, "model", None)
    return candidates


def is_siliconflow_model(model: Any) -> bool:
    """Return whether a routed model points at SiliconFlow's API host."""
    for candidate in _model_candidates(model):
        for attribute in ("base_url", "openai_api_base"):
            value = getattr(candidate, attribute, None)
            if _SILICONFLOW_HOST in str(value or "").lower():
                return True
    return False


def strip_stream_usage(message: Any) -> Any:
    """Remove provider usage fields from a completed AI message.

    SiliconFlow reports cumulative usage on every streamed chunk. LangChain
    adds those chunks together, so the resulting ``AIMessage.usage_metadata``
    is not a valid measurement. The explicit protocol usage events remain
    available to Octop's usage ledger; only the state message is sanitized so
    context estimation and summarization do not consume the inflated value.
    """
    if not isinstance(message, AIMessage):
        return message

    response_metadata = dict(message.response_metadata or {})
    for key in _USAGE_KEYS:
        response_metadata.pop(key, None)
    return message.model_copy(
        update={
            "usage_metadata": None,
            "response_metadata": response_metadata,
        }
    )


def _strip_response(response: Any) -> Any:
    if not isinstance(response, AIMessage):
        return response
    return strip_stream_usage(response)


class SiliconFlowUsageMiddleware(AgentMiddleware[Any, Any]):
    """Keep repeated cumulative provider usage out of agent state."""

    def _prepare(self, request: ModelRequest[Any]) -> ModelRequest[Any]:
        model = request.model
        if not is_siliconflow_model(model):
            return request
        sanitized = model | RunnableLambda(_strip_response)
        return request.override(model=sanitized)

    def wrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], ModelResponse[Any]],
    ) -> ModelResponse[Any]:
        return handler(self._prepare(request))

    async def awrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], Awaitable[ModelResponse[Any]]],
    ) -> ModelResponse[Any]:
        return await handler(self._prepare(request))


__all__ = ["SiliconFlowUsageMiddleware", "is_siliconflow_model", "strip_stream_usage"]
