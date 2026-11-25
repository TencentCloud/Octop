"""@mentions on a managed turn become a prompt note and an ask_agent call."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from octop.infra.agents.acp.agents_mcp import handle_agents_mcp
from octop.infra.agents.acp.delegation import AgentScope, delegation_note_for


def test_punctuated_mention_still_names_the_expert() -> None:
    note = delegation_note_for(
        "请@分析师，看一下",
        experts=[("分析师", "财务")],
        subagents=[],
        locale="zh",
    )
    assert note is not None
    assert "ask_agent" in note
    assert "@分析师" in note


def test_expert_mention_asks_the_agent_to_call_ask_agent() -> None:
    note = delegation_note_for(
        "请 @分析师 看一下",
        experts=[("分析师", "财务")],
        subagents=[("分析师", "同名子智能体")],
        locale="zh",
    )
    assert note is not None
    assert "ask_agent" in note
    assert "子智能体" not in note


def test_subagent_mention_asks_for_delegation() -> None:
    note = delegation_note_for(
        "@researcher 查一下",
        experts=[],
        subagents=[("researcher", "查资料")],
        locale="en",
    )
    assert note is not None
    assert "@researcher" in note
    assert "Delegate" in note


@pytest.mark.asyncio
async def test_ask_agent_returns_the_peer_answer() -> None:
    class Team:
        def list_peers(self, user_id: int, *, exclude_agent_id: str | None = None) -> list[Any]:
            return []

        def resolve_peer(
            self, user_id: int, query: str, *, exclude_agent_id: str | None = None
        ) -> Any:
            assert query == "分析师"
            return SimpleNamespace(agent_id="peer1")

        async def call_peer(self, **kwargs: Any) -> Any:
            assert kwargs["to_agent_id"] == "peer1"
            assert kwargs["source_thread_id"] == "thr"
            return SimpleNamespace(name="分析师", response="42")

    scope = AgentScope(user_id=7, from_agent_id="GWN", thread_id="thr", session_key="")
    result = await handle_agents_mcp(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "ask_agent", "arguments": {"expert": "@分析师", "message": "今天"}},
        },
        scope=scope,
        team=Team(),
    )
    assert result["result"]["content"][0]["text"] == "分析师: 42"
    assert result["result"]["isError"] is False


@pytest.mark.asyncio
async def test_managed_turn_attaches_experts_and_stores_the_note() -> None:
    from octop.infra.agents.acp.turn import attach_managed_turn

    class Entry:
        agent_id = "peer1"
        metadata = {"display_name": "分析师", "description": "财务"}
        config = SimpleNamespace(name="分析师")

    class Team:
        def list_peers(self, user_id: int, *, exclude_agent_id: str | None = None) -> list[Entry]:
            return [Entry()]

    class Manager:
        _harness_manager = SimpleNamespace(team=Team())
        _config = SimpleNamespace(
            bind_host="127.0.0.1",
            port=8000,
            tls=SimpleNamespace(enabled=False, cert_file="", key_file=""),
        )
        _connector_svc = SimpleNamespace()

        def get_row(self, agent_id: str) -> SimpleNamespace:
            return SimpleNamespace(kind="managed")

        async def list_subagent_summaries(self, agent_id: str) -> list[dict[str, str]]:
            return [{"slug": "researcher", "description": "查资料"}]

    request: dict[str, Any] = {
        "user": "7",
        "thread_id": "thr",
        "messages": [{"role": "user", "content": "@researcher 看一下"}],
        "configurable": {"locale": "zh"},
    }
    await attach_managed_turn(Manager(), "GWN", request)
    configurable = request["configurable"]
    assert isinstance(configurable, dict)
    specs = configurable["acp_mcp_servers"]
    assert isinstance(specs, dict)
    assert set(specs) == {"octop-agents", "octop-files"}
    assert specs["octop-agents"]["transport"] == "http"
    assert "/api/internal/mcp/agents?token=" in specs["octop-agents"]["url"]
    note = configurable["acp_prompt_note"]
    assert isinstance(note, str)
    assert "@researcher" in note
