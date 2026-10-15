"""OpenDesign built-in configuration and real stdio integration regressions."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from langchain_core.runnables.config import var_child_runnable_config
from langchain_core.tools import ToolException

from octop.config import OctopConfig
from octop.infra.connectors.builder import build_http_mcp_spec, validate_create_credentials
from octop.infra.connectors.catalog import get_catalog_entry
from octop.infra.connectors.open_design import OpenDesignRuntime, probe_open_design


def credentials() -> dict[str, Any]:
    return {
        "command": sys.executable,
        "args": [str(Path(__file__).resolve().parents[2] / "fixtures" / "open_design_mcp.py")],
        "env": {},
    }


def test_builtin_config_and_secret_preview() -> None:
    from octop.api.routers.connectors import _credentials_preview, _merge_credentials

    raw = {"command": sys.executable, "args": '["mcp"]', "env": '{"TOKEN":"secret"}'}
    creds = validate_create_credentials("open-design", raw)
    entry = get_catalog_entry("open-design")
    assert entry is not None and entry.mcp_mode == "stdio"
    assert build_http_mcp_spec(entry=entry, instance_id="i", creds=creds, config=OctopConfig())[
        "args"
    ] == ["mcp"]
    assert _credentials_preview("open-design", creds) == {
        "command": sys.executable,
        "args": ["mcp"],
        "env_configured": True,
    }
    assert _merge_credentials(creds, {"command": "other"}, kind="open-design")["env"] == {
        "TOKEN": "secret"
    }
    with pytest.raises(ValueError):
        validate_create_credentials("open-design", {"command": "node", "args": "[1]"})


@pytest.mark.asyncio
async def test_read_only_probe() -> None:
    result = await probe_open_design(credentials())
    assert result["ok"] is True
    assert result["tool_count"] == 6


@pytest.mark.asyncio
async def test_persistent_brief_resources_tasks_and_isolation() -> None:
    stored: dict[str, str] = {}
    instance = SimpleNamespace(
        instance_id="i", kind="open-design", mcp_server_name="open-design__i"
    )
    service = SimpleNamespace(
        decrypt=lambda _: credentials(), list_user_instances=lambda *a, **kw: [instance]
    )
    repos = SimpleNamespace(
        agent_repo=SimpleNamespace(get=lambda _: SimpleNamespace(user_id=7)),
        settings_repo=SimpleNamespace(get=stored.get, set=stored.__setitem__),
    )
    runtime = OpenDesignRuntime(service, repos)
    try:
        tools = {
            t.name.removeprefix("open-design__i_"): t
            for t in await runtime.build_tools(user_id=7, instance=instance, agent_id="a")
        }
        config = {"configurable": {"user": "7", "thread_id": "t"}}

        async def invoke(name: str, args: dict[str, Any], cfg: Any = config) -> Any:
            return await tools[name].ainvoke(
                {"name": tools[name].name, "args": args, "id": name, "type": "tool_call"},
                config=cfg,
            )

        await invoke("collect_brief", {"projectTitle": "demo"})
        result = await invoke(
            "confirm_brief", {"briefDraftId": "draft", "nonce": "nonce", "answers": {"color": None}}
        )
        assert result.status == "success"
        assert "demo" in str(result.content)
        assert result.artifact is not None
        other = await invoke(
            "confirm_brief",
            {"briefDraftId": "draft", "nonce": "nonce", "answers": {}},
            {"configurable": {"user": "7", "thread_id": "other"}},
        )
        assert other.status == "error"
        resource = await invoke("read_resource", {"uri": "od://design-systems/test/DESIGN.md"})
        assert "blue accent" in resource.content
        started = await invoke("start_run", {"project": "p", "prompt": "design", "skills": ["web"]})
        assert started.artifact is not None
        state = json.loads(next(iter(stored.values())))
        assert state["status"] == "running"
        assert state["arguments"]["skills"] == ["web"]
        repeated = await invoke(
            "start_run", {"project": "p", "prompt": "design", "skills": ["web"]}
        )
        assert repeated.artifact == started.artifact
        blocked = await invoke("start_run", {"project": "p", "prompt": "different"})
        assert blocked.status == "error"
        status = await invoke("task_status", {})
        assert "succeeded" in status.content
        assert json.loads(next(iter(stored.values())))["status"] == "succeeded"
        await runtime.close()
        restored = await invoke("task_status", {})
        assert "succeeded" in restored.content
        repos.agent_repo.get = lambda _: SimpleNamespace(user_id=None)
        shared_other = await invoke(
            "confirm_brief",
            {"briefDraftId": "draft", "nonce": "nonce", "answers": {}},
            {"configurable": {"user": "8", "thread_id": "t"}},
        )
        assert shared_other.status == "error"
        token = var_child_runnable_config.set({"configurable": {"user": "8", "thread_id": "t"}})
        try:
            with pytest.raises(ToolException):
                await runtime.call(7, "i", "a", "list_projects", {})
        finally:
            var_child_runnable_config.reset(token)
    finally:
        await runtime.close()
    assert not runtime._clients


@pytest.mark.asyncio
async def test_open_design_authorization_survives_real_graph_hitl(tmp_path: Path) -> None:
    from unittest.mock import MagicMock, patch

    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.graph import END, START, MessagesState, StateGraph
    from langgraph.types import interrupt
    from octop_harness.agent import HarnessAgent
    from octop_harness.config import HarnessAgentConfig, ModelConfig, ProviderConfig

    from octop.infra.gateway.hitl.stream_compat import install_harness_hitl_compat

    install_harness_hitl_compat()
    instance = SimpleNamespace(
        instance_id="i", kind="open-design", mcp_server_name="open-design__i"
    )
    runtime = OpenDesignRuntime(
        SimpleNamespace(
            decrypt=lambda _: credentials(), list_user_instances=lambda *a, **k: [instance]
        ),
        SimpleNamespace(
            agent_repo=SimpleNamespace(get=lambda _: SimpleNamespace(user_id=7)),
            settings_repo=SimpleNamespace(get=lambda _: None, set=lambda *a: None),
        ),
    )
    results: list[Any] = []
    tools = {
        t.name: t for t in await runtime.build_tools(user_id=7, instance=instance, agent_id="a")
    }

    async def confirm_and_read(state: MessagesState) -> dict[str, Any]:
        interrupt(
            {"action_requests": [{"name": "ask_user_question", "args": {"question": "Confirm?"}}]}
        )
        result = await tools["open-design__i_list_resources"].ainvoke(
            {
                "name": "open-design__i_list_resources",
                "args": {},
                "id": "resources",
                "type": "tool_call",
            }
        )
        results.append(result)
        return {"messages": []}

    builder = StateGraph(MessagesState)
    builder.add_node("confirm", confirm_and_read)
    builder.add_edge(START, "confirm")
    builder.add_edge("confirm", END)
    graph = builder.compile(checkpointer=InMemorySaver())
    config = HarnessAgentConfig(
        name="designer",
        workspace_dir=tmp_path,
        backend={"type": "filesystem", "root_dir": str(tmp_path), "virtual_mode": False},
        providers=[
            ProviderConfig(
                id="p",
                base_url="https://example.invalid",
                api_key="test",
                models=[ModelConfig(id="text")],
            )
        ],
        default_model="p/text",
        memory_enabled=False,
        checkpointer=False,
    )
    with (
        patch("langchain_openai.ChatOpenAI", return_value=MagicMock()),
        patch("deepagents.create_deep_agent", return_value=graph),
    ):
        agent = HarnessAgent(config)
    try:
        chunks = [
            c
            async for c in agent.stream(
                {
                    "messages": "design",
                    "thread_id": "t",
                    "user": "7",
                    "agent_id": "a",
                    "mcp_servers": ["open-design__i"],
                    "configurable": {"locale": "zh"},
                }
            )
        ]
        assert any(c.get("type") == "hitl_required" for c in chunks)
        _ = [c async for c in agent.resume_hitl("t", [{"type": "approve"}])]
        assert len(results) == 1
        assert results[0].status == "success"
        assert "od://design-systems" in str(results[0].content)
    finally:
        await agent.aclose()
        await runtime.close()
