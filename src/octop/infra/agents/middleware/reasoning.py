"""Apply per-turn provider-specific reasoning request parameters."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langgraph.config import get_config

from octop.infra.agents.providers.reasoning import model_with_reasoning

CONFIG_KEY = "octop_reasoning_overrides"


def _configured_request(request: ModelRequest[Any]) -> ModelRequest[Any]:
    configurable = dict(get_config().get("configurable") or {})
    overrides = configurable.get(CONFIG_KEY)
    if not isinstance(overrides, dict) or not overrides:
        return request
    model = model_with_reasoning(request.model, overrides)
    return request if model is request.model else request.override(model=model)


class ReasoningRequestMiddleware(AgentMiddleware[Any, Any]):
    def wrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], ModelResponse[Any]],
    ) -> ModelResponse[Any]:
        return handler(_configured_request(request))

    async def awrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], Awaitable[ModelResponse[Any]]],
    ) -> ModelResponse[Any]:
        return await handler(_configured_request(request))


__all__ = ["CONFIG_KEY", "ReasoningRequestMiddleware"]
