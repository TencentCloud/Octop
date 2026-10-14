"""Fold system messages from the conversation into the leading system prompt.

Team dispatch hands a member its briefing as a ``SystemMessage`` in the turn
input, so the model request ends up with a system message after the member's
own system prompt, and on later dispatches after earlier turns as well. Several
providers reject that shape: Qwen chat templates (vLLM, DashScope compatible
mode) answer "System message must be at the beginning", and langchain-anthropic
raises "Received multiple non-consecutive system messages". Merge them into the
system prompt at model-call time instead; the stored conversation is unchanged.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.messages import SystemMessage


def fold_system_messages(request: ModelRequest[Any]) -> ModelRequest[Any]:
    folded = [m for m in request.messages if isinstance(m, SystemMessage)]
    if not folded:
        return request
    blocks: list[Any] = (
        list(request.system_message.content_blocks) if request.system_message else []
    )
    for message in folded:
        text = message.text
        if not text:
            continue
        blocks.append({"type": "text", "text": f"\n\n{text}" if blocks else text})
    return request.override(
        system_message=SystemMessage(content_blocks=blocks) if blocks else None,
        messages=[m for m in request.messages if not isinstance(m, SystemMessage)],
    )


class SystemMessageFoldMiddleware(AgentMiddleware[Any, Any]):
    def wrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], ModelResponse[Any]],
    ) -> ModelResponse[Any]:
        return handler(fold_system_messages(request))

    async def awrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], Awaitable[ModelResponse[Any]]],
    ) -> ModelResponse[Any]:
        return await handler(fold_system_messages(request))


__all__ = ["SystemMessageFoldMiddleware", "fold_system_messages"]
