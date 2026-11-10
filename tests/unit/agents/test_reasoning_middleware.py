"""Unit tests for the reasoning request middleware (#2498)."""

import pytest
from langchain.agents.middleware import ModelRequest
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_openai import ChatOpenAI

from octop.infra.agents.middleware import reasoning


def test_scrubs_replayed_reasoning_when_gate_false(monkeypatch) -> None:
    """Issue #2498: groq rejects replayed assistant ``reasoning_content``."""
    monkeypatch.setattr(
        reasoning,
        "get_config",
        lambda: {"configurable": {reasoning.ROUNDTRIP_KEY: False}},
    )
    model = ChatOpenAI(model="llama-3.3-70b-versatile", api_key="test")
    history = [
        HumanMessage(content="hi"),
        AIMessage(
            content="hello",
            additional_kwargs={"reasoning_content": "thought about it"},
        ),
    ]
    request = ModelRequest(model=model, messages=history)

    scrubbed = reasoning._scrub_replayed_reasoning(request)

    assert scrubbed is not request
    assert scrubbed.messages[1].additional_kwargs == {}
    assert scrubbed.messages[1].content == "hello"
    assert request.messages[1].additional_kwargs == {"reasoning_content": "thought about it"}


def test_scrub_keeps_history_when_gate_grants_roundtrip(monkeypatch) -> None:
    monkeypatch.setattr(
        reasoning,
        "get_config",
        lambda: {"configurable": {reasoning.ROUNDTRIP_KEY: True}},
    )
    request = ModelRequest(
        model=ChatOpenAI(model="deepseek-v4", api_key="test"),
        messages=[
            HumanMessage(content="hi"),
            AIMessage(content="hello", additional_kwargs={"reasoning_content": "kept"}),
        ],
    )

    assert reasoning._scrub_replayed_reasoning(request) is request


def test_scrub_keeps_history_without_reasoning_content(monkeypatch) -> None:
    monkeypatch.setattr(
        reasoning,
        "get_config",
        lambda: {"configurable": {reasoning.ROUNDTRIP_KEY: False}},
    )
    request = ModelRequest(
        model=ChatOpenAI(model="llama-3.3-70b-versatile", api_key="test"),
        messages=[HumanMessage(content="hi"), AIMessage(content="hello")],
    )

    assert reasoning._scrub_replayed_reasoning(request) is request


def test_scrub_keeps_history_when_gate_absent_and_overrides_present(monkeypatch) -> None:
    """Gate missing while overrides exist (pre-gate caller contract): no scrubbing."""
    monkeypatch.setattr(
        reasoning,
        "get_config",
        lambda: {
            "configurable": {reasoning.CONFIG_KEY: {"model_fields": {"reasoning_effort": "high"}}}
        },
    )
    request = ModelRequest(
        model=ChatOpenAI(model="llama-3.3-70b-versatile", api_key="test"),
        messages=[AIMessage(content="hello", additional_kwargs={"reasoning_content": "x"})],
    )

    assert reasoning._scrub_replayed_reasoning(request) is request


def test_scrub_keeps_history_when_gate_is_not_a_bool(monkeypatch) -> None:
    monkeypatch.setattr(
        reasoning,
        "get_config",
        lambda: {"configurable": {reasoning.ROUNDTRIP_KEY: "false"}},
    )
    request = ModelRequest(
        model=ChatOpenAI(model="llama-3.3-70b-versatile", api_key="test"),
        messages=[AIMessage(content="hello", additional_kwargs={"reasoning_content": "x"})],
    )

    assert reasoning._scrub_replayed_reasoning(request) is request


def test_scrub_removes_empty_and_none_reasoning_content(monkeypatch) -> None:
    """With gate=False, empty-string and None values are dropped too."""
    monkeypatch.setattr(
        reasoning,
        "get_config",
        lambda: {"configurable": {reasoning.ROUNDTRIP_KEY: False}},
    )
    request = ModelRequest(
        model=ChatOpenAI(model="llama-3.3-70b-versatile", api_key="test"),
        messages=[
            AIMessage(content="one", additional_kwargs={"reasoning_content": ""}),
            AIMessage(content="two", additional_kwargs={"reasoning_content": None}),
        ],
    )

    scrubbed = reasoning._scrub_replayed_reasoning(request)

    assert scrubbed is not request
    assert scrubbed.messages[0].additional_kwargs == {}
    assert scrubbed.messages[1].additional_kwargs == {}
    assert scrubbed.messages[0].content == "one"
    assert scrubbed.messages[1].content == "two"


