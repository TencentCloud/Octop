"""Tests for AgentProfile."""

from __future__ import annotations

from octop_harness.cli.agents.profile import AgentProfile


def test_profile_basic_creation() -> None:
    p = AgentProfile(name="main", provider="deepseek", model="deepseek-chat")
    assert p.name == "main"
    assert p.provider == "deepseek"
    assert p.model == "deepseek-chat"
    assert p.backend is None
    assert p.workspace_dir is None


def test_profile_resolve_inherits_missing_fields() -> None:
    p = AgentProfile(name="code", provider="anthropic", model="claude-sonnet-4")
    top_level = {
        "providers": {
            "anthropic": {
                "base_url": "https://api.anthropic.com/v1",
                "api_key": "k",
                "models": [{"id": "claude-sonnet-4"}],
            },
            "deepseek": {
                "base_url": "https://api.deepseek.com/v1",
                "api_key": "k2",
                "models": [{"id": "deepseek-chat"}],
            },
        },
        "backend": "local_shell",
        "workspace_dir": "/home/u/.octop-harness/workspace",
        "default_model": "deepseek/deepseek-chat",
    }
    resolved = p.resolve(top_level)
    assert resolved["default_model"] == "anthropic/claude-sonnet-4"
    assert resolved["workspace_dir"] == "/home/u/.octop-harness/workspace"
    assert "anthropic" in resolved["providers"]
    assert "deepseek" in resolved["providers"]


def test_profile_resolve_overrides_workspace_dir() -> None:
    p = AgentProfile(name="code", provider="openai", model="gpt-4o", workspace_dir="/tmp/ws")
    top_level = {
        "providers": {"openai": {"base_url": "http://x", "api_key": "k", "models": [{"id": "gpt-4o"}]}},
        "workspace_dir": "/home/u/.octop-harness/workspace",
        "default_model": "openai/gpt-4o",
    }
    resolved = p.resolve(top_level)
    assert resolved["workspace_dir"] == "/tmp/ws"


def test_profile_resolve_overrides_backend() -> None:
    p = AgentProfile(name="ops", provider="deepseek", model="deepseek-chat", backend={"type": "cos", "bucket": "b"})
    top_level = {
        "providers": {"deepseek": {"base_url": "http://x", "api_key": "k", "models": [{"id": "deepseek-chat"}]}},
        "workspace_dir": "/ws",
        "default_model": "deepseek/deepseek-chat",
    }
    resolved = p.resolve(top_level)
    assert resolved["backend"] == {"type": "cos", "bucket": "b"}


def test_profile_from_dict() -> None:
    data = {"provider": "openai", "model": "gpt-4o", "workspace_dir": "/tmp/ws"}
    p = AgentProfile.from_dict("test", data)
    assert p.name == "test"
    assert p.provider == "openai"
    assert p.model == "gpt-4o"
    assert p.workspace_dir == "/tmp/ws"
    assert p.backend is None


def test_profile_to_dict() -> None:
    p = AgentProfile(name="x", provider="openai", model="gpt-4o", workspace_dir="/tmp/ws")
    d = p.to_dict()
    assert d == {"provider": "openai", "model": "gpt-4o", "workspace_dir": "/tmp/ws"}
    assert "backend" not in d


def test_profile_resolve_provider_only_picks_first_model() -> None:
    """When only provider is set (no model), resolve picks first model from that provider."""
    p = AgentProfile(name="auto", provider="openai")
    top_level = {
        "providers": {
            "openai": {"base_url": "http://x", "api_key": "k", "models": [{"id": "gpt-4o"}, {"id": "gpt-4o-mini"}]}
        },
        "workspace_dir": "/ws",
        "default_model": "openai/gpt-4o-mini",
    }
    resolved = p.resolve(top_level)
    assert resolved["default_model"] == "openai/gpt-4o"
