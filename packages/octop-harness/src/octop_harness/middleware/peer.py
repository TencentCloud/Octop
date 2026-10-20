"""``PeerAgentMiddleware`` — let an agent call other agents via ``ask_agent``."""

from __future__ import annotations

import logging
import re
from collections.abc import Awaitable, Callable, Sequence
from typing import TYPE_CHECKING, Any

from deepagents.middleware._utils import append_to_system_message
from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.messages import HumanMessage

from octop_harness.middleware.runtime import runtime_config
from octop_harness.teams.profile import (
    Language,
    peer_description,
    peer_guidance_cards,
)
from octop_harness.teams.tools import build_team_tools
from octop_harness.teams.util import (
    PeerInvokeMode,
    clamp_peer_invoke_mode,
    coerce_user_id,
    parse_peer_invoke_mode,
    parse_team_peers,
)

if TYPE_CHECKING:
    from octop_harness.registry import AgentEntry
    from octop_harness.teams.team_manager import TeamManager

logger = logging.getLogger(__name__)

# Agent names: ``@data-analyst``, ``@分析师``. Skip ``@path/to/file.ext``.
_AGENT_AT_RE = re.compile(r"@([^\W\d_][\w\-]*)(?![\w./\-~]*\.\w)")


def has_agent_at_mention(text: str) -> bool:
    """True when *text* contains an ``@agent`` token (not ``@file.ext``)."""
    return _AGENT_AT_RE.search(text) is not None


def _latest_user_text(request: ModelRequest) -> str:
    messages = getattr(request, "messages", None) or []
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            return _stringify_content(msg.content).strip()
    return ""


def _stringify_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
        return "".join(parts)
    return str(content or "")


def render_peer_prompt(
    peers: list[AgentEntry],
    *,
    language: Language,
    display_name: Callable[[AgentEntry], str],
    async_enabled: bool,
    invoke_mode: PeerInvokeMode = "both",
) -> str:
    """Build the system-prompt block describing callable peers and ``@`` usage."""
    if language == "zh":
        lines = [
            "你可以通过工具调用同一用户下的其他专家。",
            "不确定找谁时先调用 agent_list。对方更擅长时用 ask_agent。",
        ]
        if peers:
            lines.append("当前可调用的其他专家:")
            lines.extend(_peer_lines(peers, display_name, language))
        else:
            lines.append("当前没有可调用的其他专家。")
        lines.append(
            "用户消息里的 @名字 (或近似名称、简称) 表示要把问题交给对方: "
            "先在专家名单里匹配, 命中则 ask_agent, 不要自己顶替. 名称不必完全精确."
            "名单里没有对应专家时, 改用 task 调用本系统提示词里已列出的 subagent, 不要编造专家.",
        )
        if invoke_mode == "async":
            lines.append("派工一律用 ask_agent (异步, 发完即返回; 对方完成后你会再被唤醒).")
        elif async_enabled:
            lines.append(
                "短问题用 ask_agent mode=sync; 长任务用 mode=background (完成后会主动回复用户)。",
            )
        else:
            lines.append("ask_agent 使用 mode=sync 等待对方立即回答。")
        return "\n".join(lines)

    lines = [
        "You can call other experts owned by the current user.",
        "Call agent_list when the best expert is unclear. Use ask_agent when their expertise fits better.",
    ]
    if peers:
        lines.append("Other experts you can call:")
        lines.extend(_peer_lines(peers, display_name, language))
    else:
        lines.append("No other experts are currently available.")
    lines.append(
        "When the user's message contains @Name (or a similar / abbreviated name), "
        "match an expert first and call ask_agent; do not answer in their place. "
        "Approximate names are fine. If no expert matches, use the task tool to "
        "run a subagent already listed in this system prompt. Do not invent an expert.",
    )
    if invoke_mode == "async":
        lines.append(
            "Always dispatch with ask_agent (async: return immediately; "
            "you will be invoked again when the teammate finishes)."
        )
    elif async_enabled:
        lines.append(
            "Use ask_agent mode=sync for quick questions. "
            "Use mode=background for slow work (the user gets a follow-up when it completes).",
        )
    else:
        lines.append("Use ask_agent with mode=sync and wait for the peer's answer.")
    return "\n".join(lines)


def _peer_card_lines(metadata: dict[str, Any], language: Language) -> list[str]:
    cards = peer_guidance_cards(metadata, language)
    if not cards:
        return []
    header = "  指引卡片:" if language == "zh" else "  Suggested asks:"
    lines = [header]
    for card in cards:
        title = card["title"]
        detail = card.get("description")
        lines.append(f"  - {title}: {detail}" if detail else f"  - {title}")
    return lines


