"""Tests for security settings store."""

from __future__ import annotations

from unittest.mock import MagicMock

from octop_harness.security.models import SecurityPolicy

from octop.infra.agents.security import SecuritySettingsStore


def test_load_defaults_when_missing() -> None:
    repo = MagicMock()
    repo.get.return_value = None
    store = SecuritySettingsStore(settings_repo=repo)
    policy = store.load()
    assert policy.hitl.enabled is False
    assert policy.tool_guard.enabled is True
    assert policy.tool_guard.mode == "warn"
    assert policy.resolve_interrupt_on() is None


def test_save_round_trip() -> None:
    repo = MagicMock()
    repo.get.return_value = None
    store = SecuritySettingsStore(settings_repo=repo)
    policy = SecurityPolicy.from_dict({"hitl": {"enabled": False}})
    saved = store.save(policy)
    assert saved.hitl.enabled is False
    repo.set.assert_called_once()
    key, raw = repo.set.call_args[0]
    assert key == "security_policy"
    assert '"enabled": false' in raw or '"enabled": false' in raw.replace(" ", "")
