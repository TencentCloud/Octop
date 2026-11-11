"""Apply per-turn provider-specific reasoning request parameters."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.messages import AIMessage
from langgraph.config import get_config

CONFIG_KEY = "octop_reasoning_overrides"
ROUNDTRIP_KEY = "octop_reasoning_roundtrip"


def _configured_request(request: ModelRequest[Any]) -> ModelRequest[Any]:
    configurable = dict(get_config().get("configurable") or {})
    overrides = configurable.get(CONFIG_KEY)
    if not isinstance(overrides, dict) or not overrides:
        return request
    model = request.model
    if not hasattr(model, "model_copy"):
        return request
    updates = dict(overrides.get("model_fields") or {})
    extra = overrides.get("extra_body")
    if isinstance(extra, dict) and extra and hasattr(model, "extra_body"):
        current = dict(getattr(model, "extra_body", None) or {})
        current.update(extra)
        updates["extra_body"] = current
    if not updates:
        return request
    configured = model.model_copy(update=updates)
    return request.override(model=configured)


def _roundtrip_supported() -> bool:
    """Whether this turn's model accepts ``reasoning_content`` on assistant replay.

    Providers without a reasoning adapter reject a persisted
    ``additional_kwargs.reasoning_content`` on the next turn (groq answers 400:
    ``property 'reasoning_content' is unsupported``), so the request builder
    gates replay with ``octop_reasoning_roundtrip``. An absent or non-boolean
    gate keeps the message intact, matching callers that predate the gate.
    """
    configurable = get_config().get("configurable") or {}
    if isinstance(configurable, dict) and isinstance(configurable.get(ROUNDTRIP_KEY), bool):
        return bool(configurable[ROUNDTRIP_KEY])
    return True


def _scrub_replayed_reasoning(request: ModelRequest[Any]) -> ModelRequest[Any]:
    if _roundtrip_supported():
        return request
    dropped = False
    scrubbed: list[Any] = []
    for message in request.messages:
        if isinstance(message, AIMessage) and "reasoning_content" in (
            message.additional_kwargs or {}
        ):
            kwargs = dict(message.additional_kwargs or {})
            kwargs.pop("reasoning_content", None)
            scrubbed.append(message.model_copy(update={"additional_kwargs": kwargs}))
            dropped = True
        else:
            scrubbed.append(message)
    if not dropped:
        return request
    return request.override(messages=scrubbed)


class ReasoningRequestMiddleware(AgentMiddleware[Any, Any]):
    def wrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], ModelResponse[Any]],
    ) -> ModelResponse[Any]:
        return handler(_scrub_replayed_reasoning(_configured_request(request)))

    async def awrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], Awaitable[ModelResponse[Any]]],
    ) -> ModelResponse[Any]:
        return await handler(_scrub_replayed_reasoning(_configured_request(request)))


__all__ = ["CONFIG_KEY", "ReasoningRequestMiddleware", "ROUNDTRIP_KEY"]
