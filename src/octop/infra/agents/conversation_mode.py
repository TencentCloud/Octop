"""Conversation modes (Ask / Plan / Craft) — turn-scoped tool overlays (#616).

Ask / Plan denylists cover **builtin** Octop / harness tool names only. MCP and
custom connector tools are not name-denylisted here; mutating MCP tools may still
appear unless blocked by agent ``tools_disabled`` or connector policy. Prefer an
allowlist / mutating tag on MCP tools for stricter Ask if needed.
"""

from __future__ import annotations

from typing import Literal

from octop.infra.agents.tool_catalog import CRITICAL_TOOLS

ConversationMode = Literal["ask", "plan", "craft"]

DEFAULT_CONVERSATION_MODE: ConversationMode = "craft"

_VALID_MODES: frozenset[str] = frozenset({"ask", "plan", "craft"})

# Mutating / side-effect tools blocked in Ask and Plan. Must not intersect CRITICAL_TOOLS.
_ASK_PLAN_TOOLS_DISABLED: frozenset[str] = frozenset(
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

# Ask-only: no structured plan todos (Plan keeps write_todos).
_ASK_ONLY_TOOLS_DISABLED: frozenset[str] = frozenset({"write_todos"})

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

assert _ASK_PLAN_TOOLS_DISABLED.isdisjoint(CRITICAL_TOOLS)
# write_todos is CRITICAL (cannot be permanently disabled in agent settings) but Ask
# still turn-blocks it via middleware — same pattern as ``task``.


def parse_conversation_mode(value: object | None) -> ConversationMode:
    """Return a valid mode. ``None`` → craft; unknown non-null → ``ValueError``."""
    if value is None:
        return DEFAULT_CONVERSATION_MODE
    if not isinstance(value, str) or value not in _VALID_MODES:
        raise ValueError(f"invalid conversation_mode: {value!r}")
    return value  # type: ignore[return-value]


def conversation_mode_tools_disabled(mode: ConversationMode) -> frozenset[str]:
    """Turn-scoped builtin denylist.

    ``craft`` → empty; Plan → mutating + no orchestration escape; Ask → Plan set
    plus ``write_todos``. Does **not** cover MCP/custom tool names (see module doc).
    """
    if mode == "craft":
        return frozenset()
    base = _ASK_PLAN_TOOLS_DISABLED | _ORCHESTRATION_ESCAPE_TOOLS
    if mode == "ask":
        return base | _ASK_ONLY_TOOLS_DISABLED
    return base


def resolve_conversation_mode(
    *,
    explicit: object | None = None,
    thread_override: ConversationMode | None = None,
    agent_default: ConversationMode | None = None,
) -> ConversationMode:
    """Resolve turn mode: explicit → thread sticky → agent default → craft.

    Unknown non-null *explicit* values resolve to craft (compat) and do not fall
    through to sticky/agent defaults.
    """
    if isinstance(explicit, str) and explicit in _VALID_MODES:
        return explicit  # type: ignore[return-value]
    if explicit is not None:
        return DEFAULT_CONVERSATION_MODE
    if thread_override is not None:
        return thread_override
    if agent_default is not None:
        return agent_default
    return DEFAULT_CONVERSATION_MODE


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
