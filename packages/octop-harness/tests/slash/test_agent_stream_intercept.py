"""Tests for runtime slash interception on HarnessAgent.stream."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from octop_harness.agent import HarnessAgent
from octop_harness.config import HarnessAgentConfig, ModelConfig, ProviderConfig
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
                models=[ModelConfig(id="gpt-4o", enabled=True), ModelConfig(id="gpt-4o-mini", enabled=True)],
            )
        ],
    )


@pytest.fixture
def agent(tmp_path: Path) -> HarnessAgent:
    with patch("octop_harness.agent.deepagents.create_deep_agent", return_value=MagicMock()):
        return HarnessAgent(_config(tmp_path))


async def test_agent_stream_intercepts_model_slash(agent: HarnessAgent) -> None:
    agent._protocol = MagicMock()
    agent._protocol.stream = AsyncMock()

    chunks = [
        c
        async for c in agent.stream(
            ChatRequest(messages="/model openai/gpt-4o-mini", thread_id="t1"),
        )
    ]
    assert chunks[-1] == {"type": "done"}
    text = "".join(c.get("content", "") for c in chunks if c.get("type") == "token")
    assert "gpt-4o-mini" in text
    assert agent.get_thread_model("t1") == "openai/gpt-4o-mini"
    agent._protocol.stream.assert_not_called()
