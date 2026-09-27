"""Global SecurityPolicy persistence in the settings table."""

from __future__ import annotations

import json
import logging
from typing import Any

from octop_harness.security.models import SecurityPolicy

from octop.infra.db.repos.settings import SettingsRepo

logger = logging.getLogger(__name__)

_SETTINGS_KEY = "security_policy"


def _default_policy() -> SecurityPolicy:
    """Octop defaults when no ``security_policy`` row exists in settings."""
    data = SecurityPolicy.defaults().to_dict()
    data["hitl"]["enabled"] = False
    data["tool_guard"] = {"enabled": True, "mode": "warn"}
    return SecurityPolicy.from_dict(data)


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
        return self.load()
