"""Deliver the team-dispatch briefing through the leading system prompt.

A team host hands each member a briefing (i18n ``teams.member_briefing`` /
``teams.member_briefing_with_history``) before running the member's turn.
``wire_host_dispatch``'s ``enrich()`` used to put that briefing into the turn
input as a ``SystemMessage``. Once the member thread has history the request
shape becomes ``[system, ...history..., system(briefing), human(task)]``, which
strict providers reject:

* Qwen chat templates behind vLLM / DashScope compatible mode answer
  ``400 System message must be at the beginning.``
* ``langchain_anthropic`` raises
  ``ValueError: Received multiple non-consecutive system messages.``

The entry also stays in the thread checkpoint, so every later turn keeps
failing until the history is trimmed.

The briefing now travels in ``configurable`` and this middleware appends it to
the leading system message at model-call time. Nothing is written into the
conversation, so transcripts, projections and the member page stay unchanged.
It also covers the first dispatch: the harness bootstrap middleware drops
in-conversation system messages on a fresh agent's first turn, which silently
lost the briefing (and left nothing for a fold-the-messages fix to recover).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.messages import SystemMessage
from langgraph.config import get_config

CONFIG_KEY = "octop_team_dispatch_briefing"


def _with_briefing(request: ModelRequest[Any]) -> ModelRequest[Any]:
    configurable = get_config().get("configurable") or {}
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
