"""Append a team-dispatch briefing to the leading system prompt.

A team host hands each member a briefing before the member's turn. The briefing
travels in ``configurable`` and this middleware appends it at model-call time.
Nothing is written into the conversation: a ``SystemMessage`` in the turn input
lands mid-thread on later dispatches, and strict providers reject that shape
(Qwen chat templates return ``400 System message must be at the beginning``;
``langchain_anthropic`` raises on multiple non-consecutive system messages).
The harness bootstrap middleware also drops in-conversation system messages on
a fresh agent's first turn, which used to lose the briefing.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.messages import SystemMessage
from langgraph.config import get_config

CONFIG_KEY = "octop_team_dispatch_briefing"


def _with_briefing(request: ModelRequest[Any]) -> ModelRequest[Any]:
    configurable = dict(get_config().get("configurable") or {})
    briefing = configurable.get(CONFIG_KEY)
    if not isinstance(briefing, str):
        return request
    text = briefing.strip()
    if not text:
        return request
    blocks: list[Any] = (
        list(request.system_message.content_blocks) if request.system_message else []
    )
    if blocks:
        text = f"\n\n{text}"
    blocks.append({"type": "text", "text": text})
    return request.override(system_message=SystemMessage(content_blocks=blocks))


class TeamDispatchBriefingMiddleware(AgentMiddleware[Any, Any]):
    """Append the host's dispatch briefing to the member's system prompt."""

    def wrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], ModelResponse[Any]],
    ) -> ModelResponse[Any]:
        return handler(_with_briefing(request))

    async def awrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], Awaitable[ModelResponse[Any]]],
    ) -> ModelResponse[Any]:
        return await handler(_with_briefing(request))


__all__ = ["CONFIG_KEY", "TeamDispatchBriefingMiddleware"]
