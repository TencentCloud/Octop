"""Exercise deferred MCP selection and credentials through the real harness graph."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import StructuredTool
from langgraph.checkpoint.memory import MemorySaver
from octop_harness.agent import HarnessAgent
from octop_harness.config import HarnessAgentConfig
from octop_harness.request import ChatRequest
from pydantic import Field

from octop.infra.agents.manager import AgentManager
from octop.infra.connectors.service import ConnectorService

_SERVERS = ("inventory", "probe", "probe_extra", "broken", "seed")
_TOOL_NAMES = frozenset(f"{server}_read" for server in _SERVERS)
_SEED_CONFIG = {
    "seed": {
        "transport": "streamable_http",
        "url": "https://seed.invalid/mcp",
        "headers": {"Authorization": "test-seed-identity"},
    }
}


class _RecordingModel(BaseChatModel):
    seen: list[list[str]] = Field(default_factory=list)
    bound_names: list[str] = Field(default_factory=list)
    forced_tool: str | None = None
    search_then_call: bool = False
    call_args: dict[str, Any] = Field(default_factory=dict)

    @property
    def _llm_type(self) -> str:
        return "local-mcp-scope-test"

    def bind_tools(self, tools: Any, **_kwargs: Any) -> Any:
        self.bound_names = [
            tool.get("name", "") if isinstance(tool, dict) else tool.name for tool in tools
        ]
        self.seen.append([name for name in self.bound_names if name in _TOOL_NAMES])
        return self

    def _generate(
        self, messages: Any, stop: Any = None, run_manager: Any = None, **kwargs: Any
    ) -> ChatResult:
        args: dict[str, Any] = dict(self.call_args)
        call_id = "scope-call"
        if self.search_then_call:
            last = messages[-1]
            if not isinstance(last, ToolMessage) and "tool_search" in self.bound_names:
                target = "tool_search"
                args = {"query": "probe", "max_results": 1}
                call_id = "search-call"
            elif isinstance(last, ToolMessage) and "Loaded tools:" in str(last.content):
                target = "probe_read"
            else:
                target = None
        else:
            target = self.forced_tool or next(
                (name for name in self.bound_names if name in _TOOL_NAMES), None
            )
        if target and (self.search_then_call or not isinstance(messages[-1], ToolMessage)):
            message = AIMessage(
                content="",
                tool_calls=[{"name": target, "args": args, "id": call_id, "type": "tool_call"}],
            )
        else:
            message = AIMessage(content="Local test finished")
        return ChatResult(generations=[ChatGeneration(message=message)])


class _ModelFactory:
    def __init__(self, model: _RecordingModel) -> None:
        self.model = model

    def provider_configs(self) -> list[Any]:
        return []

    def get_chat_model(self, _ref: str) -> _RecordingModel:
        return self.model

    def get(self, _ref: str, **_kwargs: Any) -> Any:
        return SimpleNamespace(chat_model=self.model)

    def bind_runtime(self, **_kwargs: Any) -> None:
        pass


class _Catalog(ConnectorService):
    """Synthetic account specs, retaining the real explicit permission policy."""

    def __init__(self) -> None:
        self.specs = {
            uid: {
                server: {
                    "transport": "streamable_http",
                    "url": f"https://{server}.invalid/mcp",
                    "headers": {"Authorization": f"test-user-{uid}-v1"},
                }
                for server in _SERVERS
            }
            for uid in (1, 2)
        }

    def list_active_mcp_server_names(self, user_id: int) -> list[str]:
        return list(self.specs.get(user_id, {}))

    def custom_harness_configs(self, user_id: int) -> dict[str, Any]:
        return deepcopy(self.specs.get(user_id, {}))


@pytest.fixture
async def runtime_factory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[Callable[..., SimpleNamespace]]:
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))
    monkeypatch.setattr(HarnessAgent, "_init_logging", lambda _self: None)
    agents: list[HarnessAgent] = []
    executions: list[tuple[str, str]] = []
    loads: list[tuple[str, str]] = []

    class _MCPClient:
        def __init__(self, configs: dict[str, Any], **_kwargs: Any) -> None:
            self.server, self.spec = next(iter(configs.items()))

        async def get_tools(self) -> list[Any]:
            identity = self.spec["headers"]["Authorization"]
            loads.append((self.server, identity))
            if self.server == "broken":
                raise ConnectionError("Synthetic local transport failure")
            server = self.server

            async def read() -> str:
                executions.append((server, identity))
                return identity

            return [
                StructuredTool.from_function(
                    coroutine=read, name=f"{server}_read", description="Local MCP identity probe"
                )
            ]

    monkeypatch.setattr("octop_harness.mcp.MultiServerMCPClient", _MCPClient)

    def make_runtime(
        *,
        initial: dict[str, Any] | None = None,
        checkpointer: Any = False,
        interrupt_on: dict[str, Any] | None = None,
        default_servers: list[str] | None = None,
        defer_mcp_tools: bool = False,
    ) -> SimpleNamespace:
        model = _RecordingModel()
        config = HarnessAgentConfig(
            name="mcp-scope-test",
            workspace_dir=tmp_path / f"workspace-{len(agents)}",
            backend={"type": "filesystem", "virtual_mode": False},
            default_model="fake/model",
            checkpointer=checkpointer,
            memory_enabled=False,
            session_log_enabled=False,
            bootstrap_enabled=False,
            pii_enabled=False,
            tool_guard_enabled=False,
            model_retry_enabled=False,
            media_offload_enabled=False,
            ask_user_enabled=False,
            team_enabled=False,
            subagents_auto_load=False,
            mcp_server_configs=deepcopy(initial or {}),
            mcp_default_servers=default_servers,
            interrupt_on=interrupt_on,
            defer_mcp_tools=defer_mcp_tools,
        )
        agent = HarnessAgent(config, model_factory=_ModelFactory(model), agent_id="shared")
        agents.append(agent)
        row = SimpleNamespace(agent_id="shared", kind="expert", user_id=2, is_shared=1)
        manager = object.__new__(AgentManager)
        manager._repos = SimpleNamespace(agent_repo=SimpleNamespace(get=lambda _id: row))
        manager._harness_manager = SimpleNamespace(
            get_agent=lambda _id: SimpleNamespace(agent=agent)
        )
        manager._connector_svc = _Catalog()
        manager._connector_user_override = {}
        manager._paths = SimpleNamespace(root=tmp_path)
        manager._mcp_tool_cache = {}
        manager._mcp_tool_cache_locks = {}
        manager._mcp_tool_cache_guard = asyncio.Lock()
        return SimpleNamespace(
            agent=agent,
            manager=manager,
            catalog=manager._connector_svc,
            model=model,
            executions=executions,
            loads=loads,
        )

    yield make_runtime
    for agent in agents:
        await agent.aclose()


async def _prepare(env: SimpleNamespace, uid: int, names: list[str]) -> list[str]:
    approved = env.manager.validate_mcp_servers(uid, names)
    return await env.manager.prepare_chat_mcp("shared", approved, connector_user_id=uid)


def _request(uid: int, names: list[str] | None, *, label: str) -> ChatRequest:
    return ChatRequest(
        messages="Use an available local probe tool once.",
        user=str(uid),
        agent_id="shared",
        source="ask_agent",
        thread_id=label,
        mcp_servers=names,
    )


async def _execute(env: SimpleNamespace, request: ChatRequest) -> SimpleNamespace:
    env.model.seen.clear()
    before = len(env.executions)
    result = await env.agent.call(request)
    return SimpleNamespace(
        visible=list(env.model.seen),
        executed=env.executions[before:],
        result=result,
    )


@pytest.mark.asyncio
async def test_shared_runtime_executes_each_users_current_credentials(runtime_factory: Any) -> None:
    env = runtime_factory(initial={"inventory": {}})
    for uid in (1, 2):
        assert await _prepare(env, uid, ["inventory"]) == []
        observation = await _execute(env, _request(uid, ["inventory"], label=f"user-{uid}"))
        assert observation.executed == [("inventory", f"test-user-{uid}-v1")]


@pytest.mark.asyncio
async def test_interleaved_preparations_do_not_replace_another_requests_credentials(
    runtime_factory: Any,
) -> None:
    env = runtime_factory(initial={"inventory": {}})
    assert await _prepare(env, 1, ["inventory"]) == []
    first = _request(1, ["inventory"], label="prepared-first")
    assert await _prepare(env, 2, ["inventory"]) == []
    second = _request(2, ["inventory"], label="prepared-second")
    for request, identity in ((first, "test-user-1-v1"), (second, "test-user-2-v1")):
        observation = await _execute(env, request)
        assert observation.executed == [("inventory", identity)]


@pytest.mark.asyncio
@pytest.mark.parametrize("selection", [None, []])
@pytest.mark.parametrize("scenario", ["first-load", "existing-server", "partial-failure"])
async def test_deferred_tools_remain_hidden_and_unused_without_request_selection(
    runtime_factory: Any, scenario: str, selection: list[str] | None
) -> None:
    env = runtime_factory(initial=_SEED_CONFIG if scenario == "existing-server" else {})
    names = ["probe", "broken"] if scenario == "partial-failure" else ["probe"]
    missing = await _prepare(env, 1, names)
    assert missing == (["broken"] if scenario == "partial-failure" else [])
    observation = await _execute(env, _request(1, selection, label="unselected"))
    assert all(names == [] for names in observation.visible)
    assert observation.executed == []


@pytest.mark.asyncio
@pytest.mark.parametrize("selection", [None, []])
async def test_unselected_mcp_cannot_execute_a_forced_tool_call(
    runtime_factory: Any, selection: list[str] | None
) -> None:
    env = runtime_factory(initial={"probe": {}})
    assert await _prepare(env, 1, ["probe"]) == []
    env.model.forced_tool = "probe_read"
    observation = await _execute(env, _request(1, selection, label="forced-unselected"))
    assert observation.executed == []


@pytest.mark.asyncio
async def test_new_server_is_available_when_another_server_was_already_registered(
    runtime_factory: Any,
) -> None:
    env = runtime_factory(initial=_SEED_CONFIG)
    assert await _prepare(env, 1, ["probe"]) == []
    observation = await _execute(env, _request(1, ["probe"], label="selected-new-server"))
    assert observation.executed == [("probe", "test-user-1-v1")]


@pytest.mark.asyncio
async def test_probe_selection_uses_exact_server_not_probe_extra(runtime_factory: Any) -> None:
    env = runtime_factory(initial={"probe": {}, "probe_extra": {}})
    assert await _prepare(env, 1, ["probe_extra"]) == []
    assert await _prepare(env, 1, ["probe"]) == []
    observation = await _execute(env, _request(1, ["probe"], label="exact-server"))
    assert all(names == ["probe_read"] for names in observation.visible)
    assert observation.executed == [("probe", "test-user-1-v1")]


@pytest.mark.asyncio
async def test_probe_selection_cannot_execute_probe_extra(runtime_factory: Any) -> None:
    env = runtime_factory(initial={"probe": {}, "probe_extra": {}})
    assert await _prepare(env, 1, ["probe"]) == []
    assert await _prepare(env, 1, ["probe_extra"]) == []
    env.model.forced_tool = "probe_extra_read"
    observation = await _execute(env, _request(1, ["probe"], label="forced-wrong-server"))
    assert observation.executed == []


@pytest.mark.asyncio
async def test_same_users_changed_spec_does_not_keep_old_credentials(runtime_factory: Any) -> None:
    env = runtime_factory(initial={"inventory": {}})
    assert await _prepare(env, 1, ["inventory"]) == []
    first = await _execute(env, _request(1, ["inventory"], label="before-config-change"))
    assert first.executed == [("inventory", "test-user-1-v1")]
    env.catalog.specs[1]["inventory"]["headers"]["Authorization"] = "test-user-1-v2"
    assert await _prepare(env, 1, ["inventory"]) == []
    second = await _execute(env, _request(1, ["inventory"], label="after-config-change"))
    assert second.executed == [("inventory", "test-user-1-v2")]


@pytest.mark.asyncio
async def test_explicitly_shared_connector_uses_resolved_authorized_spec(
    runtime_factory: Any,
) -> None:
    env = runtime_factory(initial={"inventory": {}})
    env.catalog.specs[1]["inventory"]["headers"]["Authorization"] = "authorized-shared-owner-2"
    assert await _prepare(env, 1, ["inventory"]) == []
    observation = await _execute(env, _request(1, ["inventory"], label="authorized-shared"))
    assert observation.executed == [("inventory", "authorized-shared-owner-2")]


@pytest.mark.asyncio
async def test_hitl_approve_resumes_original_users_selected_tool(runtime_factory: Any) -> None:
    env = runtime_factory(
        initial={"probe": {}}, checkpointer=MemorySaver(), interrupt_on={"probe_read": True}
    )
    assert await _prepare(env, 1, ["probe"]) == []
    paused = await _execute(env, _request(1, ["probe"], label="approval-original"))
    assert paused.result.get("__interrupt__")
    assert env.executions == []
    chunks = [
        chunk async for chunk in env.agent.resume_hitl("approval-original", [{"type": "approve"}])
    ]
    assert chunks
    assert env.executions == [("probe", "test-user-1-v1")]


@pytest.mark.asyncio
async def test_another_users_prepare_during_hitl_cannot_replace_pending_identity(
    runtime_factory: Any,
) -> None:
    env = runtime_factory(
        initial={"probe": {}}, checkpointer=MemorySaver(), interrupt_on={"probe_read": True}
    )
    assert await _prepare(env, 1, ["probe"]) == []
    paused = await _execute(env, _request(1, ["probe"], label="approval-interleaved"))
    assert paused.result.get("__interrupt__")
    assert await _prepare(env, 2, ["probe"]) == []
    chunks = [
        chunk
        async for chunk in env.agent.resume_hitl("approval-interleaved", [{"type": "approve"}])
    ]
    assert chunks
    assert env.executions == [("probe", "test-user-1-v1")]


@pytest.mark.asyncio
@pytest.mark.parametrize("edited_tool", ["probe_extra_read", "inventory_read"])
async def test_hitl_edit_cannot_enable_unselected_or_another_users_old_tool(
    runtime_factory: Any, edited_tool: str
) -> None:
    env = runtime_factory(
        initial={"probe": {}, "probe_extra": {}, "inventory": {}},
        checkpointer=MemorySaver(),
        interrupt_on={"probe_read": True},
    )
    assert await _prepare(env, 2, ["inventory"]) == []
    assert await _prepare(env, 1, ["probe", "probe_extra"]) == []
    env.model.forced_tool = "probe_read"
    paused = await _execute(env, _request(1, ["probe"], label="approval-edited"))
    assert paused.result.get("__interrupt__")
    assert env.executions == []
    decisions = [{"type": "edit", "edited_action": {"name": edited_tool, "args": {}}}]
    chunks = [chunk async for chunk in env.agent.resume_hitl("approval-edited", decisions)]
    assert chunks
    assert env.executions == []


@pytest.mark.asyncio
async def test_concurrent_calls_execute_their_own_authorized_identity(runtime_factory: Any) -> None:
    env = runtime_factory(initial={"inventory": {}})
    assert await _prepare(env, 1, ["inventory"]) == []
    assert await _prepare(env, 2, ["inventory"]) == []
    results = await asyncio.gather(
        env.agent.call(_request(1, ["inventory"], label="concurrent-1")),
        env.agent.call(_request(2, ["inventory"], label="concurrent-2")),
    )
    for uid, result in enumerate(results, 1):
        outputs = [
            str(message.content)
            for message in result["messages"]
            if isinstance(message, ToolMessage)
        ]
        assert outputs == [f"test-user-{uid}-v1"]


@pytest.mark.asyncio
async def test_request_can_explicitly_opt_into_configured_defaults(runtime_factory: Any) -> None:
    env = runtime_factory(initial={"probe": {}}, default_servers=["probe"])
    assert await _prepare(env, 1, ["probe"]) == []
    request = _request(1, None, label="explicit-defaults")
    request.mcp_use_default = True
    observation = await _execute(env, request)
    assert observation.executed == [("probe", "test-user-1-v1")]


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["ask", "plan"])
async def test_ask_and_plan_cannot_execute_selected_mcp(runtime_factory: Any, mode: str) -> None:
    env = runtime_factory(initial={"probe": {}})
    assert await _prepare(env, 1, ["probe"]) == []
    request = _request(1, ["probe"], label=f"mode-{mode}")
    request.conversation_mode = mode
    env.model.forced_tool = "probe_read"
    observation = await _execute(env, request)
    assert all(names == [] for names in observation.visible)
    assert observation.executed == []


@pytest.mark.asyncio
async def test_client_tool_search_loads_and_executes_selected_server(runtime_factory: Any) -> None:
    env = runtime_factory(initial={"probe": {}}, defer_mcp_tools=True)
    assert await _prepare(env, 1, ["probe"]) == []
    env.model.search_then_call = True
    observation = await _execute(env, _request(1, ["probe"], label="search-selected"))
    search_outputs = [
        str(message.content)
        for message in observation.result["messages"]
        if isinstance(message, ToolMessage) and message.tool_call_id == "search-call"
    ]
    assert len(search_outputs) == 1
    assert "Loaded tools:" in search_outputs[0]
    assert "probe_read" in search_outputs[0]
    assert observation.executed == [("probe", "test-user-1-v1")]


@pytest.mark.asyncio
async def test_client_tool_search_cannot_discover_unselected_server(runtime_factory: Any) -> None:
    env = runtime_factory(initial={"probe": {}}, defer_mcp_tools=True)
    assert await _prepare(env, 1, ["probe"]) == []
    env.model.search_then_call = True
    observation = await _execute(env, _request(1, [], label="search-unselected"))
    assert all(names == [] for names in observation.visible)
    assert observation.executed == []
    assert not any(
        isinstance(message, ToolMessage) and message.tool_call_id == "search-call"
        for message in observation.result["messages"]
    )


@pytest.mark.asyncio
async def test_revoked_permission_blocks_already_prepared_tool(runtime_factory: Any) -> None:
    env = runtime_factory(initial={"probe": {}})
    assert await _prepare(env, 1, ["probe"]) == []
    del env.catalog.specs[1]["probe"]
    env.model.forced_tool = "probe_read"
    observation = await _execute(env, _request(1, ["probe"], label="permission-revoked"))
    assert observation.executed == []


@pytest.mark.asyncio
async def test_cache_invalidation_refreshes_prepared_credentials(runtime_factory: Any) -> None:
    env = runtime_factory(initial={"inventory": {}})
    assert await _prepare(env, 1, ["inventory"]) == []
    env.catalog.specs[1]["inventory"]["headers"]["Authorization"] = "test-user-1-v2"
    env.manager.invalidate_mcp_tool_cache(1)
    assert await _prepare(env, 1, ["inventory"]) == []
    observation = await _execute(env, _request(1, ["inventory"], label="after-invalidation"))
    assert observation.executed == [("inventory", "test-user-1-v2")]


@pytest.mark.asyncio
async def test_resume_actor_cannot_use_another_users_checkpoint(runtime_factory: Any) -> None:
    from octop.infra.agents.middleware.mcp_scope import mcp_actor_scope

    env = runtime_factory(
        initial={"probe": {}}, checkpointer=MemorySaver(), interrupt_on={"probe_read": True}
    )
    assert await _prepare(env, 1, ["probe"]) == []
    paused = await _execute(env, _request(1, ["probe"], label="actor-mismatch"))
    assert paused.result.get("__interrupt__")
    with mcp_actor_scope(2):
        chunks = [
            chunk async for chunk in env.agent.resume_hitl("actor-mismatch", [{"type": "approve"}])
        ]
    assert chunks
    assert env.executions == []


@pytest.mark.asyncio
async def test_same_named_tools_keep_each_users_actual_argument_schema(
    runtime_factory: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = runtime_factory(initial={"inventory": {}})
    outputs: list[tuple[str, int]] = []

    async def load(configs: dict[str, Any]) -> list[Any]:
        uid = configs["inventory"]["headers"]["Authorization"]
        if uid == "test-user-1-v1":

            async def read_a(foo: int) -> str:
                outputs.append(("a", foo))
                return str(foo)

            callback = read_a
        else:

            async def read_b(bar: int) -> str:
                outputs.append(("b", bar))
                return str(bar)

            callback = read_b
        return [
            StructuredTool.from_function(
                coroutine=callback, name="inventory_read", description="Schema probe"
            )
        ]

    monkeypatch.setattr("octop_harness.mcp.aload_mcp_tools", load)
    assert await _prepare(env, 1, ["inventory"]) == []
    assert await _prepare(env, 2, ["inventory"]) == []
    for uid, args in ((1, {"foo": 7}), (2, {"bar": 9})):
        env.model.call_args = args
        await _execute(env, _request(uid, ["inventory"], label=f"schema-{uid}"))
    assert outputs == [("a", 7), ("b", 9)]


@pytest.mark.asyncio
async def test_mcp_runtime_argument_is_not_replaced_by_execution_context(
    runtime_factory: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = runtime_factory(initial={"probe": {}})
    outputs: list[str] = []

    async def read(runtime: str) -> str:
        outputs.append(runtime)
        return runtime

    async def load(_configs: dict[str, Any]) -> list[Any]:
        return [
            StructuredTool.from_function(
                coroutine=read, name="probe_read", description="Argument probe"
            )
        ]

    monkeypatch.setattr("octop_harness.mcp.aload_mcp_tools", load)
    assert await _prepare(env, 1, ["probe"]) == []
    env.model.call_args = {"runtime": "user-supplied tool argument"}
    await _execute(env, _request(1, ["probe"], label="runtime-argument"))
    assert outputs == ["user-supplied tool argument"]


@pytest.mark.asyncio
async def test_changed_credentials_do_not_retarget_an_existing_approval(
    runtime_factory: Any,
) -> None:
    env = runtime_factory(
        initial={"inventory": {}}, checkpointer=MemorySaver(), interrupt_on={"inventory_read": True}
    )
    assert await _prepare(env, 1, ["inventory"]) == []
    paused = await _execute(env, _request(1, ["inventory"], label="old-approval"))
    assert paused.result.get("__interrupt__")
    env.catalog.specs[1]["inventory"]["headers"]["Authorization"] = "test-user-1-v2"
    assert await _prepare(env, 1, ["inventory"]) == []
    chunks = [chunk async for chunk in env.agent.resume_hitl("old-approval", [{"type": "approve"}])]
    assert chunks
    assert env.executions == []


def _bind_builtin_catalog(
    env: Any, monkeypatch: pytest.MonkeyPatch, kind: str
) -> tuple[str, dict[str, str]]:
    from unittest.mock import AsyncMock

    from octop.config import OctopConfig

    server = f"{kind}__1"
    instance = SimpleNamespace(instance_id="1", kind=kind, status="active", mcp_server_name=server)
    creds = {"token": "builtin-v1", "email": "local@example.invalid", "password": "builtin-v1"}
    env.manager._config = OctopConfig()
    env.manager._repos.connector_repo = SimpleNamespace(
        connector_feature_allows=lambda _uid: True, list_visible=lambda _uid: [instance]
    )
    monkeypatch.setattr(env.catalog, "list_active_mcp_server_names", lambda _uid: [server])
    monkeypatch.setattr(env.catalog, "custom_harness_configs", lambda _uid: {})
    monkeypatch.setattr(env.catalog, "decrypt", lambda _iid: dict(creds))
    monkeypatch.setattr(env.catalog, "ensure_fresh_credentials", AsyncMock())
    return server, creds


@pytest.mark.asyncio
async def test_builtin_http_refreshes_credentials_without_reloading_agent(
    runtime_factory: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = runtime_factory()
    server, creds = _bind_builtin_catalog(env, monkeypatch, "tencent-lexiang")
    env.model.forced_tool = f"{server}_read"
    for version in ("builtin-v1", "builtin-v2"):
        creds["token"] = version
        assert await _prepare(env, 1, [server]) == []
        observation = await _execute(env, _request(1, [server], label=version))
        assert observation.executed == [(server, f"Bearer {version}")]


@pytest.mark.asyncio
async def test_gateway_refreshes_effective_credentials_and_blocks_unselected_calls(
    runtime_factory: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = runtime_factory()
    server, creds = _bind_builtin_catalog(env, monkeypatch, "qq-mail")
    executions: list[str] = []

    def handle(**kwargs: Any) -> dict[str, Any]:
        identity = kwargs["creds"]["password"]
        executions.append(identity)
        return {"result": {"content": [{"type": "text", "text": identity}]}}

    monkeypatch.setattr("octop.infra.connectors.gateway.langchain.handle_mcp_request", handle)
    env.model.forced_tool = f"{server}_search_emails"
    for version in ("builtin-v1", "builtin-v2"):
        creds["password"] = version
        assert await _prepare(env, 1, [server]) == []
        await _execute(env, _request(1, [server], label=version))
    await _execute(env, _request(1, [], label="unselected-gateway"))
    assert executions == ["builtin-v1", "builtin-v2"]


@pytest.mark.asyncio
async def test_agently_confirm_still_requires_hitl_with_global_policy_off(
    runtime_factory: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = runtime_factory(checkpointer=MemorySaver())
    server, _creds = _bind_builtin_catalog(env, monkeypatch, "agently-cli")
    executions: list[dict[str, Any]] = []

    def handle(**kwargs: Any) -> dict[str, Any]:
        executions.append(kwargs)
        return {"result": {"content": [{"type": "text", "text": "confirmed"}]}}

    monkeypatch.setattr("octop.infra.connectors.gateway.langchain.handle_mcp_request", handle)
    assert await _prepare(env, 1, [server]) == []
    env.model.forced_tool = f"{server}_agently_send"
    env.model.call_args = {
        "confirmation_token": "local-confirmation",
        "to": "local@example.invalid",
        "subject": "Local",
        "text": "Test",
    }
    paused = await _execute(env, _request(1, [server], label="agently-confirm"))
    assert paused.result.get("__interrupt__")
    assert executions == []


@pytest.mark.asyncio
async def test_manager_resume_rechecks_effective_credentials_before_approval(
    runtime_factory: Any,
) -> None:
    from contextlib import asynccontextmanager

    env = runtime_factory(
        initial={"inventory": {}}, checkpointer=MemorySaver(), interrupt_on={"inventory_read": True}
    )

    @asynccontextmanager
    async def lifecycle(*_args: Any) -> AsyncIterator[None]:
        yield

    env.manager._thread_execution_lock = lifecycle
    env.manager._track_invocation = lifecycle
    env.manager._apply_pending_bootstrap_graph_refresh = lambda _id: None
    env.manager._stream_model_label = lambda *_args: "fake/model"
    env.manager._harness_manager.resume_hitl = lambda _id, tid, decisions: env.agent.resume_hitl(
        tid, decisions
    )
    assert await _prepare(env, 1, ["inventory"]) == []
    paused = await _execute(env, _request(1, ["inventory"], label="manager-approval"))
    assert paused.result.get("__interrupt__")
    env.catalog.specs[1]["inventory"]["headers"]["Authorization"] = "changed-without-prepare"
    chunks = [
        chunk
        async for chunk in env.manager.resume_hitl(
            "shared", "manager-approval", [{"type": "approve"}], user_id=1
        )
    ]
    assert chunks
    assert env.executions == []
