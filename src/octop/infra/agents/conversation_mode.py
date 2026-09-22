"""Ask / Plan / Craft helpers for Octop (policy SoT lives in harness-agent)."""

from __future__ import annotations

import re
from typing import Any

from harness_agent.middleware.conversation_mode import (
    CONFIG_EXTRA_READ_KEY,
    CONFIG_MODE_KEY,
    DEFAULT_CONVERSATION_MODE,
    ConversationMode,
    is_allowed_plan_path,
    parse_conversation_mode,
)

HOST_READ_TOOLS: tuple[str, ...] = ("search_knowledge",)

_EXECUTE_EXACT = frozenset(
    {
        "执行计划",
        "按计划执行",
        "开始干",
        "开始干吧",
        "开始执行",
        "干吧",
        "开干",
        "executeplan",
        "executetheplan",
    }
)
_EXECUTE_CONTAINS = (
    "按计划执行",
    "execute the plan",
    "execute plan",
    "start executing",
)
_PLAN_FILE = r"plans/[a-zA-Z0-9][a-zA-Z0-9._-]{0,120}\.md"
_DASHBOARD_EXECUTE_RES = (
    re.compile(rf"请按\s*{_PLAN_FILE}\s*执行"),
    re.compile(rf"(?i)(?:please\s+)?execute\s+{_PLAN_FILE}"),
)
_PUNCT_RE = re.compile(r"[\s，。！？、,.!?;:'\"“”‘’]+")


def resolve_conversation_mode(
    *,
    explicit: object | None = None,
    thread_mode: object | None = None,
) -> ConversationMode:
    """explicit (if a valid mode string) → thread sticky → craft."""
    if isinstance(explicit, str) and explicit in {"ask", "plan", "craft"}:
        return explicit  # type: ignore[return-value]
    if explicit is not None:
        return DEFAULT_CONVERSATION_MODE
    if thread_mode is not None:
        return parse_conversation_mode(thread_mode)
    return DEFAULT_CONVERSATION_MODE


def plan_relpath_from_artifact(path: str) -> str:
    """Return ``plans/<slug>.md`` if *path* points at an allowed plan file."""
    raw = (path or "").strip().replace("\\", "/")
    parts = [p for p in raw.lstrip("/").split("/") if p and p != "."]
    if len(parts) >= 2 and parts[-2] == "plans":
        rel = f"plans/{parts[-1]}"
        if is_allowed_plan_path(rel):
            return rel
    stripped = raw.lstrip("/")
    return stripped if is_allowed_plan_path(stripped) else ""


def execute_user_message(plan_path: str, locale: str | None = None) -> str:
    """Visible user-turn text that tells craft mode to follow the plan file."""
    from octop.i18n import tr
    from octop.infra.utils.locale import DEFAULT_LOCALE

    rel = plan_relpath_from_artifact(plan_path) or plan_path.strip()
    return tr("conversation_mode.execute", locale or DEFAULT_LOCALE, path=rel)


def is_plan_execute_utterance(text: str) -> bool:
    """Loose match for IM/CLI 'run the pending plan' messages."""
    raw = (text or "").strip()
    if not raw:
        return False
    if any(pattern.search(raw) for pattern in _DASHBOARD_EXECUTE_RES):
        return True
    lowered = raw.lower()
    for needle in _EXECUTE_CONTAINS:
        if needle in lowered or needle in raw:
            return True
    compact = _PUNCT_RE.sub("", raw).lower()
    return compact in _EXECUTE_EXACT


def stamp_conversation_mode(
    request: dict[str, Any],
    mode: ConversationMode,
) -> None:
    """Write mode + Ask/Plan host overlays onto a harness request dict."""
    configurable = dict(request.get("configurable") or {})
    configurable[CONFIG_MODE_KEY] = mode
    if mode in ("ask", "plan"):
        configurable[CONFIG_EXTRA_READ_KEY] = list(HOST_READ_TOOLS)
        request["skills"] = []
        request["mcp_servers"] = []
        configurable["skills"] = []
        configurable["mcp_servers"] = []
        configurable.pop("mcp_use_default", None)
    request["configurable"] = configurable
    request["conversation_mode"] = mode


__all__ = [
    "CONFIG_EXTRA_READ_KEY",
    "CONFIG_MODE_KEY",
    "DEFAULT_CONVERSATION_MODE",
    "HOST_READ_TOOLS",
    "ConversationMode",
    "execute_user_message",
    "is_allowed_plan_path",
    "is_plan_execute_utterance",
    "parse_conversation_mode",
    "plan_relpath_from_artifact",
    "resolve_conversation_mode",
    "stamp_conversation_mode",
]
