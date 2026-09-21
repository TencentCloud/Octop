"""Team peer discovery after harness-agent dropped apply_mentions intercept."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from harness_agent.config import HarnessAgentConfig, ModelConfig, ProviderConfig
from harness_agent.manager import HarnessAgentManager
from harness_agent.teams.tools import AskAgentInput, build_team_tools


def _config(tmp_path: Path, *, name: str = "agent") -> HarnessAgentConfig:
    return HarnessAgentConfig(
        workspace_dir=tmp_path,
        providers=[
            ProviderConfig(
                id="openai",
                base_url="https://api.openai.com/v1",
                api_key="sk-test",
                models=[ModelConfig(id="gpt-4", enabled=True)],
            )
        ],
        default_model="openai/gpt-4",
        name=name,
    )


def _mgr(tmp_path: Path) -> HarnessAgentManager:
    mock_agent = MagicMock()
    mock_agent.init_workspace.return_value = MagicMock()
    mock_agent.call = AsyncMock(return_value={"messages": [{"role": "assistant", "content": "ok"}]})
    with patch("harness_agent.manager.HarnessAgent", return_value=mock_agent):
        mgr = HarnessAgentManager()
        mgr.create_agent(
            _config(tmp_path, name="main"),
            agent_id="main",
            metadata={"user_id": 1},
        )
        mgr.create_agent(
            _config(tmp_path / "b", name="researcher"),
            agent_id="agent-b",
            metadata={"user_id": 1},
        )
    return mgr


def test_list_peers_excludes_self(tmp_path: Path) -> None:
    mgr = _mgr(tmp_path)
    peers = mgr.team.list_peers(1, exclude_agent_id="main")
    assert [e.agent_id for e in peers] == ["agent-b"]


def test_resolve_peer_matches_at_name(tmp_path: Path) -> None:
    mgr = _mgr(tmp_path)
    entry = mgr.team.resolve_peer(1, "@researcher", exclude_agent_id="main")
    assert entry is not None
    assert entry.agent_id == "agent-b"


def test_resolve_peer_matches_octop_display_name(tmp_path: Path) -> None:
    mock_agent = MagicMock()
    mock_agent.init_workspace.return_value = MagicMock()
    mock_agent.call = AsyncMock(return_value={"messages": [{"role": "assistant", "content": "ok"}]})
    with patch("harness_agent.manager.HarnessAgent", return_value=mock_agent):
        mgr = HarnessAgentManager()
        mgr.create_agent(
            _config(tmp_path, name="agent_host01"),
            agent_id="host01",
            metadata={"user_id": 1},
        )
        mgr.create_agent(
            _config(tmp_path / "c", name="agent_clin01"),
            agent_id="clin01",
            metadata={"user_id": 1, "display_name": "临床辅助专家"},
        )
    entry = mgr.team.resolve_peer(1, "临床辅助专家", exclude_agent_id="host01")
    assert entry is not None
    assert entry.agent_id == "clin01"
    assert mgr.team.peer_display_name(entry) == "临床辅助专家"


def test_ask_agent_schema_uses_expert_field() -> None:
    props = AskAgentInput.model_json_schema()["properties"]
    assert "expert" in props
    assert "agent" not in props
    assert "agent" not in props["expert"]["description"].lower()


@pytest.mark.asyncio
async def test_ask_agent_accepts_expert_or_legacy_agent_key(tmp_path: Path) -> None:
    mgr = _mgr(tmp_path)
    tools = {tool.name: tool for tool in build_team_tools(mgr.team)}
    runtime = {"configurable": {"agent_id": "main", "user": 1}}
    with patch("harness_agent.teams.tools.get_config", return_value=runtime):
        by_expert = json.loads(
            await tools["ask_agent"].ainvoke({"expert": "researcher", "message": "hi"})
        )
        by_legacy = json.loads(
            await tools["ask_agent"].ainvoke({"agent": "researcher", "message": "hi"})
        )
        missing = json.loads(
            await tools["ask_agent"].ainvoke({"expert": "没有这个人", "message": "hi"})
        )
    assert by_expert.get("name") == "researcher"
    assert by_legacy.get("name") == "researcher"
    assert missing == {"error": "expert not found: 没有这个人"}
