# tests/test_peer_agent.py
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from octop_harness.config import HarnessAgentConfig, ProviderConfig
from octop_harness.manager import HarnessAgentManager
from octop_harness.teams.inbox import InboxMessage
from octop_harness.teams.processor import ReplyEvent, default_compose_followup
from octop_harness.teams.util import derive_peer_thread_id


def _config(tmp_path: Path, *, name: str = "peer-a", team_peers: tuple[str, ...] | None = None) -> HarnessAgentConfig:
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
        team_peers=team_peers,
    )


def _mgr(tmp_path: Path, *, team_peers: tuple[str, ...] | None = None) -> HarnessAgentManager:
    mock_agent = MagicMock()
    mock_agent.init_workspace.return_value = MagicMock()
    mock_agent.call = AsyncMock(return_value={"messages": [{"role": "assistant", "content": "ok"}]})
    with patch("octop_harness.manager.HarnessAgent", return_value=mock_agent):
        mgr = HarnessAgentManager()
        mgr.create_agent(
            _config(tmp_path, name="main", team_peers=team_peers),
            agent_id="main",
            metadata={"user_id": 7},
        )
        mgr.create_agent(
            _config(tmp_path / "b", name="data-analyst"),
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
                        "prompt": {"en": "do not leak", "zh": "不要泄漏"},
                    }
                ],
            },
        )
        mgr.create_agent(
            _config(tmp_path / "c", name="researcher"),
            agent_id="peer-c",
            metadata={"user_id": 7},
        )
    return mgr


def test_team_tools_exposes_agent_list_and_ask_agent(tmp_path: Path) -> None:
    mgr = _mgr(tmp_path)
    assert {tool.name for tool in mgr.team.team_tools()} == {"agent_list", "ask_agent"}


def test_list_peers_defaults_to_same_user(tmp_path: Path) -> None:
    mgr = _mgr(tmp_path)
    peers = mgr.team.list_peers(7, exclude_agent_id="main")
    names = {mgr.team.peer_display_name(e) for e in peers}
    assert names == {"data-analyst", "researcher"}


def test_list_peers_honors_team_peers_allowlist(tmp_path: Path) -> None:
    mgr = _mgr(tmp_path, team_peers=("data-analyst",))
    peers = mgr.team.list_peers(7, exclude_agent_id="main")
    assert [mgr.team.peer_display_name(e) for e in peers] == ["data-analyst"]


def test_resolve_peer_matches_approximate_name(tmp_path: Path) -> None:
    mgr = _mgr(tmp_path)
    entry = mgr.team.resolve_peer(7, "@Data-Analyst", exclude_agent_id="main")
    assert entry is not None
    assert entry.agent_id == "peer-b"


def test_resolve_peer_matches_metadata_display_name(tmp_path: Path) -> None:
    mock_agent = MagicMock()
    mock_agent.init_workspace.return_value = MagicMock()
    mock_agent.call = AsyncMock(return_value={"messages": [{"role": "assistant", "content": "ok"}]})
    with patch("octop_harness.manager.HarnessAgent", return_value=mock_agent):
        mgr = HarnessAgentManager()
        mgr.create_agent(
            _config(tmp_path, name="agent_clin01"),
            agent_id="clin01",
            metadata={"user_id": 7, "display_name": "临床辅助专家"},
        )
        mgr.create_agent(
            _config(tmp_path / "h", name="agent_host"),
            agent_id="host",
            metadata={"user_id": 7},
        )
    entry = mgr.team.resolve_peer(7, "临床辅助专家", exclude_agent_id="host")
    assert entry is not None
    assert entry.agent_id == "clin01"
    assert mgr.team.peer_display_name(entry) == "临床辅助专家"


@pytest.mark.asyncio
async def test_prepare_request_leaves_at_mention_in_user_text(tmp_path: Path) -> None:
    mgr = _mgr(tmp_path)
    prepared = await mgr._prepare_request(
        "main",
        {
            "messages": [{"role": "user", "content": "@data-analyst hello"}],
            "user": "7",
            "configurable": {"target_agent_ids": ["peer-b"]},
        },
    )
    assert prepared.messages == [{"role": "user", "content": "@data-analyst hello"}]
    assert prepared.agent_id == "main"


