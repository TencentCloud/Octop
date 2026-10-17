"""Exercise credential input on registered harness graphs without an LLM service."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any, Self

import pytest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from octop_harness import HarnessAgentManager
from octop_harness.llm.factory import ChatModelFactory
from tests.unit.agents.test_agent_manager import _MEMORY_OFF, _seed_test_provider

from octop.config import OctopConfig
from octop.infra.agents.manager import AgentManager
from octop.infra.agents.secret_file.tool import HEADLESS_FALLBACK
from octop.infra.agents.security.hitl_session import (
    HitlSessionPolicyStore,
    hitl_thread_scope,
)
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.services import build_shared_services
from octop.infra.gateway.hitl.stream_compat import install_harness_hitl_compat
from octop.infra.utils.paths import PathLayout


class _ToolCallingModel(FakeMessagesListChatModel):
    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> Self:
        return self


@pytest.fixture
async def manager(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AgentManager]:
    paths = PathLayout(tmp_path / ".octop")
    monkeypatch.setenv("OCTOP_HOME", str(paths.root))
    paths.ensure_root()
    db = SqlitePool(paths.db)
    run_migrations(db)
    services = build_shared_services(db=db, paths=paths, config=OctopConfig())
    manager = AgentManager(repos=services.repos, paths=services.paths)
    _seed_test_provider(manager)
    manager._repos.agent_repo.create(
        agent_id="SECRET01",
        user_id=None,
        name="credential test",
        config_json=json.dumps(_MEMORY_OFF),
    )
    manager._harness_manager = HarnessAgentManager(
        providers=manager.providers.build_harness_configs(),
        log_dir=str(paths.logs_dir),
    )
    try:
        yield manager
    finally:
        await manager.shutdown()
        db.close()


async def _register(
    manager: AgentManager,
    monkeypatch: pytest.MonkeyPatch,
    responses: list[BaseMessage],
    *,
    bootstrap: bool = False,
) -> Any:
    model = _ToolCallingModel(responses=responses)
    monkeypatch.setattr(ChatModelFactory, "get_chat_model", lambda self, *args, **kwargs: model)
    row = manager.get_row("SECRET01")
    assert row is not None
    cfg = manager._build_harness_config(row)
    cfg = replace(
        cfg,
        bootstrap_enabled=bootstrap,
        backend={"type": "filesystem", "root_dir": str(cfg.workspace_dir)},
        checkpointer=InMemorySaver(),
        team_enabled=False,
    )
    assert manager._harness_manager is not None
    manager._harness_manager.set_security_policy(manager.security.harness_policy())
    return await manager._harness_manager.acreate_agent(
        cfg, agent_id=row.agent_id, init_workspace=False
    )


def _secret_call() -> dict[str, Any]:
    return {
        "name": "request_secret_file",
        "args": {"path": "example-cli/agent.token", "prompt": "Provide the HR credential"},
        "id": "secret-call",
        "type": "tool_call",
    }


@pytest.mark.parametrize(
    ("bootstrap", "allow_all", "rebuild"),
    [(False, False, False), (True, False, False), (False, True, False), (True, True, True)],
)
async def test_registered_secret_input_survives_security_and_bootstrap(
    manager: AgentManager,
    monkeypatch: pytest.MonkeyPatch,
    bootstrap: bool,
    allow_all: bool,
    rebuild: bool,
) -> None:
    store = HitlSessionPolicyStore()
    if allow_all:
        store.set("secret-thread", {"mode": "allow_all"})
    manager.set_hitl_session_store(store)
    entry = await _register(
        manager,
        monkeypatch,
        [AIMessage(content="", tool_calls=[_secret_call()]), AIMessage(content="Connected")],
        bootstrap=bootstrap,
    )
    if rebuild:
        manager.save_security(
            {"hitl": {"enabled": True, "tools": ["request_secret_file", "write_file"]}}
        )
        assert manager._harness_manager is not None
        entry = manager._harness_manager.get_agent("SECRET01")
    assert entry.agent.is_bootstrapped() is not bootstrap
    config = {"configurable": {"thread_id": "secret-thread"}}
    with hitl_thread_scope("secret-thread"):
        paused = await entry.agent.graph.ainvoke({"messages": [("user", "Connect HR")]}, config)
        payload = paused["__interrupt__"][0].value
        assert [action["name"] for action in payload["action_requests"]] == ["request_secret_file"]
        assert payload["review_configs"][0]["allowed_decisions"] == ["respond"]
        completed = await entry.agent.graph.ainvoke(
            Command(resume={"decisions": [{"type": "respond", "message": "Credential filled"}]}),
            config,
        )
    assert "__interrupt__" not in completed
    secret_results = [
        message.content
        for message in completed["messages"]
        if isinstance(message, ToolMessage) and message.tool_call_id == "secret-call"
    ]
    assert secret_results == ["Credential filled"]
    assert HEADLESS_FALLBACK not in secret_results


@pytest.mark.parametrize("approval_enabled", [True, False])
async def test_secret_input_coexists_with_approval_and_ask_user_after_policy_reload(
    manager: AgentManager,
    monkeypatch: pytest.MonkeyPatch,
    approval_enabled: bool,
) -> None:
    calls = [
        _secret_call(),
        {
            "name": "write_file",
            "args": {"file_path": "/approved.txt", "content": "approved"},
            "id": "write-call",
            "type": "tool_call",
        },
        {"name": "ask_user_question", "args": {}, "id": "ask-call", "type": "tool_call"},
    ]
    await _register(
        manager,
        monkeypatch,
        [AIMessage(content="", tool_calls=calls), AIMessage(content="Done")],
    )
    manager.save_security(
        {
            "hitl": {
                "enabled": True,
                "tools": ["write_file", "request_secret_file"],
                "allowed_decisions": ["approve", "reject"],
            },
        }
    )
    if not approval_enabled:
        manager.save_security({"hitl": {"enabled": False}})
    assert manager._harness_manager is not None
    entry = manager._harness_manager.get_agent("SECRET01")
    config = {"configurable": {"thread_id": "mixed-thread"}}
    result = await entry.agent.graph.ainvoke({"messages": [("user", "Run the tools")]}, config)
    seen: list[str] = []
    for _ in range(3):
        if "__interrupt__" not in result:
            break
        payload = result["__interrupt__"][0].value
        decisions = []
        for action in payload["action_requests"]:
            name = action["name"]
            seen.append(name)
            decisions.append(
                {"type": "approve"}
                if name == "write_file"
                else {
                    "type": "respond",
                    "message": "Credential filled" if name == "request_secret_file" else "Answer",
                }
            )
        result = await entry.agent.graph.ainvoke(Command(resume={"decisions": decisions}), config)
    expected = ["ask_user_question", "request_secret_file"]
    if approval_enabled:
        expected.append("write_file")
    assert sorted(seen) == expected
    assert "__interrupt__" not in result
    assert (entry.config.workspace_dir / "approved.txt").read_text() == "approved"
    results = {
        message.tool_call_id: message.content
        for message in result["messages"]
        if isinstance(message, ToolMessage)
    }
    assert results["secret-call"] == "Credential filled"
    assert results["ask-call"] == "Answer"


async def test_disabled_secret_tool_does_not_offer_an_input_card(
    manager: AgentManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager.persist_harness_config(
        "SECRET01", {**_MEMORY_OFF, "tools_disabled": ["request_secret_file"]}
    )
    entry = await _register(
        manager,
        monkeypatch,
        [AIMessage(content="", tool_calls=[_secret_call()]), AIMessage(content="Tool unavailable")],
    )
    result = await entry.agent.graph.ainvoke(
        {"messages": [("user", "Connect HR")]},
        {"configurable": {"thread_id": "disabled-thread"}},
    )
    assert "__interrupt__" not in result
    tool_results = [message for message in result["messages"] if isinstance(message, ToolMessage)]
    assert len(tool_results) == 1
    assert tool_results[0].status == "error"


async def test_paused_secret_input_resumes_after_security_rebuild(
    manager: AgentManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entry = await _register(
        manager,
        monkeypatch,
        [AIMessage(content="", tool_calls=[_secret_call()]), AIMessage(content="Connected")],
    )
    config = {"configurable": {"thread_id": "paused-secret-thread"}}
    paused = await entry.agent.graph.ainvoke({"messages": [("user", "Connect HR")]}, config)
    assert [action["name"] for action in paused["__interrupt__"][0].value["action_requests"]] == [
        "request_secret_file"
    ]
    checkpointer = entry.agent.checkpointer

    manager.save_security(
        {"hitl": {"enabled": True, "tools": ["request_secret_file", "write_file"]}}
    )
    assert manager._harness_manager is not None
    rebuilt = manager._harness_manager.get_agent("SECRET01")
    assert rebuilt.agent is not entry.agent
    assert rebuilt.agent.checkpointer is checkpointer
    snapshot = await rebuilt.agent.graph.aget_state(config)
    assert snapshot.next
    assert snapshot.values["messages"][-1].tool_calls[0]["id"] == "secret-call"

    completed = await rebuilt.agent.graph.ainvoke(
        Command(resume={"decisions": [{"type": "respond", "message": "Credential filled"}]}),
        config,
    )
    assert "__interrupt__" not in completed
    secret_results = [
        message.content
        for message in completed["messages"]
        if isinstance(message, ToolMessage) and message.tool_call_id == "secret-call"
    ]
    assert secret_results == ["Credential filled"]


async def test_registered_agent_stream_emits_one_credential_card_and_resumes(
    manager: AgentManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_harness_hitl_compat()
    entry = await _register(
        manager,
        monkeypatch,
        [AIMessage(content="", tool_calls=[_secret_call()]), AIMessage(content="Connected")],
    )
    chunks = [
        chunk
        async for chunk in entry.agent.stream(
            {
                "thread_id": "stream-secret-thread",
                "messages": [{"role": "user", "content": "Connect HR"}],
            }
        )
    ]
    cards = [chunk for chunk in chunks if chunk.get("type") == "hitl_required"]
    assert len(cards) == 1
    assert cards[0]["request"]["action_requests"][0]["name"] == "request_secret_file"
    resumed = [
        chunk
        async for chunk in entry.agent.resume_hitl(
            "stream-secret-thread", [{"type": "respond", "message": "Credential filled"}]
        )
    ]
    assert not any(chunk.get("type") == "hitl_required" for chunk in resumed)
    snapshot = await entry.agent.graph.aget_state(
        {"configurable": {"thread_id": "stream-secret-thread"}}
    )
    assert [
        message.content
        for message in snapshot.values["messages"]
        if isinstance(message, ToolMessage) and message.tool_call_id == "secret-call"
    ] == ["Credential filled"]