def _peer_lines(
    peers: list[AgentEntry],
    display_name: Callable[[AgentEntry], str],
    language: Language,
) -> list[str]:
    lines: list[str] = []
    for entry in peers:
        name = display_name(entry)
        short = entry.agent_id[-6:]
        meta = entry.metadata or {}
        description = peer_description(meta, language)
        suffix = f": {description}" if description else ""
        lines.append(f"- {name} ({short}){suffix}")
        lines.extend(_peer_card_lines(meta, language))
    return lines


class PeerAgentMiddleware(AgentMiddleware[Any, Any]):
    """Expose ``agent_list`` / ``ask_agent`` and append a peer roster on ``@``.

    Prompt injection is request-scoped (``wrap_model_call``) and only runs when
    the latest user message contains an ``@agent`` token, so ordinary turns keep
    a stable system-prompt prefix for provider cache hits. The roster is
    appended after other prompt injectors. Tools are attached via ``self.tools``.
    A request-scoped ``peer_invoke_mode`` may replace ``ask_agent``'s schema
    for that turn when it tightens (never escalates) the agent's configured
    mode.
    """

    def __init__(
        self,
        team: TeamManager,
        *,
        language: Language = "zh",
        peer_invoke_mode: PeerInvokeMode = "both",
    ) -> None:
        super().__init__()
        self._team = team
        self._language: Language = language if language in ("en", "zh") else "zh"
        self._peer_invoke_mode: PeerInvokeMode = parse_peer_invoke_mode(peer_invoke_mode) or "both"
        modes: tuple[PeerInvokeMode, ...] = ("sync", "async", "both")
        self._tools_by_mode = {mode: build_team_tools(team, peer_invoke_mode=mode) for mode in modes}
        self.tools = self._tools_by_mode[self._peer_invoke_mode]

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        return handler(self._inject(request))

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        return await handler(self._inject(request))

    def _inject(self, request: ModelRequest) -> ModelRequest:
        overrides: dict[str, Any] = {}
        try:
            invoke_mode = self._request_invoke_mode(request)
            tools = self._tools_for_mode(request.tools, invoke_mode)
            block: str | None = None
            if has_agent_at_mention(_latest_user_text(request)):
                block = self._prompt_block(request, invoke_mode=invoke_mode)
            if tools is None and block is None:
                return request
            if tools is not None:
                overrides["tools"] = tools
            if block is not None:
                overrides["system_message"] = append_to_system_message(request.system_message, block)
        except Exception:  # prompt injection is best-effort; pylint: disable=broad-except
            logger.warning("PeerAgentMiddleware prompt injection failed", exc_info=True)
            return request
        return request.override(**overrides)

    def _request_invoke_mode(self, request: ModelRequest) -> PeerInvokeMode:
        configurable = runtime_config(request).get("configurable") or {}
        requested = parse_peer_invoke_mode(configurable.get("peer_invoke_mode"))
        return clamp_peer_invoke_mode(requested, self._peer_invoke_mode)

    def _tools_for_mode(
        self,
        tools: Sequence[Any],
        invoke_mode: PeerInvokeMode,
    ) -> list[Any] | None:
        if invoke_mode == self._peer_invoke_mode:
            return None
        replacement = next(tool for tool in self._tools_by_mode[invoke_mode] if tool.name == "ask_agent")
        return [replacement if getattr(tool, "name", None) == "ask_agent" else tool for tool in tools]

    def _prompt_block(self, request: ModelRequest, *, invoke_mode: PeerInvokeMode) -> str:
        configurable = runtime_config(request).get("configurable") or {}
        agent_id = configurable.get("agent_id")
        from_agent_id = str(agent_id) if agent_id else None
        user_id = coerce_user_id(configurable.get("user"))
        team_peers = parse_team_peers(configurable.get("team_peers"))

        peers: list[AgentEntry] = []
        if user_id is not None and from_agent_id:
            peers = self._team.list_peers(
                user_id,
                exclude_agent_id=from_agent_id,
                team_peers=team_peers,
            )
        return render_peer_prompt(
            peers,
            language=self._language,
            display_name=self._team.peer_display_name,
            async_enabled=self._team.enabled and invoke_mode != "sync",
            invoke_mode=invoke_mode,
        )


# Backward-compatible alias (removed from docs; keep import path working).
TeamMiddleware = PeerAgentMiddleware
render_team_prompt = render_peer_prompt

__all__ = [
    "PeerAgentMiddleware",
    "TeamMiddleware",
    "has_agent_at_mention",
    "render_peer_prompt",
    "render_team_prompt",
]