@pytest.mark.asyncio
async def test_call_peer_forwards_only_message_text(tmp_path: Path) -> None:
    mock_agent = MagicMock()
    mock_agent.init_workspace.return_value = MagicMock()
    mock_agent.call = AsyncMock(return_value={"messages": [{"role": "assistant", "content": "ok"}]})
    with patch("octop_harness.manager.HarnessAgent", return_value=mock_agent):
        mgr = HarnessAgentManager()
        mgr.create_agent(_config(tmp_path), agent_id="main", metadata={"user_id": 7})
        mgr.create_agent(_config(tmp_path / "b"), agent_id="peer-b", metadata={"user_id": 7})

    await mgr.team.call_peer(
        from_agent_id="main",
        to_agent_id="peer-b",
        message="only this",
        user_id=7,
    )
    req = mock_agent.call.await_args.args[0]
    assert req.messages == "only this"
    assert req.agent_id == "peer-b"
    assert req.source == "ask_agent"


@pytest.mark.asyncio
async def test_submit_peer_requires_team(tmp_path: Path) -> None:
    mock_agent = MagicMock()
    mock_agent.init_workspace.return_value = MagicMock()
    with patch("octop_harness.manager.HarnessAgent", return_value=mock_agent):
        mgr = HarnessAgentManager()
        mgr.create_agent(_config(tmp_path), agent_id="main", metadata={"user_id": 1})
        mgr.create_agent(_config(tmp_path / "b"), agent_id="child", metadata={"user_id": 1})

    assert mgr.team.enabled is False
    with pytest.raises(RuntimeError):
        mgr.team.submit_peer(
            from_agent_id="main",
            to_agent_id="child",
            message="x",
            user_id=1,
            source_thread_id="T",
        )


@pytest.mark.asyncio
async def test_submit_peer_enqueues_and_pushes(tmp_path: Path) -> None:
    events: list[ReplyEvent] = []

    class _Proc:
        def compose_followup(self, msg: InboxMessage, *, result_text, error_text) -> str:
            return default_compose_followup(msg, result_text=result_text, error_text=error_text)

        async def on_reply(self, event: ReplyEvent) -> None:
            events.append(event)

    mock_agent = MagicMock()
    mock_agent.init_workspace.return_value = MagicMock()
    mock_agent.call = AsyncMock(return_value={"messages": [{"role": "assistant", "content": "reply"}]})

    with patch("octop_harness.manager.HarnessAgent", return_value=mock_agent):
        mgr = HarnessAgentManager(team_processor=_Proc())
        mgr.create_agent(_config(tmp_path), agent_id="main", metadata={"user_id": 1})
        mgr.create_agent(_config(tmp_path / "b"), agent_id="child", metadata={"user_id": 1})

    assert mgr.team.enabled is True
    result = mgr.team.submit_peer(
        from_agent_id="main",
        to_agent_id="child",
        message="long task",
        user_id=1,
        source_thread_id="T-main",
        metadata={"session_key": "sk"},
    )
    assert result.mode == "background"
    assert result.job_id

    await asyncio.sleep(0.05)
    assert len(events) == 1
    assert events[0].status == "done"
    assert events[0].metadata.get("session_key") == "sk"


def test_list_peers_runs_peer_enrich(tmp_path: Path) -> None:
    mgr = _mgr(tmp_path)

    def enrich(entry: Any) -> None:
        entry.metadata["description"] = "hot"

    mgr.team.bind_peer_enrich(enrich)
    peers = mgr.team.list_peers(7, exclude_agent_id="main")
    analyst = next(p for p in peers if p.agent_id == "peer-b")
    assert analyst.metadata["description"] == "hot"


@pytest.mark.asyncio
async def test_agent_list_includes_guidance_cards(tmp_path: Path) -> None:
    mgr = _mgr(tmp_path)
    tools = {tool.name: tool for tool in mgr.team.team_tools()}
    runtime = {"configurable": {"agent_id": "main", "user": 7}}
    with patch("octop_harness.teams.tools.get_config", return_value=runtime):
        raw = await tools["agent_list"].ainvoke({})
    payload = json.loads(raw)
    analyst = next(item for item in payload if item["agent_id"] == "peer-b")
    assert analyst["description"] == "charts"
    assert analyst["guidance_cards"] == [
        {"title": "画趋势图", "description": "把表格画成图"},
    ]
    dumped = json.dumps(analyst)
    assert "do not leak" not in dumped
    assert "不要泄漏" not in dumped
    researcher = next(item for item in payload if item["agent_id"] == "peer-c")
    assert "guidance_cards" not in researcher


