from octop.infra.agents.providers.reasoning import (
    reasoning_capability,
    reasoning_request_parameters,
)


def test_reasoning_capability_accepts_token_plan_thinking_option() -> None:
    capability = reasoning_capability({"id": "glm-5", "options": {"thinking": {"type": "enabled"}}})
    assert capability is not None
    assert capability["toggle"] is True
    assert capability["default_mode"] == "enabled"


def test_known_token_plan_model_is_detected_without_saved_metadata() -> None:
    capability = reasoning_capability({"id": "kimi-k2.5"})
    assert capability is not None
    assert capability["toggle"] is True
    assert capability["default_mode"] == "enabled"


def test_minimax_token_plan_reasoning_is_always_on() -> None:
    capability = reasoning_capability(
        {"id": "minimax-m2.7", "options": {"thinking": {"type": "enabled"}}}
    )
    assert capability is not None
    assert capability["toggle"] is False
    assert capability["default_mode"] == "enabled"


def test_deepseek_v4_uses_nested_effort_parameter() -> None:
    capability = reasoning_capability(
        {
            "id": "deepseek-v4-pro-202606",
            "options": {"thinking": {"type": "enabled"}},
        },
        base_url="https://api.lkeap.cloud.tencent.com/plan/v3",
    )
    assert capability is not None
    assert capability["efforts"] == ["high", "max"]
    assert reasoning_request_parameters(capability, mode="enabled", effort="max") == {
        "extra_body": {"thinking": {"type": "enabled", "reasoning_effort": "max"}}
    }


def test_explicit_capability_filters_unsupported_effort() -> None:
    capability = reasoning_capability(
        {
            "id": "reasoner",
            "reasoning_config": {
                "supported": True,
                "toggle": True,
                "efforts": ["low", "high"],
            },
        }
    )
    assert reasoning_request_parameters(capability, mode="disabled", effort="max") == {
        "extra_body": {"thinking": {"type": "disabled"}}
    }


def test_openai_adapter_maps_disable_to_none_effort_without_thinking() -> None:
    capability = reasoning_capability(
        {
            "id": "gpt-5.4",
            "reasoning_config": {
                "adapter": "openai_reasoning_effort",
                "efforts": ["low", "medium", "high", "xhigh"],
            },
        }
    )
    assert reasoning_request_parameters(capability, mode="disabled", effort=None) == {
        "model_fields": {"reasoning_effort": "none"}
    }


def test_anthropic_adaptive_uses_native_model_fields() -> None:
    capability = reasoning_capability(
        {
            "id": "claude-opus-4-6",
            "reasoning_config": {
                "adapter": "anthropic_adaptive",
                "efforts": ["low", "medium", "high", "max"],
            },
        }
    )
    assert reasoning_request_parameters(capability, mode="enabled", effort="high") == {
        "model_fields": {"thinking": {"type": "adaptive"}, "reasoning_effort": "high"}
    }


def test_dashscope_token_budget_uses_compatible_body_fields() -> None:
    capability = reasoning_capability(
        {
            "id": "qwen3.5-plus",
            "reasoning_config": {
                "adapter": "dashscope",
                "effort_type": "token_budget",
                "efforts": ["4096", "8192"],
            },
        }
    )
    assert reasoning_request_parameters(capability, mode="enabled", effort="8192") == {
        "extra_body": {"enable_thinking": True, "thinking_budget": 8192}
    }


def test_openrouter_uses_normalized_reasoning_object() -> None:
    capability = reasoning_capability(
        {
            "id": "anthropic/claude-sonnet-4",
            "reasoning_config": {
                "adapter": "openrouter",
                "efforts": ["low", "medium", "high"],
            },
        }
    )
    assert reasoning_request_parameters(capability, mode="enabled", effort="high") == {
        "extra_body": {"reasoning": {"enabled": True, "effort": "high"}}
    }


def test_status_only_model_does_not_emit_fake_controls() -> None:
    capability = reasoning_capability(
        {
            "id": "minimax-m2.7",
            "reasoning_config": {
                "adapter": "status_only",
                "toggle": False,
                "efforts": ["low", "high"],
            },
        }
    )
    assert capability is not None
    assert capability["efforts"] == []
    assert reasoning_request_parameters(capability, mode="disabled", effort="high") == {}
