"""``ChatRequest`` — a normalized one-call invocation parameter object.

Per design doc §4:
    - Accepts ``messages`` as ``str`` / ``list[dict]`` / ``list[BaseMessage]``;
      normalization happens at request boundaries (the agent's invoke
      method calls :func:`ChatRequest.normalize_messages` before constructing
      the LangGraph input).
    - Provides convenience constructors via :py:meth:`coerce` so callers can
      pass plain strings or kwargs dicts without explicit ``ChatRequest(...)``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)


@dataclass
class ChatRequest:
    """One chat invocation's parameters.

    Attributes:
        messages: User input. May be a string (becomes a single user message),
            a list of OpenAI-style dicts, or a list of LangChain ``BaseMessage``s.
        thread_id: Conversation thread identifier. Auto-generated when ``None``.
        user: Optional user identifier (recorded in session logs).
        source: Optional source label, e.g. ``"cli"`` / ``"web"``.
        model: Optional ``"<provider>/<model_id>"`` override; takes precedence
            over both the model selector and ``default_model``.
        mcp_servers: MCP server names to expose as tools for this invocation.
            ``None`` (default) disables MCP tools. Pass an explicit list to
            opt in. Use together with :attr:`mcp_use_default` only when you
            want the agent's ``mcp_default_servers`` instead of a custom list.
        mcp_use_default: When ``True``, expose tools from
            ``HarnessAgentConfig.mcp_default_servers`` for this invocation.
        skills: Optional skill names to expose for this invocation. When set,
            only the listed skills appear in the system prompt (empty list
            disables all skills). ``None`` (default) leaves the full skill set.
        conversation_mode: Optional turn permission mode (``ask`` / ``plan`` /
            ``craft``). Ask/Plan force ``skills=[]`` and hide MCP tools.
        agent_id: Optional agent identifier recorded in
            ``RunnableConfig.configurable`` (e.g. for logging middleware).
        configurable: Extra ``RunnableConfig.configurable`` entries.
        metadata: Extra ``RunnableConfig.metadata`` entries.
        recursion_limit: Override the default LangGraph recursion limit.
    """

    messages: str | list[dict[str, Any]] | list[BaseMessage]
    thread_id: str | None = None
    user: str | None = None
    source: str | None = None
    model: str | None = None
    mcp_servers: list[str] | None = None
    mcp_use_default: bool = False
    skills: list[str] | None = None
    conversation_mode: str | None = None
    agent_id: str | None = None
    configurable: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None
    callbacks: list[Any] | None = None
    recursion_limit: int | None = None

    # Track whether thread_id was auto-generated so that callers (and the
    # agent) can distinguish "user didn't care" from "user explicitly chose this id".
    _auto_thread_id: bool = field(default=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.thread_id is None:
            self.thread_id = uuid.uuid4().hex
            self._auto_thread_id = True

    # ------------------------------------------------------------------
    # Construction helpers
    # ------------------------------------------------------------------

    @classmethod
    def coerce(cls, request: ChatRequest | str | dict[str, Any]) -> ChatRequest:
        """Accept str / dict / ChatRequest and return a ChatRequest."""
        if isinstance(request, cls):
            return request
        if isinstance(request, str):
            return cls(messages=request)
        if isinstance(request, dict):
            return cls(**request)
        raise TypeError(
            f"Cannot coerce {type(request).__name__} to ChatRequest; expected ChatRequest, str, or dict.",
        )

    # ------------------------------------------------------------------
    # Message normalization
    # ------------------------------------------------------------------

    def normalize_messages(self) -> list[BaseMessage]:
        """Return ``self.messages`` as a list of LangChain ``BaseMessage`` objects."""
        return _normalize_messages(self.messages)

    # ------------------------------------------------------------------
    # Mapping to LangGraph RunnableConfig
    # ------------------------------------------------------------------

    def to_runnable_config(self) -> dict[str, Any]:
        """Build a ``RunnableConfig``-compatible dict.

        ``thread_id`` / ``user`` / ``source`` / ``model`` / ``skills`` /
        ``conversation_mode`` / ``agent_id`` are injected into ``configurable``
        automatically; existing keys in ``self.configurable`` win over the
        auto-injected values except Ask/Plan which force empty skills/MCP.
        """
        from octop_harness.middleware.conversation_mode import parse_conversation_mode

        configurable: dict[str, Any] = {"thread_id": self.thread_id}
        _assign_if_not_none(
            configurable,
            user=self.user,
            source=self.source,
            model=self.model,
            agent_id=self.agent_id,
        )
        if self.mcp_use_default:
            configurable["mcp_use_default"] = True
        if self.mcp_servers is not None:
            configurable["mcp_servers"] = list(self.mcp_servers)
        if self.skills is not None:
            configurable["skills"] = list(self.skills)
        if self.conversation_mode is not None:
            configurable["conversation_mode"] = parse_conversation_mode(self.conversation_mode)
        if self.configurable:
            configurable.update(self.configurable)
        _restrict_ask_plan_config(configurable)

        config: dict[str, Any] = {"configurable": configurable}
        if self.metadata:
            config["metadata"] = dict(self.metadata)
        if self.callbacks:
            config["callbacks"] = list(self.callbacks)
        if self.recursion_limit is not None:
            config["recursion_limit"] = self.recursion_limit
        return config


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _assign_if_not_none(target: dict[str, Any], **values: object) -> None:
    for key, value in values.items():
        if value is not None:
            target[key] = value


def _restrict_ask_plan_config(configurable: dict[str, Any]) -> None:
    from octop_harness.middleware.conversation_mode import parse_conversation_mode

    mode = parse_conversation_mode(configurable.get("conversation_mode"))
    if mode not in ("ask", "plan"):
        return
    configurable["conversation_mode"] = mode
    configurable["skills"] = []
    configurable["mcp_servers"] = []
    configurable.pop("mcp_use_default", None)


_ROLE_TO_MESSAGE: dict[str, type[BaseMessage]] = {
    "user": HumanMessage,
    "human": HumanMessage,
    "assistant": AIMessage,
    "ai": AIMessage,
    "system": SystemMessage,
    "tool": ToolMessage,
}


def _normalize_messages(
    messages: str | list[dict[str, Any]] | list[BaseMessage],
) -> list[BaseMessage]:
    """Convert any supported input form into ``list[BaseMessage]``."""
    if isinstance(messages, str):
        return [HumanMessage(content=messages)]

    if not isinstance(messages, list):
        raise TypeError(
            f"messages must be str / list[dict] / list[BaseMessage], got {type(messages).__name__}",
        )

    if not messages:
        raise ValueError("messages list must not be empty")

    # Detect homogeneous BaseMessage list early.
    if all(isinstance(m, BaseMessage) for m in messages):
        return list(messages)  # type: ignore[arg-type]

    normalized: list[BaseMessage] = []
    for idx, item in enumerate(messages):
        if isinstance(item, BaseMessage):
            normalized.append(item)
            continue
        if not isinstance(item, dict):
            raise TypeError(
                f"messages[{idx}] must be a dict or BaseMessage, got {type(item).__name__}",
            )
        normalized.append(_dict_to_message(item, idx))
    return normalized


def _dict_to_message(item: dict[str, Any], idx: int) -> BaseMessage:
    role = item.get("role")
    if role is None:
        raise ValueError(f"messages[{idx}] missing required 'role' key")
    cls = _ROLE_TO_MESSAGE.get(role)
    if cls is None:
        raise ValueError(
            f"messages[{idx}] has unknown role {role!r}; expected one of {sorted(_ROLE_TO_MESSAGE)}",
        )

    content = item.get("content", "")
    extra: dict[str, Any] = {k: v for k, v in item.items() if k not in ("role", "content")}

    if cls is ToolMessage:
        # ToolMessage requires a tool_call_id field.
        tool_call_id = extra.pop("tool_call_id", None)
        if tool_call_id is None:
            raise ValueError(f"messages[{idx}] (tool message) requires 'tool_call_id'")
        return ToolMessage(content=content, tool_call_id=tool_call_id, **extra)

    return cls(content=content, **extra)


__all__ = ["ChatRequest"]