def test_scrub_spares_tool_calls_and_other_kwargs(monkeypatch) -> None:
    monkeypatch.setattr(
        reasoning,
        "get_config",
        lambda: {"configurable": {reasoning.ROUNDTRIP_KEY: False}},
    )
    history = [
        AIMessage(
            content="",
            tool_calls=[{"name": "get_weather", "args": {"city": "x"}, "id": "call_1"}],
            additional_kwargs={"reasoning_content": "chose tool", "other": "keep"},
        ),
        ToolMessage(content="sunny", tool_call_id="call_1"),
        HumanMessage(content="thanks"),
    ]
    request = ModelRequest(
        model=ChatOpenAI(model="llama-3.3-70b-versatile", api_key="test"),
        messages=history,
    )

    scrubbed = reasoning._scrub_replayed_reasoning(request)

    assert scrubbed is not request
    cleaned = scrubbed.messages[0]
    assert isinstance(cleaned, AIMessage)
    # langchain normalizes tool_calls with a "type": "tool_call" entry.
    assert cleaned.tool_calls == [
        {"name": "get_weather", "args": {"city": "x"}, "id": "call_1", "type": "tool_call"}
    ]
    assert cleaned.additional_kwargs == {"other": "keep"}
    assert scrubbed.messages[1].content == "sunny"
    assert scrubbed.messages[2].content == "thanks"
    # The original history stays untouched.
    assert history[0].additional_kwargs["reasoning_content"] == "chose tool"


def test_scrub_keeps_request_without_reasoning_fields(monkeypatch) -> None:
    monkeypatch.setattr(
        reasoning,
        "get_config",
        lambda: {"configurable": {reasoning.ROUNDTRIP_KEY: False}},
    )
    request = ModelRequest(
        model=ChatOpenAI(model="llama-3.3-70b-versatile", api_key="test"),
        messages=[AIMessage(content="hello", additional_kwargs={"other": "value"})],
    )

    assert reasoning._scrub_replayed_reasoning(request) is request


def test_wrap_model_call_passes_scrubbed_request(monkeypatch) -> None:
    """The sync handler receives the scrubbed request."""
    monkeypatch.setattr(
        reasoning,
        "get_config",
        lambda: {"configurable": {reasoning.ROUNDTRIP_KEY: False}},
    )
    request = ModelRequest(
        model=ChatOpenAI(model="llama-3.3-70b-versatile", api_key="test"),
        messages=[AIMessage(content="hello", additional_kwargs={"reasoning_content": "x"})],
    )
    seen = []
    middleware = reasoning.ReasoningRequestMiddleware()

    middleware.wrap_model_call(request, seen.append)

    assert len(seen) == 1
    assert seen[0] is not request
    assert seen[0].messages[0].additional_kwargs == {}
    assert seen[0].messages[0].content == "hello"


@pytest.mark.asyncio
async def test_awrap_model_call_passes_scrubbed_request(monkeypatch) -> None:
    """The async handler receives the scrubbed request."""
    monkeypatch.setattr(
        reasoning,
        "get_config",
        lambda: {"configurable": {reasoning.ROUNDTRIP_KEY: False}},
    )
    request = ModelRequest(
        model=ChatOpenAI(model="llama-3.3-70b-versatile", api_key="test"),
        messages=[AIMessage(content="hello", additional_kwargs={"reasoning_content": "x"})],
    )
    seen = []

    async def handler(req):
        seen.append(req)
        return "ok"

    middleware = reasoning.ReasoningRequestMiddleware()

    result = await middleware.awrap_model_call(request, handler)

    assert result == "ok"
    assert len(seen) == 1
    assert seen[0] is not request
    assert seen[0].messages[0].additional_kwargs == {}
    assert seen[0].messages[0].content == "hello"