def test_derive_peer_thread_id_appends_and_replaces() -> None:
    assert derive_peer_thread_id("thr_abc", "peer-b") == "thr_abc~peer-b"
    assert derive_peer_thread_id("thr_abc~peer-b", "peer-b") == "thr_abc~peer-b"
    assert derive_peer_thread_id("thr_abc~peer-b", "peer-c") == "thr_abc~peer-b~peer-c"


@pytest.mark.asyncio
async def test_call_peer_uses_stable_derived_thread_id(tmp_path: Path) -> None:
    mock_agent = MagicMock()
    mock_agent.init_workspace.return_value = MagicMock()
    mock_agent.call = AsyncMock(return_value={"messages": [{"role": "assistant", "content": "ok"}]})
    with patch("octop_harness.manager.HarnessAgent", return_value=mock_agent):
        mgr = HarnessAgentManager()
        mgr.create_agent(_config(tmp_path), agent_id="main", metadata={"user_id": 7})
        mgr.create_agent(_config(tmp_path / "b"), agent_id="peer-b", metadata={"user_id": 7})

    first = await mgr.team.call_peer(
        from_agent_id="main",
        to_agent_id="peer-b",
        message="one",
        user_id=7,
        source_thread_id="thr_src",
        session_key="main:dashboard:7:dm",
    )
    second = await mgr.team.call_peer(
        from_agent_id="main",
        to_agent_id="peer-b",
        message="two",
        user_id=7,
        source_thread_id="thr_src",
        session_key="main:dashboard:7:dm",
    )
    req = mock_agent.call.await_args_list[0].args[0]
    assert first.thread_id == "thr_src~peer-b"
    assert second.thread_id == first.thread_id
    assert req.thread_id == "thr_src~peer-b"
    assert req.configurable["session_key"] == "main:dashboard:7:dm"


@pytest.mark.asyncio
async def test_call_peer_prepare_hook_can_rewrite_session(tmp_path: Path) -> None:
    from octop_harness.teams.util import PeerCall, PeerSession

    mock_agent = MagicMock()
    mock_agent.init_workspace.return_value = MagicMock()
    mock_agent.call = AsyncMock(return_value={"messages": [{"role": "assistant", "content": "ok"}]})
    with patch("octop_harness.manager.HarnessAgent", return_value=mock_agent):
        mgr = HarnessAgentManager()
        mgr.create_agent(_config(tmp_path), agent_id="main", metadata={"user_id": 7})
        mgr.create_agent(_config(tmp_path / "b"), agent_id="peer-b", metadata={"user_id": 7})

    async def prepare(call: PeerCall) -> PeerSession:
        assert call.to_agent_id == "peer-b"
        return PeerSession(thread_id="thr_src~peer-b", session_key="peer-b:dashboard:7:dm")

    mgr.team.bind_peer_session(prepare=prepare)
    await mgr.team.call_peer(
        from_agent_id="main",
        to_agent_id="peer-b",
        message="one",
        user_id=7,
        source_thread_id="thr_src",
        session_key="main:dashboard:7:dm",
    )
    req = mock_agent.call.await_args.args[0]
    assert req.configurable["session_key"] == "peer-b:dashboard:7:dm"
    assert req.thread_id == "thr_src~peer-b"


@pytest.mark.asyncio
async def test_call_peer_prepare_hook_can_rewrite_message(tmp_path: Path) -> None:
    from octop_harness.teams.util import PeerCall, PeerSession

    mock_agent = MagicMock()
    mock_agent.init_workspace.return_value = MagicMock()
    mock_agent.call = AsyncMock(return_value={"messages": [{"role": "assistant", "content": "ok"}]})
    with patch("octop_harness.manager.HarnessAgent", return_value=mock_agent):
        mgr = HarnessAgentManager()
        mgr.create_agent(_config(tmp_path), agent_id="main", metadata={"user_id": 7})
        mgr.create_agent(_config(tmp_path / "b"), agent_id="peer-b", metadata={"user_id": 7})

    async def prepare(call: PeerCall) -> PeerSession:
        return PeerSession(message=f"history\n---\n{call.message}")

    mgr.team.bind_peer_session(prepare=prepare)
    await mgr.team.call_peer(
        from_agent_id="main",
        to_agent_id="peer-b",
        message="task",
        user_id=7,
        source_thread_id="thr_src",
    )
    req = mock_agent.call.await_args.args[0]
    assert req.messages == "history\n---\ntask"


