"""Tests for provider-agnostic progressive tool loading."""

from __future__ import annotations

import json
from typing import Any, cast
from unittest.mock import patch

import pytest
from langchain.agents import create_agent
from langchain.agents.middleware import ModelRequest, ModelResponse
from langchain.agents.middleware.types import AgentState
from langchain.tools import ToolRuntime
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import StructuredTool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command

from octop_harness.config import ModelConfig, ProviderConfig
from octop_harness.llm.factory import build_chat_model
from octop_harness.middleware.client_tool_search import (
    ClientToolSearchMiddleware,
    ClientToolSearchState,
)


def _tool(name: str, *, deferred: bool = False) -> StructuredTool:
    tool = StructuredTool.from_function(lambda: "ok", name=name, description=f"{name} capability")
    if deferred:
        tool = tool.model_copy(update={"extras": {"defer_loading": True}})
    return tool


def _prompt_tool(name: str) -> StructuredTool:
    def run(prompt: str) -> str:
        return prompt

    return StructuredTool.from_function(run, name=name, description=f"{name} capability")


def _request(tools: list[Any], *, loaded: list[str] | None = None) -> ModelRequest:
    return ModelRequest(
        model=object(),  # type: ignore[arg-type]
        messages=[],
        tools=tools,
        state=cast(AgentState[Any], {"loaded_tool_names": loaded or []}),
    )


def _runtime(
    *, loaded: list[str] | None = None, thread_id: str = "thread-1"
) -> ToolRuntime[Any, ClientToolSearchState]:
    return ToolRuntime(
        state=cast(ClientToolSearchState, {"loaded_tool_names": loaded or []}),
        context=None,
        config={"configurable": {"thread_id": thread_id}},
        stream_writer=lambda _: None,
        tool_call_id="search-1",
        store=None,
        tools=[],
    )


def _capture_tools(middleware: ClientToolSearchMiddleware, request: ModelRequest) -> list[Any]:
    captured: list[Any] = []

    def handler(prepared: ModelRequest) -> ModelResponse:
        captured.extend(prepared.tools)
        return ModelResponse(result=[])

    with patch(
        "octop_harness.middleware.client_tool_search._current_thread_key",
        return_value="thread-1",
    ):
        middleware.wrap_model_call(request, handler)
    return captured


def test_hides_deferred_schema_then_exposes_loaded_tool() -> None:
    eager = _tool("current_time")
    image = _prompt_tool("generate_image")
    middleware = ClientToolSearchMiddleware(deferred_tools=frozenset({"generate_image"}))

    first_tools = _capture_tools(middleware, _request([eager, image, {"type": "web_search"}]))
    assert [getattr(tool, "name", None) for tool in first_tools] == [
        "current_time",
        "tool_search",
        "generate_image",
        None,
    ]
    reference = first_tools[2]
    assert reference is not image
    assert reference.args == {}
    assert "generate_image capability" in reference.description
    assert "Deferred reference" in reference.description
    assert "defer_loading" not in (reference.extras or {})
    assert first_tools[-1] == {"type": "web_search"}

    second_tools = _capture_tools(
        middleware,
        _request([eager, image], loaded=["generate_image"]),
    )
    assert [tool.name for tool in second_tools] == [
        "current_time",
        "tool_search",
        "generate_image",
    ]
    assert second_tools[2] is image
    assert "prompt" in second_tools[2].args


def test_search_loads_only_visible_matching_tools() -> None:
    middleware = ClientToolSearchMiddleware(
        deferred_tools=frozenset(),
        mcp_tool_names=frozenset({"github_search", "hidden_admin"}),
        defer_mcp_tools=True,
    )
    tools = _capture_tools(middleware, _request([_tool("github_search")]))

    assert [tool.name for tool in tools] == ["tool_search", "github_search"]
    assert all(tool.name != "hidden_admin" for tool in tools)

    result = middleware._search("github repository search", 3, _runtime())

    assert isinstance(result, Command)
    update = cast(dict[str, Any], result.update)
    assert update["loaded_tool_names"] == ["github_search"]
    message = update["messages"][0]
    assert isinstance(message, ToolMessage)
    assert "hidden_admin" not in message.text


