from langchain.agents.middleware import ModelRequest
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, HumanMessage
from langchain_openai import ChatOpenAI

from octop.infra.agents.middleware import reasoning


def test_scrubs_replayed_reasoning_when_capability_absent(monkeypatch) -> None:
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


def test_scrub_defaults_to_roundtrip_when_gate_absent(monkeypatch) -> None:
    monkeypatch.setattr(
        reasoning,
        "get_config",
        lambda: {"configurable": {}},
    )
    request = ModelRequest(
        model=ChatOpenAI(model="llama-3.3-70b-versatile", api_key="test"),
        messages=[AIMessage(content="hello", additional_kwargs={"reasoning_content": "x"})],
    )

    assert reasoning._scrub_replayed_reasoning(request) is request


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
