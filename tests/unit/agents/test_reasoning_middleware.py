from langchain.agents.middleware import ModelRequest
from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI

from octop.infra.agents.middleware import reasoning


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
