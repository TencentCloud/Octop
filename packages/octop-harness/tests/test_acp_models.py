"""Tests for ACP configuration models."""

from __future__ import annotations

from octop_harness.acp.models import ACPConfig, ACPRunnerConfig, default_acp_runners


def test_default_runners_include_builtins() -> None:
    runners = default_acp_runners()
    assert "opencode" in runners
    assert "codebuddy" in runners
    assert "qwen_code" in runners
    assert runners["opencode"].command == "opencode"
    assert runners["codebuddy"].command == "codebuddy"
    assert runners["codebuddy"].args == ["--acp"]


def test_acp_config_from_dict_merges_defaults() -> None:
    cfg = ACPConfig.from_dict(
        {
            "runners": {
                "opencode": {"enabled": True, "command": "opencode", "args": ["acp"]},
            },
        },
    )
    assert cfg.runners["opencode"].enabled is True
    assert "codex" in cfg.runners


def test_runner_config_roundtrip() -> None:
    raw = {
        "enabled": True,
        "command": "npx",
        "args": ["-y", "pkg"],
        "env": {"FOO": "bar"},
        "trusted": True,
        "tool_parse_mode": "call_detail",
        "stdio_buffer_limit_bytes": 1024,
    }
    runner = ACPRunnerConfig.from_dict(raw)
    assert runner.to_dict() == raw


def test_enabled_runner_names() -> None:
    cfg = ACPConfig.from_dict({"runners": {"custom": {"enabled": True, "command": "x"}}})
    assert cfg.enabled_runner_names() == ["custom"]
