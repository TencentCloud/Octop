"""Session modes a managed expert can pin, keyed by the underlying agent.

These are the mode ids each agent documents for ``session/set_mode``. A live
session still only switches to an id that agent actually advertises.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

# Same markers as octop-harness ``is_unattended_mode``. Kept here so this
# package does not import a harness module newer than the pinned release.
_UNATTENDED_MARKERS = (
    "yolo",
    "bypass",
    "full-access",
    "fullaccess",
    "auto-accept",
    "autoaccept",
    "unrestricted",
    "danger",
)


def is_unattended_mode(value: object) -> bool:
    """True when a session mode id means the agent should run without asking."""
    folded = str(value or "").lower()
    return any(marker in folded for marker in _UNATTENDED_MARKERS)


# ``ask`` and ``craft`` are Octop's own conversation modes. ``plan`` is also an
# ACP mode id (CodeBuddy, OpenCode), so a stored ``plan`` is kept.
_NATIVE = frozenset({"ask", "craft"})


@dataclass(frozen=True)
class AcpSessionMode:
    id: str
    name_zh: str
    name_en: str
    hint_zh: str
    hint_en: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def _mode(mode_id: str, name_zh: str, name_en: str, hint_zh: str, hint_en: str) -> AcpSessionMode:
    return AcpSessionMode(mode_id, name_zh, name_en, hint_zh, hint_en)


_CODEBUDDY = (
    _mode(
        "default",
        "默认",
        "Default",
        "危险操作需要确认。",
        "Asks before dangerous actions.",
    ),
    _mode(
        "acceptEdits",
        "接受编辑",
        "Accept edits",
        "信任目录里的改文件不再询问。",
        "Auto-approves file edits in trusted directories.",
    ),
    _mode(
        "plan",
        "规划",
        "Plan",
        "先规划，基本只读。",
        "Plan first. Mostly read-only.",
    ),
    _mode(
        "auto",
        "自动",
        "Auto",
        "安全操作自动通过，有风险的仍会询问。",
        "Approves safe actions automatically. Risky ones still ask.",
    ),
    _mode(
        "bypassPermissions",
        "YOLO",
        "YOLO",
        "跳过大部分审批，包括改文件和运行命令。",
        "Skips most approvals, including file edits and commands.",
    ),
)

_CATALOG: dict[str, tuple[AcpSessionMode, ...]] = {
    "codebuddy": _CODEBUDDY,
    "claude_code": _CODEBUDDY,
    "opencode": (
        _mode(
            "build",
            "构建",
            "Build",
            "默认可改代码。敏感操作仍可能询问。",
            "Default coding agent. Sensitive actions may still ask.",
        ),
        _mode(
            "plan",
            "规划",
            "Plan",
            "分析为主，少改项目文件。",
            "Explore and plan, with few project edits.",
        ),
    ),
    "kimi_code": (
        _mode(
            "default",
            "默认",
            "Default",
            "按 Kimi 自己的规则确认操作。",
            "Kimi asks under its own rules.",
        ),
        _mode(
            "yolo",
            "YOLO",
            "YOLO",
            "不再弹出审批。",
            "Runs without approval prompts.",
        ),
    ),
    # Ids from ``@zed-industries/codex-acp``, the adapter Octop launches.
    "codex": (
        _mode(
            "auto",
            "自动",
            "Auto",
            "可在工作区里改文件。",
            "Can edit files inside the workspace.",
        ),
        _mode(
            "read-only",
            "只读",
            "Read-only",
            "只读，不改文件。",
            "Read-only. Does not edit files.",
        ),
        _mode(
            "full-access",
            "完全访问",
            "Full access",
            "关闭沙箱，相当于 YOLO。",
            "Turns the sandbox off. This is the YOLO mode.",
        ),
    ),
}


def session_modes(runner: str) -> list[AcpSessionMode]:
    return list(_CATALOG.get((runner or "").strip(), ()))


def yolo_session_mode_id(runner: str) -> str:
    for mode in session_modes(runner):
        if is_unattended_mode(mode.id):
            return mode.id
    return ""


def approval_for_session(session_mode: str, permission_mode: str, *, runner: str) -> str:
    """``ask`` or ``yolo`` for this turn.

    An unattended mode id skips approval. When the agent publishes one, every
    other mode asks. Agents with no such mode keep the chat's own setting.
    """
    if is_unattended_mode(session_mode):
        return "yolo"
    if session_mode and yolo_session_mode_id(runner):
        return "ask"
    return "yolo" if permission_mode == "yolo" else "ask"


def resolve_managed_session_mode(
    *,
    explicit: object = None,
    stored: object = None,
    config: dict[str, Any] | None = None,
) -> str:
    """Mode id for this turn.

    Stored ``ask`` and ``craft`` are Octop conversation modes and are ignored.
    ``plan`` is also an ACP mode id, so a stored plan is kept.
    """
    chosen = _acp_mode_id(explicit) or _acp_mode_id(stored)
    if chosen:
        return chosen
    cfg = config if isinstance(config, dict) else {}
    pinned = _acp_mode_id(cfg.get("managed_session_mode"))
    if pinned:
        return pinned
    if cfg.get("managed_permission_mode") == "yolo":
        runner = cfg.get("managed_runner")
        return yolo_session_mode_id(runner if isinstance(runner, str) else "")
    return ""


def _acp_mode_id(value: object) -> str:
    if not isinstance(value, str):
        return ""
    text = value.strip()
    if not text or text in _NATIVE:
        return ""
    if len(text) > 64 or any(
        ch not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-" for ch in text
    ):
        return ""
    return text
