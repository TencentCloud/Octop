"""Tests for octop_harness.security.tool_guard."""

from __future__ import annotations

from octop_harness.security.models import SecurityPolicy
from octop_harness.security.tool_guard import ToolGuardEngine


def test_guard_blocks_rm_rf_root() -> None:
    engine = ToolGuardEngine(enabled=True, mode="block")
    result = engine.guard("bash", {"command": "rm -rf /"})
    assert result is not None
    assert not result.is_safe
    assert engine.should_block(result)


def test_guard_allows_safe_ls() -> None:
    engine = ToolGuardEngine(enabled=True, mode="block")
    result = engine.guard("bash", {"command": "ls -la"})
    assert result is not None
    assert result.is_safe
    assert not engine.should_block(result)


def test_guard_warn_mode_does_not_block() -> None:
    engine = ToolGuardEngine(enabled=True, mode="warn")
    result = engine.guard("bash", {"command": "rm -rf /"})
    assert result is not None
    assert not result.is_safe
    assert not engine.should_block(result)


def test_guard_require_approval_mode_blocks_medium_and_above() -> None:
    engine = ToolGuardEngine(enabled=True, mode="require_approval")
    result = engine.guard("bash", {"command": "rm -rf /"})
    assert result is not None
    assert not result.is_safe
    assert engine.should_block(result)


def test_build_tool_guard_hitl_request_shape() -> None:
    engine = ToolGuardEngine(enabled=True, mode="require_approval")
    result = engine.guard("bash", {"command": "rm -rf /"})
    assert result is not None
    from octop_harness.security.tool_guard.engine import build_tool_guard_hitl_request

    payload = build_tool_guard_hitl_request(result)
    assert payload["action_requests"][0]["name"] == "bash"
    assert payload["action_requests"][0]["args"] == {"command": "rm -rf /"}
    assert "requires approval" in payload["action_requests"][0]["description"].lower()
    assert payload["review_configs"][0]["allowed_decisions"] == ["approve", "reject"]


def test_security_policy_applies_tool_guard() -> None:
    from octop_harness.config import HarnessAgentConfig

    policy = SecurityPolicy.defaults()
    cfg = HarnessAgentConfig(name="demo", workspace_dir="/tmp/demo")
    applied = policy.apply_to_config(cfg)
    assert applied.tool_guard_enabled is True
    assert applied.tool_guard_mode == "warn"


def test_tool_guard_round_trip_dict() -> None:
    policy = SecurityPolicy.from_dict({"tool_guard": {"enabled": False, "mode": "warn"}})
    assert policy.tool_guard.enabled is False
    assert policy.tool_guard.mode == "warn"
    restored = SecurityPolicy.from_dict(policy.to_dict())
    assert restored.tool_guard.enabled is False
    assert restored.tool_guard.mode == "warn"


def test_list_guard_rule_catalog_nonempty() -> None:
    from octop_harness.security.tool_guard import list_guard_rule_catalog

    catalog = list_guard_rule_catalog()
    assert len(catalog) >= 10
    first = catalog[0]
    assert "id" in first
    assert "patterns" in first
    assert "severity" in first