def test_direct_deferred_call_is_blocked_until_loaded() -> None:
    image = _tool("generate_image")
    middleware = ClientToolSearchMiddleware(deferred_tools=frozenset({"generate_image"}))
    _capture_tools(middleware, _request([image]))
    called = False

    def handler(_: ToolCallRequest) -> ToolMessage:
        nonlocal called
        called = True
        return ToolMessage("ok", tool_call_id="image-1")

    blocked_request = ToolCallRequest(
        tool_call={"name": "generate_image", "args": {}, "id": "image-1", "type": "tool_call"},
        tool=image,
        state={"loaded_tool_names": []},
        runtime=cast(Any, _runtime()),
    )
    blocked = middleware.wrap_tool_call(blocked_request, handler)
    assert isinstance(blocked, Command)
    blocked_update = cast(dict[str, Any], blocked.update)
    assert blocked_update["loaded_tool_names"] == ["generate_image"]
    blocked_message = blocked_update["messages"][0]
    assert isinstance(blocked_message, ToolMessage)
    assert blocked_message.status == "error"
    payload = json.loads(blocked_message.text)
    assert payload["error"]["code"] == "tool_schema_not_loaded"
    assert payload["remediation"]["action"] == "retry_with_loaded_schema"
    assert called is False

    allowed_request = ToolCallRequest(
        tool_call=blocked_request.tool_call,
        tool=image,
        state={"loaded_tool_names": ["generate_image"]},
        runtime=cast(Any, _runtime(loaded=["generate_image"])),
    )
    allowed = middleware.wrap_tool_call(allowed_request, handler)
    assert isinstance(allowed, ToolMessage)
    assert allowed.text == "ok"
    assert called is True


def test_self_deferred_tool_uses_client_search() -> None:
    original = _tool("render_scene", deferred=True)
    middleware = ClientToolSearchMiddleware(deferred_tools=frozenset())
    tools = _capture_tools(middleware, _request([original]))
    assert [tool.name for tool in tools] == ["tool_search", "render_scene"]
    assert tools[1].args == {}
    assert "Deferred reference" in tools[1].description
    assert "defer_loading" not in (tools[1].extras or {})
    assert original.extras == {"defer_loading": True}


def test_client_deferred_reference_omits_native_marker_from_wire_format() -> None:
    original = _tool("render_scene", deferred=True)
    middleware = ClientToolSearchMiddleware(deferred_tools=frozenset())
    model = build_chat_model(
        ProviderConfig(
            id="maas",
            base_url="https://maas.example/v1",
            api_key="test-key",
        ),
        ModelConfig(id="responses-model", api_mode="responses"),
    )
    captured: dict[str, list[dict[str, Any]]] = {}

    def handler(prepared: ModelRequest) -> ModelResponse:
        bound = model.bind_tools(prepared.tools)
        captured["tools"] = list(bound.kwargs["tools"])
        return ModelResponse(result=[])

    with patch(
        "octop_harness.middleware.client_tool_search._current_thread_key",
        return_value="thread-1",
    ):
        middleware.wrap_model_call(_request([original]), handler)

    deferred_payload = captured["tools"][1]
    assert deferred_payload["function"]["parameters"] == {
        "properties": {},
        "type": "object",
    }
    assert "Deferred reference" in deferred_payload["function"]["description"]
    assert "defer_loading" not in deferred_payload
    assert original.extras == {"defer_loading": True}


@pytest.mark.asyncio
async def test_async_model_path_filters_tools() -> None:
    middleware = ClientToolSearchMiddleware(deferred_tools=frozenset({"generate_video"}))
    request = _request([_prompt_tool("generate_video")])

    async def handler(prepared: ModelRequest) -> ModelResponse:
        assert [getattr(tool, "name", None) for tool in prepared.tools] == [
            "tool_search",
            "generate_video",
        ]
        assert prepared.tools[1].args == {}
        return ModelResponse(result=[])

    with patch(
        "octop_harness.middleware.client_tool_search._current_thread_key",
        return_value="thread-1",
    ):
        result = await middleware.awrap_model_call(request, handler)
    assert result.result == []


