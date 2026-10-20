"""Tests for provider-native deferred tool loading."""

from __future__ import annotations

from typing import Any

import pytest
from langchain.agents.middleware import ModelRequest, ModelResponse
from langchain_core.tools import StructuredTool

from octop_harness.config import ModelConfig, ProviderConfig
from octop_harness.llm.factory import build_chat_model
from octop_harness.middleware.native_tool_search import NativeToolSearchMiddleware


def _tool(name: str, *, deferred: bool = False) -> StructuredTool:
    tool = StructuredTool.from_function(lambda: "ok", name=name, description=f"{name} tool")
    if deferred:
        tool = tool.model_copy(update={"extras": {"defer_loading": True}})
    return tool


def _model(provider: str, *, enabled: bool = True) -> Any:
    class_name = "ChatOpenAI" if provider == "openai" else "ChatAnthropic"
    cls = type(class_name, (), {})
    model = cls()
    model._harness_native_tool_search = enabled
    model._harness_tool_search_provider = provider
    return model


def _request(model: Any, tools: list[Any]) -> ModelRequest:
    return ModelRequest(
        model=model,
        messages=[],
        system_message=None,
        tool_choice=None,
        tools=tools,
        response_format=None,
        state={},
        runtime=None,
        model_settings={},
    )


@pytest.mark.parametrize(
    ("provider", "search_type"),
    [
        ("openai", "tool_search"),
        ("anthropic", "tool_search_tool_bm25_20251119"),
    ],
)
def test_injects_provider_search_and_defers_real_tool(provider: str, search_type: str) -> None:
    eager = _tool("current_time")
    deferred = _tool("generate_image")
    request = _request(_model(provider), [eager, deferred])
    middleware = NativeToolSearchMiddleware(deferred_tools=frozenset({"generate_image"}))
    captured: dict[str, list[Any]] = {}

    def handler(prepared: ModelRequest) -> ModelResponse:
        captured["tools"] = list(prepared.tools)
        return ModelResponse(result=[])

    middleware.wrap_model_call(request, handler)

    tools = captured["tools"]
    assert tools[0] is eager
    assert tools[1].name == "generate_image"
    assert tools[1].extras["defer_loading"] is True
    assert tools[1] is not deferred
    assert tools[-1]["type"] == search_type
    assert deferred.extras is None


def test_only_visible_mcp_tools_enter_search_inventory() -> None:
    visible = _tool("github_search")
    request = _request(_model("openai"), [visible])
    middleware = NativeToolSearchMiddleware(
        deferred_tools=frozenset(),
        mcp_tool_names=frozenset({"github_search", "hidden_admin"}),
        defer_mcp_tools=True,
    )
    captured: dict[str, list[Any]] = {}

    def handler(prepared: ModelRequest) -> ModelResponse:
        captured["tools"] = list(prepared.tools)
        return ModelResponse(result=[])

    middleware.wrap_model_call(request, handler)

    names = [getattr(tool, "name", None) for tool in captured["tools"]]
    assert names.count("github_search") == 1
    assert "hidden_admin" not in names
    assert captured["tools"][0].extras["defer_loading"] is True


def test_unsupported_model_falls_back_to_clean_eager_schema() -> None:
    marked = _tool("generate_video", deferred=True)
    request = _request(_model("openai", enabled=False), [marked])
    middleware = NativeToolSearchMiddleware(deferred_tools=frozenset({"generate_video"}))
    captured: dict[str, list[Any]] = {}

    def handler(prepared: ModelRequest) -> ModelResponse:
        captured["tools"] = list(prepared.tools)
        return ModelResponse(result=[])

    middleware.wrap_model_call(request, handler)

    assert len(captured["tools"]) == 1
    assert "defer_loading" not in (captured["tools"][0].extras or {})


def test_strict_fallback_rejects_unsupported_model() -> None:
    request = _request(_model("openai", enabled=False), [_tool("generate_3d")])
    middleware = NativeToolSearchMiddleware(
        deferred_tools=frozenset({"generate_3d"}),
        fallback="error",
    )

    with pytest.raises(ValueError, match="does not advertise"):
        middleware.wrap_model_call(request, lambda _: ModelResponse(result=[]))


@pytest.mark.parametrize(
    ("provider", "search_type"),
    [
        ("openai", "tool_search"),
        ("anthropic", "tool_search_tool_bm25_20251119"),
    ],
)
def test_real_provider_adapter_serializes_native_wire_format(provider: str, search_type: str) -> None:
    config = ProviderConfig(
        id=provider,
        base_url=f"https://{provider}.example/v1",
        api_key="test-key",
        protocol=provider,  # type: ignore[arg-type]
    )
    model = build_chat_model(
        config,
        ModelConfig(
            id="native-search-model",
            api_mode="responses" if provider == "openai" else "chat_completions",
            native_tool_search=True,
        ),
    )
    request = _request(model, [_tool("generate_image")])
    middleware = NativeToolSearchMiddleware(deferred_tools=frozenset({"generate_image"}))
    captured: dict[str, list[Any]] = {}

    def handler(prepared: ModelRequest) -> ModelResponse:
        bound = model.bind_tools(prepared.tools)
        captured["tools"] = list(bound.kwargs["tools"])
        return ModelResponse(result=[])

    middleware.wrap_model_call(request, handler)

    assert captured["tools"][0]["defer_loading"] is True
    assert captured["tools"][-1]["type"] == search_type


@pytest.mark.asyncio
async def test_async_anthropic_path() -> None:
    request = _request(_model("anthropic"), [_tool("generate_video")])
    middleware = NativeToolSearchMiddleware(deferred_tools=frozenset({"generate_video"}))

    async def handler(prepared: ModelRequest) -> ModelResponse:
        assert prepared.tools[-1]["type"] == "tool_search_tool_bm25_20251119"
        return ModelResponse(result=[])

    result = await middleware.awrap_model_call(request, handler)
    assert result.result == []
