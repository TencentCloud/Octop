"""Team member dispatch must opt in to the member's permitted MCP tools."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from langchain_core.tools import StructuredTool
from octop_harness.mcp import filter_tools_for_mcp_servers, resolve_active_mcp_servers
from octop_harness.registry import AgentRegistry
from octop_harness.teams.team_manager import TeamManager as HarnessTeamManager

from octop.infra.agents.manager import AgentManager
from octop.infra.agents.teams import TeamJobTracker
from octop.infra.agents.teams.team_manager import TeamManager
from octop.infra.connectors.service import ConnectorService
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.services import RepoBundle
from octop.infra.gateway.threads import ThreadRegistry


class _ConnectorService(ConnectorService):
    """Synthetic account catalog; use the real permission validation policy."""

    def __init__(self) -> None:
        self.allowed = {1: ["bound", "caller-default"], 2: ["owner-private"]}
        self.loaded_for: list[int] = []

    def list_active_mcp_server_names(self, user_id: int) -> list[str]:
        return self.allowed.get(user_id, [])

    def list_default_open_mcp_server_names(self, user_id: int) -> list[str]:
        return ["caller-default"] if user_id == 1 else ["owner-private"]

    def custom_harness_configs(self, user_id: int) -> dict[str, Any]:
        self.loaded_for.append(user_id)
        return {
            name: {
                "transport": "streamable_http",
                "url": f"https://{name}.invalid/mcp",
                "headers": {"Authorization": f"Bearer test-user-{user_id}"},
            }
            for name in self.list_active_mcp_server_names(user_id)
        }


class _ToolAgent:
    """Runtime boundary without building a model or making network calls."""

    def __init__(self) -> None:
        self._mcp_tools: list[Any] = []
        self._mcp_tool_name_set: frozenset[str] = frozenset()
        self.config = SimpleNamespace(mcp_server_configs={}, language="zh")

    def append_mcp_tools(self, tools: list[Any]) -> None:
        self._mcp_tools.extend(tools)
        self._mcp_tool_name_set = frozenset(tool.name for tool in self._mcp_tools)

    def replace_mcp_tools(self, tools: list[Any]) -> None:
        self._mcp_tools = list(tools)
        self._mcp_tool_name_set = frozenset(tool.name for tool in tools)

    async def aget_history(self, *_args: Any, **_kwargs: Any) -> list[Any]:
        return []


@pytest.fixture
def dispatch_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[SimpleNamespace]:
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))
    db = SqlitePool(tmp_path / "octop.db")
    run_migrations(db)
    repos = RepoBundle.from_pool(db)
    repos.user_repo.create(username="caller", password_hash="h", role="user")
    repos.user_repo.create(username="member-owner", password_hash="h", role="user")
    repos.agent_repo.create(agent_id="host", user_id=1, name="Host", kind="team")
    repos.agent_repo.create(
        agent_id="member",
        user_id=2,
        name="Member",
        mcp_servers=json.dumps(["bound"]),
    )
    repos.agent_repo.set_shared("member", True)
    repos.agent_repo.create(agent_id="colleague", user_id=1, name="Colleague")
    service = _ConnectorService()
    agents = {name: _ToolAgent() for name in ("host", "member", "colleague")}
    manager = object.__new__(AgentManager)
    manager._repos = repos
    manager._connector_svc = service
    manager._connector_user_override = {}
    manager._paths = SimpleNamespace(root=tmp_path)
    manager._mcp_tool_cache = {}
    manager._mcp_tool_cache_locks = {}
    manager._mcp_tool_cache_guard = asyncio.Lock()
    manager._team_jobs = TeamJobTracker()
    manager._harness_manager = SimpleNamespace(
        get_agent=lambda agent_id: SimpleNamespace(agent=agents[agent_id])
    )
    manager._teams = SimpleNamespace(member_ids=lambda _host: ["member", "colleague"])
    registry = ThreadRegistry(session_repo=repos.session_repo, thread_repo=repos.thread_repo)
    team = TeamManager(agent_manager=manager, thread_registry=registry, user_repo=repos.user_repo)
    harness = HarnessTeamManager(AgentRegistry())
    harness.bind_peer_session(prepare=team.prepare_peer_session)

    async def load_tools(configs: dict[str, Any]) -> list[Any]:
        return [
            StructuredTool.from_function(
                func=lambda: "available", name=f"{name}_read", description="Test MCP tool"
            )
            for name in configs
        ]

    loader = AsyncMock(side_effect=load_tools)
    monkeypatch.setattr("octop_harness.mcp.aload_mcp_tools", loader)
    yield SimpleNamespace(
        repos=repos,
        manager=manager,
        service=service,
        agents=agents,
        registry=registry,
        team=team,
        harness=harness,
        loader=loader,
    )
    db.close()


async def _dispatch(env: SimpleNamespace, **overrides: Any) -> Any:
    kwargs = {
        "from_agent_id": "host",
        "to_agent_id": "member",
        "message": "Read the assigned data",
        "user_id": 1,
        "source": "ask_agent",
        "source_thread_id": "room",
        "source_session_key": "host:dashboard:1:dm",
        "job_id": "job-1",
    }
    kwargs.update(overrides)
    return await env.harness._build_peer_request(**kwargs)


def _visible_mcp_tools(env: SimpleNamespace, request: Any) -> list[str]:
    config = request.to_runnable_config()["configurable"]
    agent = env.agents[request.agent_id]
    active = resolve_active_mcp_servers(
        mcp_use_default=bool(config.get("mcp_use_default")),
        mcp_servers=config.get("mcp_servers"),
        default_servers=["caller-default", "owner-private"],
    )
    visible = filter_tools_for_mcp_servers(
        agent._mcp_tools,
        mcp_tool_names=agent._mcp_tool_name_set,
        server_names=frozenset(agent.config.mcp_server_configs),
        active_servers=active,
    )
    return [tool.name for tool in visible]


@pytest.mark.asyncio
async def test_group_dispatch_exposes_member_binding_with_callers_credentials(
    dispatch_env: SimpleNamespace,
) -> None:
    request = await _dispatch(dispatch_env)
    assert _visible_mcp_tools(dispatch_env, request) == ["bound_read"]
    config = request.to_runnable_config()["configurable"]
    assert config["mcp_servers"] == ["bound"]
    assert not config.get("mcp_use_default")
    assert dispatch_env.service.loaded_for == [1]
    assert dispatch_env.loader.await_args.args[0]["bound"]["headers"] == {
        "Authorization": "Bearer test-user-1"
    }
    assert dispatch_env.agents["host"]._mcp_tools == []
    assert config["peer_invoke_mode"] == "sync"
    assert config["team_peers"] == ["colleague"]
    assert request.agent_id == "member"
    assert request.user == "1"
    assert request.thread_id == "room~member"
    assert config["session_key"] == "member:dashboard:1:team:room"
    assert dispatch_env.manager._team_jobs.is_busy("host", "member")


@pytest.mark.asyncio
async def test_async_expert_dispatch_uses_members_own_binding(
    dispatch_env: SimpleNamespace,
) -> None:
    request = await _dispatch(dispatch_env, from_agent_id="colleague")
    assert _visible_mcp_tools(dispatch_env, request) == ["bound_read"]
    config = request.to_runnable_config()["configurable"]
    assert config["mcp_servers"] == ["bound"]
    assert "team_peers" not in config
    assert config["session_key"] == "member:dashboard:1:team:room"


@pytest.mark.asyncio
@pytest.mark.parametrize("binding", [[], ["owner-private"], ["bound", "owner-private"]])
async def test_missing_or_unavailable_binding_does_not_enable_other_defaults(
    dispatch_env: SimpleNamespace,
    binding: list[str],
) -> None:
    dispatch_env.repos.agent_repo.update_config("member", mcp_servers=json.dumps(binding))
    request = await _dispatch(dispatch_env)
    config = request.to_runnable_config()["configurable"]
    assert not config.get("mcp_servers")
    assert not config.get("mcp_use_default")
    assert _visible_mcp_tools(dispatch_env, request) == []
    dispatch_env.loader.assert_not_awaited()
    assert request.thread_id == "room~member"
    assert config["session_key"] == "member:dashboard:1:team:room"
    assert config["peer_invoke_mode"] == "sync"
    assert config["team_peers"] == ["colleague"]
    assert dispatch_env.registry.get_thread("room~member").user_id == 1
    assert dispatch_env.manager._team_jobs.is_busy("host", "member")


@pytest.mark.asyncio
async def test_mcp_load_failure_preserves_member_session_and_dispatch(
    dispatch_env: SimpleNamespace,
) -> None:
    dispatch_env.loader.side_effect = RuntimeError("synthetic MCP unavailable")
    request = await _dispatch(dispatch_env)
    config = request.to_runnable_config()["configurable"]
    assert not config.get("mcp_servers")
    assert not config.get("mcp_use_default")
    assert _visible_mcp_tools(dispatch_env, request) == []
    dispatch_env.loader.assert_awaited_once()
    assert request.agent_id == "member"
    assert request.user == "1"
    assert request.thread_id == "room~member"
    assert config["session_key"] == "member:dashboard:1:team:room"
    assert config["peer_invoke_mode"] == "sync"
    assert config["team_peers"] == ["colleague"]
    assert dispatch_env.registry.get_thread("room~member").user_id == 1
    assert dispatch_env.manager._team_jobs.is_busy("host", "member")


@pytest.mark.asyncio
async def test_team_host_never_receives_mcp_tools(dispatch_env: SimpleNamespace) -> None:
    dispatch_env.repos.agent_repo.update_config("host", mcp_servers=json.dumps(["bound"]))
    request = await _dispatch(dispatch_env, to_agent_id="host")
    config = request.to_runnable_config()["configurable"]
    assert not config.get("mcp_servers")
    assert not config.get("mcp_use_default")
    assert dispatch_env.agents["host"]._mcp_tools == []
    dispatch_env.loader.assert_not_awaited()


@pytest.mark.asyncio
async def test_sync_expert_peer_keeps_existing_mcp_behavior(dispatch_env: SimpleNamespace) -> None:
    request = await _dispatch(dispatch_env, from_agent_id="colleague", job_id=None)
    config = request.to_runnable_config()["configurable"]
    assert not config.get("mcp_servers")
    assert not config.get("mcp_use_default")
    assert _visible_mcp_tools(dispatch_env, request) == []
    dispatch_env.loader.assert_not_awaited()
    assert config["session_key"] == "member:dashboard:1:peer:room"
    assert "peer_invoke_mode" not in config
