"""Turn-scoped Ask / Plan / Craft: filter tools, inject system hint, block denylist calls."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.messages import SystemMessage, ToolMessage
from langchain_core.tools.base import BaseTool
from langgraph.config import get_config
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command

from octop.infra.agents.conversation_mode import (
    DEFAULT_CONVERSATION_MODE,
    ConversationMode,
    conversation_mode_tools_disabled,
    parse_conversation_mode,
)

logger = logging.getLogger(__name__)

CONFIG_MODE_KEY = "conversation_mode"
CONFIG_HINT_KEY = "conversation_mode_hint"


def _tool_name(tool: BaseTool | dict[str, Any]) -> str:
    if isinstance(tool, dict):
        fn = tool.get("function")
        if isinstance(fn, dict) and fn.get("name"):
            return str(fn["name"])
        if tool.get("name"):
            return str(tool["name"])
        return ""
    return str(getattr(tool, "name", "") or "")


def mode_from_configurable(configurable: dict[str, Any] | None) -> ConversationMode:
    """Resolve turn mode from LangGraph configurable; unknown → craft."""
    raw = (configurable or {}).get(CONFIG_MODE_KEY)
    if raw is None:
        return DEFAULT_CONVERSATION_MODE
    try:
        return parse_conversation_mode(raw)
    except ValueError:
        return DEFAULT_CONVERSATION_MODE


def _current_mode() -> ConversationMode:
    cfg = get_config().get("configurable") or {}
    if not isinstance(cfg, dict):
        return DEFAULT_CONVERSATION_MODE
    return mode_from_configurable(cfg)


def _current_hint() -> str:
    cfg = get_config().get("configurable") or {}
    if not isinstance(cfg, dict):
        return ""
    raw = cfg.get(CONFIG_HINT_KEY)
    return raw.strip() if isinstance(raw, str) else ""


def _hint_already_present(content: str | list[Any] | Any, hint: str) -> bool:
    if isinstance(content, str):
        return hint in content
    if isinstance(content, list):
        for block in content:
            if isinstance(block, str) and hint in block:
                return True
            if isinstance(block, dict):
                text = block.get("text")
                if isinstance(text, str) and hint in text:
                    return True
        return False
    return hint in str(content)


def _append_system_hint(request: ModelRequest[Any], hint: str) -> ModelRequest[Any]:
    cleaned = hint.strip()
    if not cleaned:
        return request
    existing = request.system_message
    if existing is None:
        return request.override(system_message=SystemMessage(content=cleaned))
    content = existing.content
    if _hint_already_present(content, cleaned):
        return request
    if isinstance(content, str):
        merged: str | list[Any] = f"{content.rstrip()}\n\n{cleaned}"
    elif isinstance(content, list):
        merged = [*content, {"type": "text", "text": cleaned}]
    else:
        merged = f"{content}\n\n{cleaned}"
    return request.override(system_message=SystemMessage(content=merged))


def _filter_tools(request: ModelRequest[Any], disabled: frozenset[str]) -> ModelRequest[Any]:
    if not disabled:
        return request
    tools_in = list(request.tools or [])
    if not tools_in:
        return request
    filtered = [t for t in tools_in if _tool_name(t) not in disabled]
    if len(filtered) == len(tools_in):
        return request
    return request.override(tools=filtered)


def apply_conversation_mode_to_request(request: ModelRequest[Any]) -> ModelRequest[Any]:
    """Filter Ask/Plan denylist tools and append the stamped system hint."""
    mode = _current_mode()
    out = _filter_tools(request, conversation_mode_tools_disabled(mode))
    return _append_system_hint(out, _current_hint())


def _blocked_tool_message(
    *, tool_name: str, mode: ConversationMode, tool_call_id: str
) -> ToolMessage:
    from octop.i18n.domains.conversation import conversation_mode_tool_blocked

    cfg = get_config().get("configurable") or {}
    locale = "en"
    if isinstance(cfg, dict):
        raw_locale = cfg.get("locale")
        if isinstance(raw_locale, str) and raw_locale.strip():
            locale = raw_locale.strip()
    return ToolMessage(
        content=conversation_mode_tool_blocked(tool_name, mode, locale),
        tool_call_id=tool_call_id,
        status="error",
    )


class ConversationModeMiddleware(AgentMiddleware[Any, Any]):
    """Apply turn ``conversation_mode`` from configurable — no agent-global mutation."""

    def wrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], ModelResponse[Any]],
    ) -> ModelResponse[Any]:
        return handler(apply_conversation_mode_to_request(request))

    async def awrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], Awaitable[ModelResponse[Any]]],
    ) -> ModelResponse[Any]:
        return await handler(apply_conversation_mode_to_request(request))

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command[Any]],
    ) -> ToolMessage | Command[Any]:
        mode = _current_mode()
        disabled = conversation_mode_tools_disabled(mode)
        tool_name = str(request.tool_call.get("name") or "")
        if tool_name and tool_name in disabled:
            logger.info("ConversationMode blocked tool %s (mode=%s)", tool_name, mode)
            return _blocked_tool_message(
                tool_name=tool_name,
                mode=mode,
                tool_call_id=str(request.tool_call.get("id") or ""),
            )
        return handler(request)

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]],
    ) -> ToolMessage | Command[Any]:
        mode = _current_mode()
        disabled = conversation_mode_tools_disabled(mode)
        tool_name = str(request.tool_call.get("name") or "")
        if tool_name and tool_name in disabled:
            logger.info("ConversationMode blocked tool %s (mode=%s)", tool_name, mode)
            return _blocked_tool_message(
                tool_name=tool_name,
                mode=mode,
                tool_call_id=str(request.tool_call.get("id") or ""),
            )
        return await handler(request)


__all__ = [
    "CONFIG_HINT_KEY",
    "CONFIG_MODE_KEY",
    "ConversationModeMiddleware",
    "apply_conversation_mode_to_request",
    "mode_from_configurable",
]
