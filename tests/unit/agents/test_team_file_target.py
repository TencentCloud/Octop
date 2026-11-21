"""Team dispatch uses the host workspace for file tools."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from deepagents.backends.protocol import ExecuteResponse, SandboxBackendProtocol

from octop.infra.agents.acp.team_workspace_mcp import (
    TeamWorkspaceScope,
    handle_team_workspace_mcp,
)
from octop.infra.agents.acp.turn import attach_managed_turn
from octop.infra.agents.middleware.team_file_target import TeamFileTargetMiddleware
from octop.infra.agents.teams.file_target import (
    CAPABILITIES_KEY,
    DIR_KEY,
    EXECUTE_KEY,
    HOST_KEY,
    activate_file_target,
    file_target_opt_out,
    install_file_redirect,
    reset_file_target,
    workspace_directory,
    workspace_relative,
)
from octop.infra.agents.teams.team_manager import TeamManager
from octop.infra.bridge.local_workspace import (
    clear_local_workspace_state,
    register_peer_target,
    remember_thread_target,
    replace_peer_target,
)


class _Disk:
    def __init__(self, label: str) -> None:
        self.label = label

    def read(self, path: str) -> str:
        return f"{self.label}:{path}"

    async def aread(self, path: str) -> str:
        return self.read(path)


class _Shell(SandboxBackendProtocol):
    def execute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        return ExecuteResponse(output=command, exit_code=0)

    async def aexecute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        return self.execute(command, timeout=timeout)


def test_redirect_hits_the_host_backend_only_while_active() -> None:
    member = _Disk("member")
    host = _Disk("host")
    install_file_redirect(member)
    assert member.read("a") == "member:a"
    token = activate_file_target(host)
    try:
        assert member.read("a") == "host:a"
    finally:
        reset_file_target(token)
    assert member.read("a") == "member:a"
    install_file_redirect(member)
    assert member.read("b") == "member:b"


def test_opt_out_requires_an_explicit_ask() -> None:
    assert file_target_opt_out("请用你自己的工作区写报告")
    assert file_target_opt_out("Please use your own file tools")
    assert not file_target_opt_out("不要用自己的工作区")
    assert not file_target_opt_out("写到主持人目录")


def test_workspace_directory_prefers_the_visible_path() -> None:
    agent = SimpleNamespace(
        _agent_visible_workspace_dir=lambda: SimpleNamespace(as_posix=lambda: "/host/ws"),
        config=SimpleNamespace(workspace_dir="/other"),
    )
    assert workspace_directory(agent) == "/host/ws"
    assert (
        workspace_directory(SimpleNamespace(config=SimpleNamespace(workspace_dir=object()))) == ""
    )


def _request(name: str, args: dict[str, Any]) -> MagicMock:
    req = MagicMock()
    req.tool_call = {"name": name, "id": "tc", "args": args}
    return req


def _middleware(member: _Disk, host: Any) -> TeamFileTargetMiddleware:
    agents = {"child": SimpleNamespace(backend=member), "host": host}

    def lookup(agent_id: str) -> Any:
        return agents[agent_id]

    return TeamFileTargetMiddleware(agent_id="child", lookup=lookup)


def test_guard_keeps_a_relative_path_on_a_file_target_turn() -> None:
    from octop_harness.middleware.filesystem_guard import FilesystemGuardMiddleware

    guard = FilesystemGuardMiddleware(workspace_dir="/member/ws")
    stamped = {"configurable": {HOST_KEY: "host", DIR_KEY: "/host/ws"}}
    request = SimpleNamespace(
        tool_call={"name": "read_file", "id": "1", "args": {"file_path": "notes.md"}}
    )
    with patch(
        "octop.infra.agents.teams.file_target_guard.get_config",
        return_value=stamped,
    ):
        updated = guard._resolve_relative_paths(request)
    assert updated.tool_call["args"]["file_path"] == "notes.md"

    plain = SimpleNamespace(
        tool_call={"name": "read_file", "id": "2", "args": {"file_path": "notes.md"}}
    )
    with patch(
        "octop.infra.agents.teams.file_target_guard.get_config",
        return_value={"configurable": {}},
    ):
        rewritten = guard._resolve_relative_paths(plain)
    assert rewritten.tool_call["args"]["file_path"] == "/member/ws/notes.md"


def test_runner_write_is_denied_and_not_reported_as_the_selected_directory() -> None:
    from octop_harness.acp.client import ACPHostedClient
    from octop_harness.acp.permissions import ACPPermissionAdapter

    adapter = ACPPermissionAdapter(cwd="/tmp/runner")
    stamped = {"configurable": {HOST_KEY: "host", DIR_KEY: "/host/ws", "locale": "en"}}
    write = {"kind": "edit", "title": "Write", "rawInput": {"path": "notes.md"}}
    own = {"kind": "edit", "title": "octop-team-workspace write_file"}
    with patch(
        "octop.infra.agents.teams.file_target_guard.get_config",
        return_value=stamped,
    ):
        assert adapter.is_hard_blocked(write) is True
        assert adapter.is_hard_blocked(own) is False
        event = ACPHostedClient._tool_event_from_state(
            SimpleNamespace(),
            SimpleNamespace(
                tool_call_id="c1",
                title="Write",
                kind="edit",
                status="completed",
                content=[{"type": "text", "text": "wrote notes.md"}],
                raw_output=None,
            ),
        )
    assert event is not None
    assert event["status"] == "failed"
    assert "selected directory" in event["output"]
    with patch(
        "octop.infra.agents.teams.file_target_guard.get_config",
        return_value={"configurable": {}},
    ):
        assert adapter.is_hard_blocked(write) is False


def test_workspace_relative_resolves_against_the_target_directory() -> None:
    assert workspace_relative("notes.md", "/host/ws") == "notes.md"
    assert workspace_relative("/host/ws/a.md", "/host/ws") == "a.md"
    assert workspace_relative("/notes.md", "/host/ws") == "notes.md"
    assert workspace_relative("/member/ws/notes.md", "/host/ws") == "member/ws/notes.md"


class _Workspace:
    def __init__(self) -> None:
        self.paths: list[str] = []

    async def aread_text(self, path: str, *, limit: int = 10_000_000) -> str:
        del limit
        self.paths.append(path)
        return "from-host"


@pytest.mark.asyncio
async def test_file_tool_reads_the_host_workspace_not_the_member_path() -> None:
    member = _Disk("member")
    workspace = _Workspace()
    host = SimpleNamespace(backend=object(), workspace=workspace)
    child = SimpleNamespace(backend=member, config=SimpleNamespace(workspace_dir="/member/ws"))
    mw = TeamFileTargetMiddleware(
        agent_id="child",
        lookup=lambda agent_id: child if agent_id == "child" else host,
    )

    async def handler(request: Any) -> str:
        return str(await request.tool.ainvoke(request.tool_call))

    request = _request("read_file", {"file_path": "notes.md"})
    request.override = lambda **kwargs: SimpleNamespace(
        tool=kwargs["tool"], tool_call=kwargs.get("tool_call", request.tool_call)
    )
    config = {"configurable": {HOST_KEY: "host", DIR_KEY: "/host/ws", EXECUTE_KEY: "1"}}
    with patch(
        "octop.infra.agents.middleware.team_file_target.get_config",
        return_value=config,
    ):
        result = await mw.awrap_tool_call(request, handler)
    assert result == "from-host"
    assert workspace.paths == ["notes.md"]


@pytest.mark.asyncio
async def test_execute_uses_the_host_shell_and_skips_the_member_tool() -> None:
    member = _Disk("member")
    host = SimpleNamespace(backend=_Shell(), workspace=object())
    mw = _middleware(member, host)

    async def handler(request: Any) -> str:
        return str(await request.tool.ainvoke(request.tool_call))

    config = {"configurable": {HOST_KEY: "host", DIR_KEY: "/host/ws", EXECUTE_KEY: "1"}}
    with patch(
        "octop.infra.agents.middleware.team_file_target.get_config",
        return_value=config,
    ):
        request = _request("execute", {"command": "pwd"})
        request.override = lambda **kwargs: SimpleNamespace(
            tool=kwargs["tool"], tool_call=kwargs.get("tool_call", request.tool_call)
        )
        result = await mw.awrap_tool_call(request, handler)
    assert result == "pwd\n[exit code 0]"


def test_execute_is_hidden_and_file_tools_name_the_host_directory() -> None:
    mw = _middleware(_Disk("member"), SimpleNamespace(backend=object(), workspace=object()))

    class _Tool:
        def __init__(self, name: str, description: str = "read a file") -> None:
            self.name = name
            self.description = description

        def model_copy(self, *, update: dict[str, str]) -> _Tool:
            return _Tool(self.name, update["description"])

    class _Req:
        def __init__(self) -> None:
            self.tools: list[Any] = [_Tool("execute"), _Tool("read_file"), _Tool("ask_agent")]

        def override(self, *, tools: list[Any]) -> _Req:
            nxt = _Req()
            nxt.tools = tools
            return nxt

    config = {"configurable": {HOST_KEY: "host", DIR_KEY: "/host/ws", EXECUTE_KEY: "0"}}
    with patch(
        "octop.infra.agents.middleware.team_file_target.get_config",
        return_value=config,
    ):
        updated = mw._prepare_tools(_Req())
    names = [tool.name for tool in updated.tools]
    assert names == ["read_file", "ask_agent"]
    assert "read a file" in updated.tools[0].description
    assert "/host/ws" in updated.tools[0].description
    assert updated.tools[1].description == "read a file"


@pytest.mark.asyncio
async def test_send_file_is_bound_to_the_host_workspace() -> None:
    member = _Disk("member")
    workspace = object()
    host = SimpleNamespace(backend=_Disk("host"), workspace=workspace)
    mw = _middleware(member, host)
    seen: list[Any] = []

    async def handler(request: Any) -> str:
        seen.append(request.tool)
        return "sent"

    request = _request("send_file_to_user", {"file_path": "a.md"})
    request.override = lambda **kwargs: SimpleNamespace(
        tool=kwargs["tool"], tool_call=request.tool_call
    )
    config = {"configurable": {HOST_KEY: "host", DIR_KEY: "/host/ws", EXECUTE_KEY: "0"}}
    with patch(
        "octop.infra.agents.middleware.team_file_target.get_config",
        return_value=config,
    ):
        assert await mw.awrap_tool_call(request, handler) == "sent"
    assert seen[0].name == "send_file_to_user"
    assert seen[0].workspace is workspace


@pytest.mark.asyncio
async def test_bind_stamps_the_host_directory_unless_the_user_opts_out() -> None:
    clear_local_workspace_state()
    host = SimpleNamespace(
        config=SimpleNamespace(workspace_dir="/host/ws"),
        backend=object(),
    )

    class _Registry:
        def get_thread(self, thread_id: str) -> Any:
            assert thread_id == "room"
            return SimpleNamespace(agent_id="host")

    class _Agents:
        def get_row(self, agent_id: str) -> SimpleNamespace:
            kind = "team" if agent_id == "host" else "expert"
            return SimpleNamespace(kind=kind, agent_id=agent_id)

        def get_agent(self, agent_id: str) -> Any:
            assert agent_id == "host"
            return host

    team = SimpleNamespace(
        _thread_registry=_Registry(),
        _agent_manager=_Agents(),
        _team_room_id=lambda thread_id, speaker: TeamManager._team_room_id(
            team, thread_id, speaker
        ),
        _last_room_user_text=_async_text(""),
        _locale_for=lambda _user_id: "zh",
        _payload_user_id=lambda _payload, _room: 1,
    )
    payload: dict[str, Any] = {
        "thread_id": "room~child",
        "messages": [SimpleNamespace(content="整理报告")],
        "configurable": {},
    }
    await TeamManager._bind_team_file_target(team, payload, "child", "room~child")
    cfg = payload["configurable"]
    assert cfg[HOST_KEY] == "host"
    assert cfg[DIR_KEY] == "/host/ws"
    assert cfg[EXECUTE_KEY] == "0"
    assert cfg[CAPABILITIES_KEY] == {"file": True, "execute": False}
    assert "/host/ws" in cfg["octop_team_dispatch_briefing"]

    opted = {
        "thread_id": "room~child",
        "messages": [SimpleNamespace(content="用你自己的工作区")],
        "configurable": {},
    }
    await TeamManager._bind_team_file_target(team, opted, "child", "room~child")
    assert HOST_KEY not in opted["configurable"]


@pytest.mark.asyncio
async def test_bridge_file_tool_calls_the_peer_target_not_the_member() -> None:
    clear_local_workspace_state()
    seen: list[dict[str, Any]] = []
    target = SimpleNamespace(
        bridge_file_target=True,
        token="tok",
        directory="/data",
        execute=True,
    )

    async def call_text(op: str, args: dict[str, Any]) -> str:
        seen.append({"op": op, "args": args})
        return f"{op}:{args['file_path']}"

    target.call_text = call_text
    register_peer_target("tok", session=object(), directory="/data", execute=True)
    replace_peer_target("tok", target)
    child = SimpleNamespace(
        backend=_Disk("member"),
        config=SimpleNamespace(workspace_dir="/member/ws"),
    )
    mw = TeamFileTargetMiddleware(
        agent_id="child",
        lookup=lambda agent_id: child if agent_id == "child" else SimpleNamespace(),
    )

    async def handler(request: Any) -> str:
        return str(await request.tool.ainvoke(request.tool_call))

    request = _request("read_file", {"file_path": "notes.md"})
    request.override = lambda **kwargs: SimpleNamespace(
        tool=kwargs["tool"], tool_call=kwargs.get("tool_call", request.tool_call)
    )
    config = {
        "configurable": {
            "octop_bridge_file_target": "tok",
            DIR_KEY: "/data",
            EXECUTE_KEY: "1",
        }
    }
    with patch(
        "octop.infra.agents.middleware.team_file_target.get_config",
        return_value=config,
    ):
        result = await mw.awrap_tool_call(request, handler)
    assert result == "read_file:notes.md"
    assert seen == [{"op": "read_file", "args": {"file_path": "notes.md"}}]
    clear_local_workspace_state()


@pytest.mark.asyncio
async def test_bind_uses_the_bridge_directory_for_a_cloud_local_room() -> None:
    clear_local_workspace_state()
    target = register_peer_target("tok", session=object(), directory="/data", execute=True)
    remember_thread_target("room", target.token)

    class _Registry:
        def get_thread(self, thread_id: str) -> Any:
            return SimpleNamespace(agent_id="host")

    class _Agents:
        def get_row(self, agent_id: str) -> SimpleNamespace:
            kind = "team" if agent_id == "host" else "expert"
            return SimpleNamespace(kind=kind, agent_id=agent_id)

        def get_agent(self, agent_id: str) -> Any:
            raise AssertionError("bridge target must not open the host workspace")

    team = SimpleNamespace(
        _thread_registry=_Registry(),
        _agent_manager=_Agents(),
        _team_room_id=lambda thread_id, speaker: TeamManager._team_room_id(
            team, thread_id, speaker
        ),
        _last_room_user_text=_async_text(""),
        _locale_for=lambda _user_id: "zh",
        _payload_user_id=lambda _payload, _room: 1,
    )
    payload: dict[str, Any] = {
        "thread_id": "room~child",
        "messages": [SimpleNamespace(content="写到本地目录")],
        "configurable": {},
    }
    await TeamManager._bind_team_file_target(team, payload, "child", "room~child")
    cfg = payload["configurable"]
    assert cfg["octop_bridge_file_target"] == "tok"
    assert cfg[DIR_KEY] == "/data"
    assert HOST_KEY not in cfg
    assert "/data" in cfg["octop_team_dispatch_briefing"]
    clear_local_workspace_state()


def _async_text(text: str) -> Any:
    async def _read(_room: str, _host: str) -> str:
        return text

    return _read


@pytest.mark.asyncio
async def test_managed_turn_adds_one_host_workspace_mcp() -> None:
    class _Manager:
        _config = SimpleNamespace(
            bind_host="127.0.0.1",
            port=8000,
            tls=SimpleNamespace(enabled=False, cert_file="", key_file=""),
        )

        def get_row(self, agent_id: str) -> SimpleNamespace:
            return SimpleNamespace(kind="managed")

    request: dict[str, Any] = {
        "user": "7",
        "configurable": {
            "locale": "zh",
            HOST_KEY: "host",
            DIR_KEY: "/host/ws",
            EXECUTE_KEY: "0",
        },
    }
    await attach_managed_turn(_Manager(), "child", request)
    specs = request["configurable"]["acp_mcp_servers"]
    assert "octop-team-workspace" in specs
    assert "/api/internal/mcp/team-workspace?token=" in specs["octop-team-workspace"]["url"]
    note = request["configurable"]["acp_prompt_note"]
    assert "octop-files" not in specs
    assert "octop-team-workspace" in note
    assert "/host/ws" in note
    assert "send_file_to_user" in note
    assert "不要调用 execute" in note


@pytest.mark.asyncio
async def test_workspace_mcp_reads_the_host_and_omits_execute_without_a_shell() -> None:
    class _Workspace:
        async def aread_text(self, path: str, *, limit: int = 10_000_000) -> str:
            assert path == "notes.md"
            return "hello\nworld"

        async def als(self, path: str = ".") -> Any:
            return None

    scope = TeamWorkspaceScope(host_agent_id="host", directory="/host/ws", execute=False)
    listed = await handle_team_workspace_mcp(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        scope=scope,
        workspace=_Workspace(),
        backend=object(),
    )
    names = [tool["name"] for tool in listed["result"]["tools"]]
    assert "execute" not in names
    assert "read_file" in names
    assert "send_file_to_user" in names
    assert "/host/ws" in listed["result"]["tools"][0]["description"]
    read = await handle_team_workspace_mcp(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "read_file", "arguments": {"file_path": "notes.md"}},
        },
        scope=scope,
        workspace=_Workspace(),
        backend=object(),
    )
    assert read["result"]["content"][0]["text"] == "hello\nworld"
    assert read["result"]["isError"] is False


@pytest.mark.asyncio
async def test_workspace_mcp_sends_a_file_from_the_target_directory(tmp_path: Path) -> None:
    report = tmp_path / "report.txt"
    report.write_text("hello", encoding="utf-8")

    class _Files:
        def materialize_local(self, path: str) -> Path:
            return tmp_path / path

    scope = TeamWorkspaceScope(host_agent_id="host", directory=str(tmp_path), execute=False)
    sent = await handle_team_workspace_mcp(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "send_file_to_user", "arguments": {"file_path": "report.txt"}},
        },
        scope=scope,
        workspace=_Files(),
        backend=object(),
    )
    text = sent["result"]["content"][0]["text"]
    assert sent["result"]["isError"] is False
    assert "octop_delivery" in text
    assert "report.txt" in text
