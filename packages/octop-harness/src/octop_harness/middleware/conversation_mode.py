"""Turn-scoped Ask / Plan / Craft: allowlist tools, disable skills, restrict plan writes.

Hosts stamp ``configurable["conversation_mode"]`` (``ask`` | ``plan`` | ``craft``).
Unknown / missing → craft (full tools). Ask/Plan: unknown tools are denied.
Hosts may add extra read-only names via ``conversation_mode_extra_read_tools``.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Awaitable, Callable, Iterable
from typing import Any, Literal, cast

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain.agents.middleware.types import AgentState
from langchain_core.messages import SystemMessage, ToolMessage
from langchain_core.tools.base import BaseTool
from langgraph.config import get_config
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command

from octop_harness.middleware.runtime import runtime_config

logger = logging.getLogger(__name__)

ConversationMode = Literal["ask", "plan", "craft"]

CONFIG_MODE_KEY = "conversation_mode"
CONFIG_EXTRA_READ_KEY = "conversation_mode_extra_read_tools"

DEFAULT_CONVERSATION_MODE: ConversationMode = "craft"
_VALID_MODES: frozenset[str] = frozenset({"ask", "plan", "craft"})

ASK_READ_TOOLS: frozenset[str] = frozenset(
    {
        "ls",
        "read_file",
        "glob",
        "grep",
        "web_fetch",
        "tavily_search",
        "brave_search",
        "google_search",
        "kimi_search",
        "searchfree_search",
        "current_time",
    }
)
PLAN_WRITE_TOOLS: frozenset[str] = frozenset({"write_file", "edit_file"})
_FS_PATH_KEYS = ("file_path", "path")
_PLAN_SLUG_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,120}$")
_SKILL_DIR_MARKERS = ("/skills/", "/_builtin_skills/")

_ASK_HINT = (
    "You are in Ask mode: answer with read-only tools (file read, search, web fetch). "
    "Do not create, edit, delete, execute, or use skills. If the user needs changes, "
    "say they can switch to Plan or Craft mode."
)
_PLAN_HINT = (
    "You are in Plan mode: explore with read-only tools, then write a step-by-step plan "
    "to plans/<english-slug>.md (ASCII slug, e.g. plans/add-ask-plan-modes.md). "
    "You may create or edit only that plans/*.md file. Do not execute, edit other files, "
    "or use skills. When the plan file is written, stop and wait for the user to confirm."
)
_CRAFT_HINT = ""

_HINTS: dict[ConversationMode, str] = {
    "ask": _ASK_HINT,
    "plan": _PLAN_HINT,
    "craft": _CRAFT_HINT,
}


def parse_conversation_mode(value: object | None) -> ConversationMode:
    """Return a valid mode. ``None`` / unknown → craft."""
    if isinstance(value, str) and value in _VALID_MODES:
        return cast(ConversationMode, value)
    return DEFAULT_CONVERSATION_MODE


def is_allowed_plan_path(path: str) -> bool:
    """True when *path* is a single ``plans/<ascii-slug>.md`` workspace file."""
    raw = (path or "").strip().replace("\\", "/")
    if not raw or ".." in raw:
        return False
    parts = [p for p in raw.lstrip("/").split("/") if p and p != "."]
    if len(parts) != 2 or parts[0] != "plans":
        return False
    name = parts[1]
    if not name.endswith(".md"):
        return False
    return bool(_PLAN_SLUG_RE.fullmatch(name[:-3]))


def extra_read_tools(configurable: dict[str, Any] | None) -> frozenset[str]:
    raw = (configurable or {}).get(CONFIG_EXTRA_READ_KEY)
    if not isinstance(raw, list):
        return frozenset()
    return frozenset(str(name).strip() for name in raw if str(name).strip())


def allowed_tool_names(
    mode: ConversationMode,
    *,
    extra_read: Iterable[str] = (),
) -> frozenset[str]:
    """Model-visible tool names for *mode*. Craft is unrestricted (empty sentinel)."""
    if mode == "craft":
        return frozenset()
    allowed = set(ASK_READ_TOOLS)
    allowed.update(str(name).strip() for name in extra_read if str(name).strip())
    if mode == "plan":
        allowed.update(PLAN_WRITE_TOOLS)
    return frozenset(allowed)


def _tool_base_name(name: str) -> str:
    trimmed = name.strip()
    slash = trimmed.rfind("/")
    return trimmed[slash + 1 :] if slash >= 0 else trimmed


def _tool_name(tool: BaseTool | dict[str, Any]) -> str:
    if isinstance(tool, dict):
        fn = tool.get("function")
        if isinstance(fn, dict) and fn.get("name"):
            return str(fn["name"])
        if tool.get("name"):
            return str(tool["name"])
        return ""
    return str(getattr(tool, "name", "") or "")


def _path_from_args(params: dict[str, Any]) -> str:
    for key in _FS_PATH_KEYS:
        raw = params.get(key)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return ""


def _mentions_skill_dir(text: str) -> bool:
    hay = text.replace("\\", "/")
    if not hay:
        return False
    padded = hay if hay.startswith("/") else f"/{hay}"
    return any(marker in padded for marker in _SKILL_DIR_MARKERS)


def _iter_arg_strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, dict):
        out: list[str] = []
        for item in value.values():
            out.extend(_iter_arg_strings(item))
        return out
    if isinstance(value, (list, tuple)):
        nested: list[str] = []
        for item in value:
            nested.extend(_iter_arg_strings(item))
        return nested
    return []


def mode_from_configurable(configurable: dict[str, Any] | None) -> ConversationMode:
    return parse_conversation_mode((configurable or {}).get(CONFIG_MODE_KEY))


def _current_configurable() -> dict[str, Any]:
    try:
        cfg = get_config()
    except RuntimeError:
        return {}
    raw = cfg.get("configurable")
    return raw if isinstance(raw, dict) else {}


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
    return request.override(system_message=SystemMessage(content=merged))


def _clear_skills_metadata(request: ModelRequest[Any]) -> ModelRequest[Any]:
    raw = request.state.get("skills_metadata")
    if not raw:
        return request
    new_state = cast(AgentState[Any], {**request.state, "skills_metadata": []})
    return request.override(state=new_state)


def apply_conversation_mode_to_request(request: ModelRequest[Any]) -> ModelRequest[Any]:
    """Filter Ask/Plan tools, drop skill catalog, append the mode hint."""
    configurable = runtime_config(request).get("configurable") or {}
    if not isinstance(configurable, dict):
        configurable = {}
    mode = mode_from_configurable(configurable)
    hint = _HINTS[mode]
    out = request
    if mode != "craft":
        allowed = allowed_tool_names(mode, extra_read=extra_read_tools(configurable))
        tools_in = list(request.tools or [])
        filtered = [t for t in tools_in if _tool_base_name(_tool_name(t)) in allowed]
        if len(filtered) != len(tools_in):
            out = out.override(tools=filtered)
        out = _clear_skills_metadata(out)
    return _append_system_hint(out, hint)


def _blocked_message(*, tool_name: str, mode: ConversationMode, tool_call_id: str) -> ToolMessage:
    return ToolMessage(
        content=(
            f"Tool `{tool_name}` is not available in {mode} mode. "
            "Switch to Craft mode to run mutating or delegated tools."
        ),
        tool_call_id=tool_call_id,
        status="error",
    )


def _plan_path_blocked_message(*, path: str, tool_call_id: str) -> ToolMessage:
    return ToolMessage(
        content=(
            f"Plan mode may only write `plans/<ascii-slug>.md` (got {path!r}). Do not edit other workspace files."
        ),
        tool_call_id=tool_call_id,
        status="error",
    )


def _tool_block_reason(
    *,
    tool_name: str,
    args: dict[str, Any],
    mode: ConversationMode,
    extra_read: Iterable[str],
) -> ToolMessage | None:
    if mode == "craft":
        return None
    allowed = allowed_tool_names(mode, extra_read=extra_read)
    base = _tool_base_name(tool_name)
    if base not in allowed:
        return _blocked_message(tool_name=tool_name or base, mode=mode, tool_call_id="")
    if any(_mentions_skill_dir(chunk) for chunk in _iter_arg_strings(args)):
        return _blocked_message(tool_name=tool_name or base, mode=mode, tool_call_id="")
    if mode == "plan" and base in PLAN_WRITE_TOOLS:
        path = _path_from_args(args)
        if not is_allowed_plan_path(path):
            return _plan_path_blocked_message(path=path, tool_call_id="")
    return None


class ConversationModeMiddleware(AgentMiddleware[Any, Any]):
    """Apply turn ``conversation_mode`` from LangGraph configurable."""

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
        blocked = self._maybe_block(request)
        if blocked is not None:
            return blocked
        return handler(request)

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]],
    ) -> ToolMessage | Command[Any]:
        blocked = self._maybe_block(request)
        if blocked is not None:
            return blocked
        return await handler(request)

    def _maybe_block(self, request: ToolCallRequest) -> ToolMessage | None:
        configurable = _current_configurable()
        mode = mode_from_configurable(configurable)
        tool_name = str(request.tool_call.get("name") or "")
        raw_args = request.tool_call.get("args") or {}
        args: dict[str, Any] = raw_args if isinstance(raw_args, dict) else {}
        blocked = _tool_block_reason(
            tool_name=tool_name,
            args=args,
            mode=mode,
            extra_read=extra_read_tools(configurable),
        )
        if blocked is None:
            return None
        logger.info("ConversationMode blocked tool %s (mode=%s)", tool_name, mode)
        return ToolMessage(
            content=blocked.content,
            tool_call_id=str(request.tool_call.get("id") or ""),
            status="error",
        )


__all__ = [
    "ASK_READ_TOOLS",
    "CONFIG_EXTRA_READ_KEY",
    "CONFIG_MODE_KEY",
    "DEFAULT_CONVERSATION_MODE",
    "PLAN_WRITE_TOOLS",
    "ConversationMode",
    "ConversationModeMiddleware",
    "allowed_tool_names",
    "apply_conversation_mode_to_request",
    "extra_read_tools",
    "is_allowed_plan_path",
    "mode_from_configurable",
    "parse_conversation_mode",
]