def test_real_graph_searches_then_executes_loaded_tool() -> None:
    calls: list[str] = []

    def generate_image(prompt: str) -> str:
        calls.append("generate_image")
        return f"image-ready:{prompt}"

    image = StructuredTool.from_function(
        generate_image,
        name="generate_image",
        description="Generate an image from a text prompt.",
    )

    class RecordingModel(FakeMessagesListChatModel):
        seen_tools: list[list[str]] = []
        seen_tool_args: list[dict[str, dict[str, Any]]] = []

        def bind_tools(self, tools: Any, **kwargs: Any) -> RecordingModel:
            del kwargs
            self.seen_tools.append([getattr(tool, "name", "provider-tool") for tool in tools])
            self.seen_tool_args.append({tool.name: tool.args for tool in tools if hasattr(tool, "args")})
            return self

    model = RecordingModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "tool_search",
                        "args": {"query": "generate image"},
                        "id": "search-1",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "generate_image",
                        "args": {"prompt": "sunset"},
                        "id": "image-1",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="done"),
            AIMessage(content="still loaded"),
        ]
    )
    middleware = ClientToolSearchMiddleware(deferred_tools=frozenset({"generate_image"}))
    graph = create_agent(
        model,
        tools=[image],
        middleware=[middleware],
        checkpointer=InMemorySaver(),
    )

    result = graph.invoke(
        {"messages": [HumanMessage("Make an image")]},
        config={"configurable": {"thread_id": "integration-thread"}},
    )

    assert calls == ["generate_image"]
    assert model.seen_tools == [
        ["tool_search", "generate_image"],
        ["tool_search", "generate_image"],
        ["tool_search", "generate_image"],
    ]
    assert model.seen_tool_args[0]["generate_image"] == {}
    assert "prompt" in model.seen_tool_args[1]["generate_image"]
    assert result["loaded_tool_names"] == ["generate_image"]
    assert result["messages"][-1].text == "done"

    continued = graph.invoke(
        {"messages": [HumanMessage("Continue in the same thread")]},
        config={"configurable": {"thread_id": "integration-thread"}},
    )
    assert model.seen_tools[-1] == ["tool_search", "generate_image"]
    assert continued["loaded_tool_names"] == ["generate_image"]
    assert continued["messages"][-1].text == "still loaded"


def test_parallel_search_calls_merge_loaded_tools() -> None:
    """A model may emit multiple tool_search calls in one assistant message."""
    image = _tool("generate_image")
    video = _tool("generate_video")

    class ToolBindingModel(FakeMessagesListChatModel):
        def bind_tools(self, tools: Any, **kwargs: Any) -> ToolBindingModel:
            del tools, kwargs
            return self

    model = ToolBindingModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "tool_search",
                        "args": {"query": "generate image"},
                        "id": "search-image",
                        "type": "tool_call",
                    },
                    {
                        "name": "tool_search",
                        "args": {"query": "generate video"},
                        "id": "search-video",
                        "type": "tool_call",
                    },
                ],
            ),
            AIMessage(content="done"),
        ]
    )
    middleware = ClientToolSearchMiddleware(deferred_tools=frozenset({"generate_image", "generate_video"}))
    graph = create_agent(
        model,
        tools=[image, video],
        middleware=[middleware],
        checkpointer=InMemorySaver(),
    )

    result = graph.invoke(
        {"messages": [HumanMessage("Create image and video")]},
        config={"configurable": {"thread_id": "parallel-search-thread"}},
    )

    assert result["loaded_tool_names"] == ["generate_image", "generate_video"]
    search_results = [
        message for message in result["messages"] if isinstance(message, ToolMessage) and message.name == "tool_search"
    ]
    assert len(search_results) == 2