def test_reasoning_middleware_updates_openai_field_and_extra_body(monkeypatch) -> None:
    monkeypatch.setattr(
        reasoning,
        "get_config",
        lambda: {
            "configurable": {
                reasoning.CONFIG_KEY: {
                    "model_fields": {"reasoning_effort": "high"},
                    "extra_body": {"thinking": {"type": "enabled"}},
                }
            }
        },
    )
    model = ChatOpenAI(model="gpt-5.4", api_key="test")
    request = ModelRequest(model=model, messages=[])

    configured = reasoning._configured_request(request)

    assert configured.model is not model
    assert configured.model.reasoning_effort == "high"
    assert configured.model.extra_body == {"thinking": {"type": "enabled"}}


def test_reasoning_middleware_updates_native_anthropic_fields(monkeypatch) -> None:
    monkeypatch.setattr(
        reasoning,
        "get_config",
        lambda: {
            "configurable": {
                reasoning.CONFIG_KEY: {
                    "model_fields": {
                        "thinking": {"type": "adaptive"},
                        "reasoning_effort": "high",
                    }
                }
            }
        },
    )
    model = ChatAnthropic(model="claude-opus-4-6", api_key="test", max_tokens=1024)
    request = ModelRequest(model=model, messages=[])

    configured = reasoning._configured_request(request)

    assert configured.model.thinking == {"type": "adaptive"}
    assert configured.model.reasoning_effort == "high"


# Offline serialization regression: verify through the real reasoning-aware
# model class shipped in octop-harness, without any network call. Only calling
# _scrub_replayed_reasoning() cannot prove the final serialized assistant
# message matches the gate decision. These cases still say nothing about a
# specific provider endpoint accepting `reasoning_content` — that needs
# per-provider verification (see the plan's follow-up section).


def _capture_payload(messages, monkeypatch):
    """Serialize messages through the real reasoning-aware ChatOpenAI subclass."""
    from langchain_openai import ChatOpenAI
    from octop_harness.llm.factory import _get_reasoning_aware_chat_openai

    monkeypatch.setattr(
        reasoning,
        "get_config",
        lambda: {"configurable": {}},
    )
    cls = _get_reasoning_aware_chat_openai(ChatOpenAI)
    model = cls(model="llama-3.3-70b-versatile", api_key="test")
    request = ModelRequest(model=model, messages=messages)
    return model._get_request_payload(request.messages, stop=None)


def test_outbound_payload_drops_reasoning_when_gate_false(monkeypatch) -> None:
    """issue #2498: an unsupported reasoning_content makes groq answer 400."""
    monkeypatch.setattr(
        reasoning,
        "get_config",
        lambda: {"configurable": {reasoning.ROUNDTRIP_KEY: False}},
    )
    history = [
        HumanMessage(content="q"),
        AIMessage(
            content="a",
            additional_kwargs={"reasoning_content": "thinking", "other": "keep"},
        ),
    ]
    request = ModelRequest(
        model=ChatOpenAI(model="llama-3.3-70b-versatile", api_key="test"),
        messages=history,
    )
    scrubbed = reasoning._scrub_replayed_reasoning(request)
    payload = _capture_payload(scrubbed.messages, monkeypatch)

    outbound = payload["messages"][1]
    assert outbound["role"] == "assistant"
    assert "reasoning_content" not in outbound


def test_outbound_payload_keeps_reasoning_when_gate_true(monkeypatch) -> None:
    """A model confirmed to accept replay keeps the reasoning payload."""
    monkeypatch.setattr(
        reasoning,
        "get_config",
        lambda: {"configurable": {reasoning.ROUNDTRIP_KEY: True}},
    )
    history = [
        HumanMessage(content="q"),
        AIMessage(content="a", additional_kwargs={"reasoning_content": "thinking"}),
    ]
    request = ModelRequest(
        model=ChatOpenAI(model="deepseek-v4", api_key="test"),
        messages=history,
    )
    passthrough = reasoning._scrub_replayed_reasoning(request)
    assert passthrough is request

    payload = _capture_payload(passthrough.messages, monkeypatch)

    outbound = payload["messages"][1]
    assert outbound["role"] == "assistant"
    assert outbound["reasoning_content"] == "thinking"
    # The gate=True case is proven here with the same Llama-class model as
    # gate=False; DeepSeek endpoint compatibility needs separate verification.
