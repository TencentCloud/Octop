"""Tests for octop_harness.security.models."""

from __future__ import annotations

import logging

import pytest

from octop_harness.config import HarnessAgentConfig
from octop_harness.security.models import SecurityPolicy


def test_defaults_disables_hitl() -> None:
    policy = SecurityPolicy.defaults()
    assert policy.resolve_interrupt_on() is None


def test_defaults_tool_guard_warn_only() -> None:
    policy = SecurityPolicy.defaults()
    assert policy.tool_guard.enabled is True
    assert policy.tool_guard.mode == "warn"


def test_disabled_hitl_returns_none() -> None:
    policy = SecurityPolicy.from_dict({"hitl": {"enabled": False}})
    assert policy.resolve_interrupt_on() is None


def test_apply_to_config_sets_pii_and_permissions() -> None:
    policy = SecurityPolicy.defaults()
    cfg = HarnessAgentConfig(
        name="demo",
        workspace_dir="/tmp/demo",
        backend={"type": "filesystem", "virtual_mode": True},
    )
    applied = policy.apply_to_config(cfg)
    assert applied.interrupt_on is None
    assert applied.permissions is not None
    assert applied.pii_enabled is True


def test_apply_to_config_keeps_permissions_for_local_shell_guard() -> None:
    """Execution backends keep permissions on config for FilesystemGuardMiddleware.

    deepagents still must not receive them (see agent kwargs gating).
    """
    policy = SecurityPolicy.defaults()
    cfg = HarnessAgentConfig(
        name="demo",
        workspace_dir="/tmp/demo",
        backend={"type": "local_shell", "virtual_mode": True},
    )
    applied = policy.apply_to_config(cfg)
    assert applied.permissions is not None


def test_apply_to_config_does_not_instantiate_backend(caplog: pytest.LogCaptureFixture) -> None:
    """Applying a policy must not construct a backend just to test shell capability."""
    policy = SecurityPolicy.defaults()
    cfg = HarnessAgentConfig(name="demo", workspace_dir="/tmp/demo", backend=None)

    with caplog.at_level(logging.WARNING, logger="octop_harness.backends"):
        applied = policy.apply_to_config(cfg)

    # backend=None is treated as execution-capable (safe default); permissions stay
    # for FilesystemGuardMiddleware and are not passed to deepagents.
    assert applied.permissions is not None
    assert not any("rooted at '/'" in record.message for record in caplog.records)


def test_round_trip_dict() -> None:
    original = SecurityPolicy.defaults()
    restored = SecurityPolicy.from_dict(original.to_dict())
    assert restored.to_dict() == original.to_dict()


def test_merge_overrides_hitl_tools() -> None:
    base = SecurityPolicy.defaults()
    merged = SecurityPolicy.merge(base, {"hitl": {"enabled": True, "tools": ["bash"]}})
    interrupt_on = merged.resolve_interrupt_on()
    assert interrupt_on is not None
    assert set(interrupt_on) == {"bash"}


def test_hitl_skips_interrupt_when_filesystem_denies_path() -> None:
    """Sensitive-path deny must hard-fail — HITL must not ask for approval first."""
    policy = SecurityPolicy.from_dict(
        {
            "hitl": {
                "enabled": True,
                "tools": ["write_file", "edit_file", "bash"],
            },
            "filesystem": {
                "enabled": True,
                "rules": [
                    {
                        "operations": ["read", "write"],
                        "paths": ["/etc/**"],
                        "mode": "deny",
                    }
                ],
            },
        }
    )
    interrupt_on = policy.resolve_interrupt_on()
    assert interrupt_on is not None
    write_cfg = interrupt_on["write_file"]
    assert "when" in write_cfg
    when = write_cfg["when"]

    denied = when(
        type(
            "Req",
            (),
            {"tool_call": {"name": "write_file", "args": {"file_path": "/etc/passwd"}}},
        )()
    )
    allowed = when(
        type(
            "Req",
            (),
            {"tool_call": {"name": "write_file", "args": {"file_path": "/tmp/ok.txt"}}},
        )()
    )
    assert denied is False
    assert allowed is True
    # Shell tools stay unconditional (no filesystem path arg).
    assert "when" not in interrupt_on["bash"]


def test_hitl_without_filesystem_has_no_when_predicate() -> None:
    policy = SecurityPolicy.from_dict(
        {
            "hitl": {"enabled": True, "tools": ["write_file"]},
            "filesystem": {"enabled": False, "rules": []},
        }
    )
    interrupt_on = policy.resolve_interrupt_on()
    assert interrupt_on is not None
    assert "when" not in interrupt_on["write_file"]
