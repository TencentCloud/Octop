"""Tests for CliAgentManager."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from octop_harness.cli.agents.manager import CliAgentManager
from octop_harness.cli.agents.profile import AgentProfile


@pytest.fixture
def config_file(tmp_path: Path) -> Path:
    path = tmp_path / "config.json"
    data = {
        "providers": {"deepseek": {"base_url": "http://x", "api_key": "k", "models": [{"id": "deepseek-chat"}]}},
        "default_model": "deepseek/deepseek-chat",
        "workspace_dir": "/ws",
        "default_agent": "main",
        "agents": {
            "main": {"provider": "deepseek", "model": "deepseek-chat"},
        },
    }
    path.write_text(json.dumps(data))
    return path


def test_list_agents(config_file: Path) -> None:
    mgr = CliAgentManager(config_file)
    agents = mgr.list()
    assert len(agents) == 1
    assert agents[0].name == "main"


def test_get_existing(config_file: Path) -> None:
    mgr = CliAgentManager(config_file)
    p = mgr.get("main")
    assert p is not None
    assert p.provider == "deepseek"


def test_get_missing(config_file: Path) -> None:
    mgr = CliAgentManager(config_file)
    assert mgr.get("nonexistent") is None


def test_create_agent(config_file: Path) -> None:
    mgr = CliAgentManager(config_file)
    profile = AgentProfile(name="code", provider="deepseek", model="deepseek-chat", workspace_dir="/tmp/ws")
    mgr.create(profile)
    data = json.loads(config_file.read_text())
    assert "code" in data["agents"]
    assert data["agents"]["code"]["workspace_dir"] == "/tmp/ws"
    assert len(mgr.list()) == 2


def test_create_duplicate_raises(config_file: Path) -> None:
    mgr = CliAgentManager(config_file)
    with pytest.raises(ValueError, match="already exists"):
        mgr.create(AgentProfile(name="main", provider="x", model="y"))


def test_remove_agent(config_file: Path) -> None:
    mgr = CliAgentManager(config_file)
    mgr.create(AgentProfile(name="code", provider="deepseek", model="deepseek-chat"))
    mgr.remove("code")
    assert mgr.get("code") is None
    data = json.loads(config_file.read_text())
    assert "code" not in data["agents"]


def test_remove_main_raises(config_file: Path) -> None:
    mgr = CliAgentManager(config_file)
    with pytest.raises(ValueError, match="cannot remove"):
        mgr.remove("main")


def test_set_default(config_file: Path) -> None:
    mgr = CliAgentManager(config_file)
    mgr.create(AgentProfile(name="code", provider="deepseek", model="deepseek-chat"))
    mgr.set_default("code")
    data = json.loads(config_file.read_text())
    assert data["default_agent"] == "code"


def test_set_default_missing_raises(config_file: Path) -> None:
    mgr = CliAgentManager(config_file)
    with pytest.raises(ValueError, match="not found"):
        mgr.set_default("nope")


def test_resolve_agent(config_file: Path) -> None:
    mgr = CliAgentManager(config_file)
    resolved = mgr.resolve("main")
    assert resolved["default_model"] == "deepseek/deepseek-chat"
    assert resolved["workspace_dir"] == "/ws"


def test_default_agent_name(config_file: Path) -> None:
    mgr = CliAgentManager(config_file)
    assert mgr.default_agent_name == "main"


def test_implicit_main_when_no_agents_key(tmp_path: Path) -> None:
    """Backward compat: config without agents key still works."""
    path = tmp_path / "config.json"
    data = {
        "providers": {"openai": {"base_url": "http://x", "api_key": "k", "models": [{"id": "gpt-4o"}]}},
        "default_model": "openai/gpt-4o",
        "workspace_dir": "/ws",
    }
    path.write_text(json.dumps(data))
    mgr = CliAgentManager(path)
    agents = mgr.list()
    assert len(agents) == 1
    assert agents[0].name == "main"
    resolved = mgr.resolve("main")
    assert resolved["default_model"] == "openai/gpt-4o"
