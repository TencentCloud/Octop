"""Tests for runtime slash interception on HarnessAgentManager.stream."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from octop_harness.config import HarnessAgentConfig, ModelConfig, ProviderConfig
from octop_harness.manager import HarnessAgentManager
from octop_harness.request import ChatRequest


def _config(tmp_path: Path) -> HarnessAgentConfig:
    return HarnessAgentConfig(
        workspace_dir=tmp_path,
        default_model="openai/gpt-4o",
        providers=[
            ProviderConfig(
                id="openai",
                base_url="https://api.openai.com/v1",
                api_key="sk-test",
                models=[
                    ModelConfig(id="gpt-4o", enabled=True),
                    ModelConfig(id="gpt-4o-mini", enabled=True),
                ],
            )
        ],
    )


@pytest.fixture
def manager_with_agent(tmp_path: Path) -> HarnessAgentManager:
    with patch("octop_harness.agent.deepagents.create_deep_agent", return_value=MagicMock()):
        mgr = HarnessAgentManager()
        mgr.create_agent(_config(tmp_path), init_workspace=False)
        return mgr


async def test_stream_intercepts_model_slash(manager_with_agent: HarnessAgentManager) -> None:
    agent_id = next(iter(manager_with_agent._registry.agent_ids()))
    entry = manager_with_agent._registry.get(agent_id)
    entry.agent._protocol = MagicMock()
    entry.agent._protocol.stream = MagicMock()

    chunks = [
        c
        async for c in manager_with_agent.stream(
            agent_id,
            ChatRequest(messages="/model openai/gpt-4o-mini", thread_id="t1"),
        )
    ]
    assert chunks[-1] == {"type": "done"}
    text = "".join(c.get("content", "") for c in chunks if c.get("type") == "token")
    assert "gpt-4o-mini" in text
    assert entry.agent.get_thread_model("t1") == "openai/gpt-4o-mini"
    entry.agent._protocol.stream.assert_not_called()
