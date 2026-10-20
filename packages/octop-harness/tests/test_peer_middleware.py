"""Tests for ``PeerAgentMiddleware``."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from langchain.agents.middleware import ModelRequest, ModelResponse
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from octop_harness.config import HarnessAgentConfig, ProviderConfig
from octop_harness.manager import HarnessAgentManager
from octop_harness.middleware.peer import (
    PeerAgentMiddleware,
    has_agent_at_mention,
    render_peer_prompt,
)
from octop_harness.teams.tools import AskAgentAsyncInput, AskAgentSyncInput


def _config(tmp_path: Path, name: str) -> HarnessAgentConfig:
    return HarnessAgentConfig(
        workspace_dir=tmp_path,
        providers=[
            ProviderConfig(
                id="openai",
                base_url="https://api.openai.com/v1",
                api_key="sk-test",
                models=[],
            )
        ],
        name=name,
    )


def _mgr(tmp_path: Path) -> HarnessAgentManager:
    mock_agent = MagicMock()
    mock_agent.init_workspace.return_value = MagicMock()
    with patch("octop_harness.manager.HarnessAgent", return_value=mock_agent):
        mgr = HarnessAgentManager()
        mgr.create_agent(_config(tmp_path, "main"), agent_id="main", metadata={"user_id": 7})
        mgr.create_agent(
            _config(tmp_path / "b", "data-analyst"),
            agent_id="peer-b",
            metadata={
                "user_id": 7,
                "description": "charts",
                "quick_prompts": [
                    {
                        "title": {"en": "Plot a trend", "zh": "画趋势图"},
                        "description": {
                            "en": "Turn a table into a chart",
                            "zh": "把表格画成图",
                        },
                    }
                ],
            },
        )
    return mgr


def _request(*, system: str = "base", user: str = "@data-analyst summarize") -> ModelRequest:
    return ModelRequest(
        model=MagicMock(),
        tools=[],
        system_message=SystemMessage(content=system),
        messages=[HumanMessage(content=user)],
        tool_choice=None,
        response_format=None,
        state={"messages": [HumanMessage(content=user)]},
        runtime=MagicMock(),
    )


def test_has_agent_at_mention_skips_files() -> None:
    assert has_agent_at_mention("@data-analyst summarize")
    assert has_agent_at_mention("please ask @bob")
    assert has_agent_at_mention("请 @分析师 看一下")
    assert not has_agent_at_mention("summarize this")
    assert not has_agent_at_mention("see @src/main.py")
    assert not has_agent_at_mention("open @file.txt")


def test_middleware_mounts_peer_tools(tmp_path: Path) -> None:
    mw = PeerAgentMiddleware(_mgr(tmp_path).team)
    assert {tool.name for tool in mw.tools} == {"agent_list", "ask_agent"}


def test_wrap_model_call_skips_without_at_mention(tmp_path: Path) -> None:
    mw = PeerAgentMiddleware(_mgr(tmp_path).team, language="en")
    captured: dict[str, ModelRequest] = {}

    def handler(request: ModelRequest) -> ModelResponse:
        captured["request"] = request
        return ModelResponse(result=[AIMessage(content="ok")])

    runtime = {"configurable": {"agent_id": "main", "user": 7}}
    with patch("octop_harness.middleware.peer.runtime_config", return_value=runtime):
        mw.wrap_model_call(_request(user="summarize this"), handler)

    applied = captured["request"]
    assert applied.system_prompt == "base"


def test_wrap_model_call_skips_file_at_refs(tmp_path: Path) -> None:
    mw = PeerAgentMiddleware(_mgr(tmp_path).team, language="en")
    captured: dict[str, ModelRequest] = {}

    def handler(request: ModelRequest) -> ModelResponse:
        captured["request"] = request
        return ModelResponse(result=[AIMessage(content="ok")])

    runtime = {"configurable": {"agent_id": "main", "user": 7}}
    with patch("octop_harness.middleware.peer.runtime_config", return_value=runtime):
        mw.wrap_model_call(_request(user="see @src/main.py"), handler)

    assert captured["request"].system_prompt == "base"


def test_wrap_model_call_injects_roster_and_at_hint(tmp_path: Path) -> None:
    mw = PeerAgentMiddleware(_mgr(tmp_path).team, language="en")
    captured: dict[str, ModelRequest] = {}

    def handler(request: ModelRequest) -> ModelResponse:
        captured["request"] = request
        return ModelResponse(result=[AIMessage(content="ok")])

    runtime = {"configurable": {"agent_id": "main", "user": 7}}
    with patch("octop_harness.middleware.peer.runtime_config", return_value=runtime):
        mw.wrap_model_call(_request(), handler)

    prompt = str(captured["request"].system_prompt)
    assert prompt.startswith("base\n\n")
    assert prompt.index("base") < prompt.index("data-analyst")
    assert prompt.strip().splitlines()[-1] == ("Use ask_agent with mode=sync and wait for the peer's answer.")
    assert "charts" in prompt
    assert "Plot a trend" in prompt
    assert "Turn a table into a chart" in prompt
    assert "ask_agent" in prompt
    assert "task" in prompt
    assert "subagent" in prompt
    assert "other experts" in prompt.lower() or "Other experts" in prompt


def test_wrap_model_call_zh_mentions_at_usage(tmp_path: Path) -> None:
    mw = PeerAgentMiddleware(_mgr(tmp_path).team, language="zh")
    captured: dict[str, Any] = {}

    def handler(request: ModelRequest) -> ModelResponse:
        captured["prompt"] = request.system_prompt
        return ModelResponse(result=[AIMessage(content="ok")])

    runtime = {"configurable": {"agent_id": "main", "user": "7"}}
    with patch("octop_harness.middleware.peer.runtime_config", return_value=runtime):
        mw.wrap_model_call(_request(), handler)

    prompt = str(captured["prompt"])
    assert "ask_agent" in prompt
    assert "@" in prompt
    assert "data-analyst" in prompt
    assert "task" in prompt
    assert "subagent" in prompt
    assert "画趋势图" in prompt
    assert "指引卡片" in prompt


def test_render_peer_prompt_empty_roster() -> None:
    text = render_peer_prompt(
        [],
        language="en",
        display_name=lambda entry: entry.agent_id,
        async_enabled=False,
    )
    assert "No other experts" in text
    assert "mode=sync" in text
    assert "task" in text
    assert "subagent" in text


def test_render_peer_prompt_skips_empty_cards() -> None:
    entry = MagicMock()
    entry.agent_id = "peer-b"
    entry.metadata = {"description": "charts", "quick_prompts": []}
    text = render_peer_prompt(
        [entry],
        language="zh",
        display_name=lambda _: "分析师",
        async_enabled=False,
    )
    assert "分析师" in text
    assert "charts" in text
    assert "指引卡片" not in text


def test_wrap_model_call_appends_without_flattening_blocks(tmp_path: Path) -> None:
    mw = PeerAgentMiddleware(_mgr(tmp_path).team, language="en")
    captured: dict[str, ModelRequest] = {}

    def handler(request: ModelRequest) -> ModelResponse:
        captured["request"] = request
        return ModelResponse(result=[AIMessage(content="ok")])

    existing = SystemMessage(
        content_blocks=[
            {"type": "text", "text": "base"},
            {"type": "text", "text": "skills block"},
        ]
    )
    req = ModelRequest(
        model=MagicMock(),
        tools=[],
        system_message=existing,
        messages=[HumanMessage(content="@data-analyst summarize")],
        tool_choice=None,
        response_format=None,
        state={"messages": [HumanMessage(content="@data-analyst summarize")]},
        runtime=MagicMock(),
    )
    runtime = {"configurable": {"agent_id": "main", "user": 7}}
    with patch("octop_harness.middleware.peer.runtime_config", return_value=runtime):
        mw.wrap_model_call(req, handler)

    blocks = captured["request"].system_message.content_blocks
    texts = [str(b.get("text", "")) for b in blocks if isinstance(b, dict)]
    assert texts[0] == "base"
    assert "skills block" in texts[1]
    assert any("data-analyst" in t for t in texts)
    assert len(texts) >= 3


def test_wrap_model_call_uses_enriched_peer_cards(tmp_path: Path) -> None:
    mgr = _mgr(tmp_path)

    def enrich(entry: Any) -> None:
        entry.metadata["quick_prompts"] = [{"title": {"en": "Hot card"}}]

    mgr.team.bind_peer_enrich(enrich)
    mw = PeerAgentMiddleware(mgr.team, language="en")
    captured: dict[str, ModelRequest] = {}

    def handler(request: ModelRequest) -> ModelResponse:
        captured["request"] = request
        return ModelResponse(result=[AIMessage(content="ok")])

    runtime = {"configurable": {"agent_id": "main", "user": 7}}
    with patch("octop_harness.middleware.peer.runtime_config", return_value=runtime):
        mw.wrap_model_call(_request(), handler)

    prompt = str(captured["request"].system_prompt)
    assert "Hot card" in prompt
    assert "Plot a trend" not in prompt


def test_middleware_mounts_async_schema(tmp_path: Path) -> None:
    mw = PeerAgentMiddleware(_mgr(tmp_path).team, peer_invoke_mode="async")
    ask = next(tool for tool in mw.tools if tool.name == "ask_agent")
    assert ask.args_schema is AskAgentAsyncInput


def test_middleware_swaps_ask_agent_schema_without_prompt_on_plain_turn(tmp_path: Path) -> None:
    mw = PeerAgentMiddleware(_mgr(tmp_path).team, peer_invoke_mode="async")
    captured: dict[str, ModelRequest] = {}

    def handler(request: ModelRequest) -> ModelResponse:
        captured["request"] = request
        return ModelResponse(result=[AIMessage(content="ok")])

    req = ModelRequest(
        model=MagicMock(),
        tools=list(mw.tools),
        system_message=SystemMessage(content="base"),
        messages=[HumanMessage(content="summarize this")],
        tool_choice=None,
        response_format=None,
        state={"messages": [HumanMessage(content="summarize this")]},
        runtime=MagicMock(),
    )
    runtime = {"configurable": {"agent_id": "main", "user": 7, "peer_invoke_mode": "sync"}}
    with patch("octop_harness.middleware.peer.runtime_config", return_value=runtime):
        mw.wrap_model_call(req, handler)

    applied = captured["request"]
    assert applied.system_prompt == "base"
    ask = next(tool for tool in applied.tools if tool.name == "ask_agent")
    assert ask.args_schema is AskAgentSyncInput


def test_middleware_does_not_escalate_sync_schema(tmp_path: Path) -> None:
    mw = PeerAgentMiddleware(_mgr(tmp_path).team, peer_invoke_mode="sync")
    captured: dict[str, ModelRequest] = {}

    def handler(request: ModelRequest) -> ModelResponse:
        captured["request"] = request
        return ModelResponse(result=[AIMessage(content="ok")])

    req = ModelRequest(
        model=MagicMock(),
        tools=list(mw.tools),
        system_message=SystemMessage(content="base"),
        messages=[HumanMessage(content="summarize this")],
        tool_choice=None,
        response_format=None,
        state={"messages": [HumanMessage(content="summarize this")]},
        runtime=MagicMock(),
    )
    runtime = {"configurable": {"agent_id": "main", "user": 7, "peer_invoke_mode": "async"}}
    with patch("octop_harness.middleware.peer.runtime_config", return_value=runtime):
        mw.wrap_model_call(req, handler)

    applied = captured["request"]
    assert applied.system_prompt == "base"
    ask = next(tool for tool in applied.tools if tool.name == "ask_agent")
    assert ask.args_schema is AskAgentSyncInput
    assert ask is next(tool for tool in mw.tools if tool.name == "ask_agent")


def test_middleware_request_team_peers_intersects_roster(tmp_path: Path) -> None:
    from dataclasses import replace

    mock_agent = MagicMock()
    mock_agent.init_workspace.return_value = MagicMock()
    with patch("octop_harness.manager.HarnessAgent", return_value=mock_agent):
        scoped = HarnessAgentManager()
        scoped.create_agent(
            replace(_config(tmp_path, "main"), team_peers=("data-analyst", "researcher")),
            agent_id="main",
            metadata={"user_id": 7},
        )
        scoped.create_agent(_config(tmp_path / "b", "data-analyst"), agent_id="peer-b", metadata={"user_id": 7})
        scoped.create_agent(_config(tmp_path / "c", "researcher"), agent_id="peer-c", metadata={"user_id": 7})

    mw = PeerAgentMiddleware(scoped.team, language="en")
    captured: dict[str, ModelRequest] = {}

    def handler(request: ModelRequest) -> ModelResponse:
        captured["request"] = request
        return ModelResponse(result=[AIMessage(content="ok")])

    runtime = {
        "configurable": {
            "agent_id": "main",
            "user": 7,
            "team_peers": ["peer-c"],
        }
    }
    with patch("octop_harness.middleware.peer.runtime_config", return_value=runtime):
        mw.wrap_model_call(_request(), handler)

    prompt = str(captured["request"].system_prompt)
    assert "researcher" in prompt
    assert "data-analyst" not in prompt
