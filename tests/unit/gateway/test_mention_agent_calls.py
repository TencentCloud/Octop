"""Team peer discovery after harness-agent dropped apply_mentions intercept."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from harness_agent.config import HarnessAgentConfig, ModelConfig, ProviderConfig
from harness_agent.manager import HarnessAgentManager


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
