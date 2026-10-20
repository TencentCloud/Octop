"""Slash parsing, context, formatting, i18n, stats, and runtime dispatch."""

from __future__ import annotations

import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from octop_harness.backends.utils import DEFENSIVE_OP_ERRORS

logger = logging.getLogger(__name__)

Locale = str

# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

_SLASH_RE = re.compile(r"^\s*/([a-zA-Z][\w-]*)\s?(.*)$", re.DOTALL)


@dataclass(frozen=True)
class SlashCommand:
    name: str
    args: str


def parse_slash(text: str | None) -> SlashCommand | None:
    if not text:
        return None
    m = _SLASH_RE.match(text)
    if not m or not m.group(1):
        return None
    return SlashCommand(name=m.group(1).lower(), args=m.group(2).strip())


# ---------------------------------------------------------------------------
# Sink
# ---------------------------------------------------------------------------


class SlashSink(Protocol):
    """Adapter every origin provides; receives the response stream of a slash command."""

    async def text(self, line: str) -> None:
        """Emit one line of command output."""
        ...

    async def complete(self) -> None:
        """Mark the response stream as finished."""
        ...


class BufferSink:
    """Accumulates output in memory. Used by tests and chat slash responses."""

    def __init__(self) -> None:
        self.lines: list[str] = []
        self.actions: list[dict[str, Any]] = []
        self.completed: bool = False

    async def text(self, line: str) -> None:
        self.lines.append(line)

    async def action(self, name: str, **payload: Any) -> None:
        self.actions.append({"action": name, **payload})

    async def complete(self) -> None:
        self.completed = True


# ---------------------------------------------------------------------------
# Context
# ---------------------------------------------------------------------------


@dataclass
class RuntimeSlashCtx:
    agent_id: str
    thread_id: str | None
    locale: str
    default_model: str | None = None
    cancel_stream: Callable[[str, str], None] | None = None
    get_thread_model: Callable[[str, str], str | None] | None = None
    set_thread_model: Callable[[str, str, str], None] | None = None
    clear_thread_model: Callable[[str, str], None] | None = None
    list_skills: Callable[[], Awaitable[list[dict[str, Any]]]] | None = field(default=None, repr=False)


RuntimeHandler = Callable[
    ["RuntimeSlashDispatcher", SlashCommand, RuntimeSlashCtx, SlashSink],
    Awaitable[None],
]

# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


async def thread_message_count(agent: Any, thread_id: str) -> int:
    """Best-effort message count from LangGraph checkpoint."""
    if hasattr(agent, "aget_history"):
        try:
            msgs = await agent.aget_history(thread_id, limit=10_000)
            return len(list(msgs))
        except DEFENSIVE_OP_ERRORS:
            logger.warning("aget_history failed for thread=%s", thread_id, exc_info=True)
            return 0
    if hasattr(agent, "graph"):
        try:
            state = await agent.graph.aget_state({"configurable": {"thread_id": thread_id}})
            raw = list((state.values or {}).get("messages") or [])
            return len(raw)
        except DEFENSIVE_OP_ERRORS:
            logger.warning("graph.aget_state failed for thread=%s", thread_id, exc_info=True)
    return 0


# ---------------------------------------------------------------------------
# Format
# ---------------------------------------------------------------------------


def markdown_kv_block(title: str, rows: list[tuple[str, str]]) -> str:
    lines = [f"**{title}**", ""]
    lines.extend(f"- **{key}**: {value}" for key, value in rows)
    return "\n".join(lines)


def markdown_bullets(title: str, bullets: list[str]) -> str:
    lines = [f"**{title}**", ""]
    lines.extend(f"- {item}" for item in bullets)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# i18n (runtime commands)
# ---------------------------------------------------------------------------

_MESSAGES: dict[str, dict[str, str]] = {
    "model.override": {"en": "Model override: {model}", "zh": "模型覆盖：{model}"},
    "model.current_default": {
        "en": "Model: {model} (agent default)",
        "zh": "模型：{model}（Agent 默认）",
    },
    "model.usage": {
        "en": "No model override. Usage: /model <provider:model>",
        "zh": "无模型覆盖。用法：/model <provider:model>",
    },
    "model.cleared": {"en": "Model override cleared.", "zh": "已清除模型覆盖。"},
    "model.set": {"en": "Model for this thread → {model}.", "zh": "此话题模型 → {model}。"},
    "skills.usage": {"en": "Usage: /skills [list]", "zh": "用法：/skills [list]"},
    "skills.title": {"en": "Skills", "zh": "技能"},
    "skills.empty": {"en": "No skills installed.", "zh": "暂无已安装技能。"},
    "skills.unavailable": {"en": "Skill list unavailable.", "zh": "无法获取技能列表。"},
    "skills.enabled": {"en": "on", "zh": "启用"},
    "skills.disabled": {"en": "off", "zh": "禁用"},
    "stop.done": {"en": "Generation stopped.", "zh": "已停止生成。"},
    "stop.empty": {
        "en": "No active generation to stop for this session.",
        "zh": "当前会话没有进行中的生成。",
    },
}


def normalize_locale(locale: str | None) -> Locale:
    if not locale:
        return "zh"
    base = locale.split("-", 1)[0].lower()
    return "zh" if base == "zh" else "en"


def tr(key: str, locale: Locale, **kwargs: object) -> str:
    table = _MESSAGES[key]
    loc = normalize_locale(locale)
    text = table.get(loc) or table["en"]
    return text.format(**kwargs)


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


class RuntimeSlashDispatcher:
    """Dispatch runtime slash commands (stop, skills, model)."""

    def __init__(self) -> None:
        from octop_harness.slash.handlers import RUNTIME_HANDLERS

        self._handlers = dict(RUNTIME_HANDLERS)

    def has(self, name: str) -> bool:
        return name in self._handlers

    async def handle(self, cmd: SlashCommand, ctx: RuntimeSlashCtx, sink: SlashSink) -> bool:
        handler = self._handlers.get(cmd.name)
        if handler is None:
            return False
        await handler(self, cmd, ctx, sink)
        await sink.complete()
        return True


def build_runtime_dispatcher() -> RuntimeSlashDispatcher:
    return RuntimeSlashDispatcher()
