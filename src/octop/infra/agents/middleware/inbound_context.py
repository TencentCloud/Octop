"""Expose the current gateway identity to the model without changing chat history."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.messages import SystemMessage
from langgraph.config import get_config

from octop.i18n import tr
from octop.infra.gateway.process.inbound_context import INBOUND_CONTEXT_KEY


def _with_inbound_context(request: ModelRequest[Any]) -> ModelRequest[Any]:
    configurable = get_config().get("configurable") or {}
    context = configurable.get(INBOUND_CONTEXT_KEY)
    context = context if isinstance(context, dict) else None
    locale = str(context.get("locale") or "en") if context is not None else "en"
    block = tr("inbound.context_prompt", locale, context=json.dumps(context, ensure_ascii=False))
    system = request.system_message
    if system is None:
        system = SystemMessage(content=block)
    else:
        content = system.content
        blocks: list[str | dict[str, Any]] = (
            list(content) if isinstance(content, list) else [content]
        )
        blocks.append({"type": "text", "text": block})
        system = system.model_copy(update={"content": blocks})
    return request.override(system_message=system)


class InboundContextMiddleware(AgentMiddleware[Any, Any]):
    """Read per-call config; never cache a sender on the shared agent instance."""

    def wrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], ModelResponse[Any]],
    ) -> ModelResponse[Any]:
        return handler(_with_inbound_context(request))

    async def awrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], Awaitable[ModelResponse[Any]]],
    ) -> ModelResponse[Any]:
        return await handler(_with_inbound_context(request))
