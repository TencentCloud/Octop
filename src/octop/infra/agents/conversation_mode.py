"""Conversation modes (Ask / Plan / Craft) — turn-scoped tool overlays (#616)."""

from __future__ import annotations

from typing import Literal

from octop.infra.agents.tool_catalog import CRITICAL_TOOLS

ConversationMode = Literal["ask", "plan", "craft"]

DEFAULT_CONVERSATION_MODE: ConversationMode = "craft"

_VALID_MODES: frozenset[str] = frozenset({"ask", "plan", "craft"})

# Mutating / side-effect tools blocked in Ask (and Plan). Must not intersect CRITICAL_TOOLS.
_ASK_TOOLS_DISABLED: frozenset[str] = frozenset(
    {
        "write_file",
        "edit_file",
        "execute",
        "write_env_file",
        "send_file_to_user",
        "browser_use",
        "desktop_screenshot",
        "generate_image",
        "generate_video",
        "mobile_screenshot",
        "mobile_tap",
        "mobile_swipe",
        "mobile_launch_app",
        "mobile_ui_dump",
        "mobile_handoff_to_user",
        # cron mutations
        "cronjob_create",
        "cronjob_update",
        "cronjob_delete",
        "cronjob_run_now",
    }
)

# Delegation / ACP / team tools that would escape Ask/Plan into a full-autonomy child.
# ``task`` is CRITICAL for agent settings (cannot be permanently disabled) but MUST be
# turn-blocked in Ask/Plan — same idea as Cursor Plan: explore + write the plan only.
_ORCHESTRATION_ESCAPE_TOOLS: frozenset[str] = frozenset(
    {
        "task",
        "acp_runner",
        "ask_agent",
    }
)

assert _ASK_TOOLS_DISABLED.isdisjoint(CRITICAL_TOOLS)


def parse_conversation_mode(value: object | None) -> ConversationMode:
    """Return a valid mode. ``None`` → craft; unknown non-null → ``ValueError``."""
    if value is None:
        return DEFAULT_CONVERSATION_MODE
    if not isinstance(value, str) or value not in _VALID_MODES:
        raise ValueError(f"invalid conversation_mode: {value!r}")
    return value  # type: ignore[return-value]


def conversation_mode_tools_disabled(mode: ConversationMode) -> frozenset[str]:
    """Turn-scoped denylist. ``craft`` → empty; Ask/Plan → mutating + no orchestration escape."""
    if mode == "craft":
        return frozenset()
    return _ASK_TOOLS_DISABLED | _ORCHESTRATION_ESCAPE_TOOLS


def merge_tools_disabled(
    agent_disabled: frozenset[str] | set[str],
    mode: ConversationMode,
) -> frozenset[str]:
    """Union agent denylist with mode overlay (Ask/Plan never re-enable tools)."""
    return frozenset(agent_disabled) | conversation_mode_tools_disabled(mode)


DEFAULT_CONVERSATION_MODE_CONFIG_KEY = "default_conversation_mode"


def default_conversation_mode_from_config(cfg: object | None) -> ConversationMode:
    """Read agent default mode from config; missing/null → craft."""
    if not isinstance(cfg, dict):
        return DEFAULT_CONVERSATION_MODE
    raw = cfg.get(DEFAULT_CONVERSATION_MODE_CONFIG_KEY)
    if raw is None:
        return DEFAULT_CONVERSATION_MODE
    return parse_conversation_mode(raw)


def normalize_config_default_conversation_mode(cfg: dict[str, object]) -> dict[str, object]:
    """Validate/normalize ``default_conversation_mode`` in-place copy. Raises ``ValueError``."""
    if DEFAULT_CONVERSATION_MODE_CONFIG_KEY not in cfg:
        return dict(cfg)
    out = dict(cfg)
    raw = out.get(DEFAULT_CONVERSATION_MODE_CONFIG_KEY)
    if raw is None:
        out.pop(DEFAULT_CONVERSATION_MODE_CONFIG_KEY, None)
        return out
    out[DEFAULT_CONVERSATION_MODE_CONFIG_KEY] = parse_conversation_mode(raw)
    return out


def apply_default_conversation_mode(
    config: dict[str, object],
    mode: object | None,
) -> dict[str, object]:
    """Write ``default_conversation_mode`` when *mode* is set. Mutates and returns *config*."""
    if mode is None:
        return config
    config[DEFAULT_CONVERSATION_MODE_CONFIG_KEY] = parse_conversation_mode(mode)
    return config