def test_list_peers_honors_explicit_allowlist(tmp_path: Path) -> None:
    mgr = _mgr(tmp_path)
    peers = mgr.team.list_peers(7, exclude_agent_id="main", team_peers=["peer-c"])
    assert [entry.agent_id for entry in peers] == ["peer-c"]


@pytest.mark.asyncio
async def test_ask_agent_request_override_forces_sync(tmp_path: Path) -> None:
    mgr = _mgr(tmp_path)
    tools = {tool.name: tool for tool in mgr.team.team_tools()}
    runtime = {
        "configurable": {
            "agent_id": "main",
            "user": 7,
            "peer_invoke_mode": "sync",
        }
    }
    with patch("octop_harness.teams.tools.get_config", return_value=runtime):
        raw = await tools["ask_agent"].ainvoke({"agent": "peer-b", "message": "hi", "mode": "background"})
    payload = json.loads(raw)
    assert payload["mode"] == "sync"
    assert payload.get("response") == "ok"


@pytest.mark.asyncio
async def test_ask_agent_uses_caller_config_async(tmp_path: Path) -> None:
    from dataclasses import replace

    from octop_harness.teams.tools import build_team_tools

    class _Proc:
        def compose_followup(self, msg: InboxMessage, *, result_text, error_text) -> str:
            return "ok"

        async def on_reply(self, event: ReplyEvent) -> None:
            return None

    mock_agent = MagicMock()
    mock_agent.init_workspace.return_value = MagicMock()
    mock_agent.call = AsyncMock(return_value={"messages": [{"role": "assistant", "content": "ok"}]})
    with patch("octop_harness.manager.HarnessAgent", return_value=mock_agent):
        mgr = HarnessAgentManager(team_processor=_Proc())
        mgr.create_agent(
            replace(_config(tmp_path, name="main"), peer_invoke_mode="async"),
            agent_id="main",
            metadata={"user_id": 7},
        )
        mgr.create_agent(_config(tmp_path / "b"), agent_id="peer-b", metadata={"user_id": 7})

    tools = {tool.name: tool for tool in build_team_tools(mgr.team)}
    runtime = {"configurable": {"agent_id": "main", "user": 7}}
    with patch("octop_harness.teams.tools.get_config", return_value=runtime):
        raw = await tools["ask_agent"].ainvoke({"agent": "peer-b", "message": "hi", "mode": "sync"})
    payload = json.loads(raw)
    assert payload["mode"] == "background"
    assert payload.get("status") == "queued"


@pytest.mark.asyncio
async def test_ask_agent_request_cannot_escalate_sync_agent(tmp_path: Path) -> None:
    from dataclasses import replace

    from octop_harness.teams.tools import build_team_tools

    mock_agent = MagicMock()
    mock_agent.init_workspace.return_value = MagicMock()
    mock_agent.call = AsyncMock(return_value={"messages": [{"role": "assistant", "content": "ok"}]})
    with patch("octop_harness.manager.HarnessAgent", return_value=mock_agent):
        mgr = HarnessAgentManager()
        mgr.create_agent(
            replace(_config(tmp_path, name="main"), peer_invoke_mode="sync"),
            agent_id="main",
            metadata={"user_id": 7},
        )
        mgr.create_agent(_config(tmp_path / "b"), agent_id="peer-b", metadata={"user_id": 7})

    tools = {tool.name: tool for tool in build_team_tools(mgr.team, peer_invoke_mode="sync")}
    runtime = {
        "configurable": {
            "agent_id": "main",
            "user": 7,
            "peer_invoke_mode": "async",
        }
    }
    with patch("octop_harness.teams.tools.get_config", return_value=runtime):
        raw = await tools["ask_agent"].ainvoke({"agent": "peer-b", "message": "hi"})
    payload = json.loads(raw)
    assert payload["mode"] == "sync"
    assert payload.get("response") == "ok"


