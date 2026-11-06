"""Global SecurityPolicy persistence in the settings table."""

from __future__ import annotations

import json
import logging
from dataclasses import replace
from typing import Any

from octop_harness.security.models import SecurityPolicy

from octop.infra.agents.secret_file.paths import REQUEST_SECRET_FILE_TOOL
from octop.infra.db.repos.settings import SettingsRepo

logger = logging.getLogger(__name__)

_SETTINGS_KEY = "security_policy"


def _default_policy() -> SecurityPolicy:
    """Octop defaults when no ``security_policy`` row exists in settings."""
    data = SecurityPolicy.defaults().to_dict()
    data["hitl"]["enabled"] = False
    data["tool_guard"] = {"enabled": True, "mode": "warn"}
    return SecurityPolicy.from_dict(data)


def without_secret_file_approval(policy: SecurityPolicy) -> SecurityPolicy:
    """The credential tool is answered only by its dedicated input channel."""
    tools = policy.hitl.tools
    if tools == "default" or REQUEST_SECRET_FILE_TOOL not in tools:
        return policy
    return replace(
        policy,
        hitl=replace(
            policy.hitl, tools=[name for name in tools if name != REQUEST_SECRET_FILE_TOOL]
        ),
    )


class SecuritySettingsStore:
    """Read/write global :class:`SecurityPolicy` in the settings table."""

    def __init__(self, *, settings_repo: SettingsRepo) -> None:
        self._settings = settings_repo

    def load(self) -> SecurityPolicy:
        raw = self._settings.get(_SETTINGS_KEY)
        if not raw:
            return _default_policy()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("invalid security_policy JSON in settings; using defaults")
            return _default_policy()
        if not isinstance(data, dict):
            return _default_policy()
        return SecurityPolicy.from_dict(data)

    def save(self, policy: SecurityPolicy | dict[str, Any]) -> SecurityPolicy:
        resolved = (
            policy if isinstance(policy, SecurityPolicy) else SecurityPolicy.from_dict(policy)
        )
        self._settings.set(_SETTINGS_KEY, json.dumps(resolved.to_dict(), ensure_ascii=False))
        return resolved

    def harness_policy(self) -> SecurityPolicy:
        return without_secret_file_approval(self.load())


def tool_execution_may_pause(policy: SecurityPolicy) -> bool:
    """True when a tool call can pause for human approval.

    Covers the admin HITL switch and command-guard ``require_approval``.
    ``ask_user_question`` is a separate collaboration pause and is ignored here.
    """
    if policy.hitl.enabled:
        return True
    guard = policy.tool_guard
    return bool(guard.enabled and guard.mode == "require_approval")