def test_list_peers_intersects_request_allowlist(tmp_path: Path) -> None:
    mgr = _mgr(tmp_path, team_peers=("data-analyst", "researcher"))
    peers = mgr.team.list_peers(7, exclude_agent_id="main", team_peers=["peer-c"])
    assert [entry.agent_id for entry in peers] == ["peer-c"]
    blocked = mgr.team.list_peers(7, exclude_agent_id="main", team_peers=["missing"])
    assert blocked == []


def test_list_peers_request_config_intersects_and_empty_hides(tmp_path: Path) -> None:
    mgr = _mgr(tmp_path, team_peers=("data-analyst", "researcher"))
    runtime = {"configurable": {"team_peers": ["peer-c"]}}
    with patch("langgraph.config.get_config", return_value=runtime):
        peers = mgr.team.list_peers(7, exclude_agent_id="main")
    assert [entry.agent_id for entry in peers] == ["peer-c"]
    with patch("langgraph.config.get_config", return_value={"configurable": {"team_peers": ""}}):
        assert mgr.team.list_peers(7, exclude_agent_id="main") == []


@pytest.mark.asyncio
async def test_prepare_hook_strips_identity_and_after_sees_rewritten_message(
    tmp_path: Path,
) -> None:
    from octop_harness.teams.util import PeerCall, PeerSession

    mock_agent = MagicMock()
    mock_agent.init_workspace.return_value = MagicMock()
    mock_agent.call = AsyncMock(return_value={"messages": [{"role": "assistant", "content": "ok"}]})
    with patch("octop_harness.manager.HarnessAgent", return_value=mock_agent):
        mgr = HarnessAgentManager()
        mgr.create_agent(_config(tmp_path), agent_id="main", metadata={"user_id": 7})
        mgr.create_agent(_config(tmp_path / "b"), agent_id="peer-b", metadata={"user_id": 7})

    seen: list[str] = []

    async def prepare(call: PeerCall) -> PeerSession:
        return PeerSession(
            message=f"WRAP:{call.message}",
            configurable={
                "agent_id": "spoof",
                "user": "evil",
                "thread_id": "hijack",
                "source": "forged",
                "peer_invoke_mode": "sync",
                "team_peers": ["peer-c"],
            },
        )

    async def after(call: PeerCall, thread_id: str, payload: dict[str, Any]) -> None:
        seen.append(call.message)

    mgr.team.bind_peer_session(prepare=prepare, after=after)
    await mgr.team.call_peer(
        from_agent_id="main",
        to_agent_id="peer-b",
        message="task",
        user_id=7,
        source_thread_id="thr_src",
    )
    req = mock_agent.call.await_args.args[0]
    assert req.messages == "WRAP:task"
    assert req.agent_id == "peer-b"
    assert req.user == "7"
    assert req.source == "ask_agent"
    assert req.configurable is not None
    assert "agent_id" not in req.configurable
    assert "user" not in req.configurable
    assert "thread_id" not in req.configurable
    assert "source" not in req.configurable
    assert req.configurable["peer_invoke_mode"] == "sync"
    assert req.configurable["team_peers"] == ["peer-c"]
    assert seen == ["WRAP:task"]


def test_team_tools_uses_caller_config_schema(tmp_path: Path) -> None:
    from dataclasses import replace

    from octop_harness.teams.tools import AskAgentAsyncInput, AskAgentInput

    mock_agent = MagicMock()
    mock_agent.init_workspace.return_value = MagicMock()
    with patch("octop_harness.manager.HarnessAgent", return_value=mock_agent):
        mgr = HarnessAgentManager()
        mgr.create_agent(
            replace(_config(tmp_path, name="main"), peer_invoke_mode="async"),
            agent_id="main",
            metadata={"user_id": 7},
        )

    both = {tool.name: tool for tool in mgr.team.team_tools()}
    assert both["ask_agent"].args_schema is AskAgentInput
    pinned = {tool.name: tool for tool in mgr.team.team_tools(agent_id="main")}
    assert pinned["ask_agent"].args_schema is AskAgentAsyncInput
