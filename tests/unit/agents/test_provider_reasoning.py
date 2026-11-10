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
    for base_url in (
        "https://api.lkeap.cloud.tencent.com/plan/v3",
        "https://tokenhub.tencentmaas.com/plan/v3",
    ):
        capability = reasoning_capability(
            {
                "id": "deepseek-v4-pro-202606",
                "options": {"thinking": {"type": "enabled"}},
            },
            base_url=base_url,
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


def _llamacpp_capability(**overrides: object) -> dict:
    config = {
        "supported": True,
        "toggle": True,
        "default_mode": "enabled",
        "efforts": ["low", "medium", "xhigh"],
        "default_effort": "medium",
        "effort_type": "enum",
        "adapter": "llamacpp",
    }
    config.update(overrides)
    capability = reasoning_capability({"id": "local-llama", "reasoning_config": config})
    assert capability is not None
    return capability


def test_llamacpp_capability_accepts_reasoning_config() -> None:
    capability = _llamacpp_capability()
    assert capability["adapter"] == "llamacpp"
    assert capability["toggle"] is True
    assert capability["default_mode"] == "enabled"
    assert capability["efforts"] == ["low", "medium", "xhigh"]
    assert capability["default_effort"] == "medium"
    assert capability["effort_type"] == "enum"


def test_llamacpp_disable_uses_chat_template_kwargs_and_none_effort() -> None:
    capability = _llamacpp_capability()
    expected = {
        "extra_body": {
            "chat_template_kwargs": {"enable_thinking": False},
            "reasoning_effort": "none",
        }
    }
    for effort in (None, "high"):
        params = reasoning_request_parameters(capability, mode="disabled", effort=effort)
        assert params == expected
        assert "thinking" not in params["extra_body"]


def test_llamacpp_enable_keeps_requested_effort() -> None:
    capability = _llamacpp_capability(efforts=["low", "medium", "high", "xhigh"])
    assert reasoning_request_parameters(capability, mode="enabled", effort="high") == {
        "extra_body": {
            "chat_template_kwargs": {"enable_thinking": True},
            "reasoning_effort": "high",
        }
    }


def test_llamacpp_auto_omits_enable_thinking() -> None:
    capability = _llamacpp_capability()
    params = reasoning_request_parameters(capability, mode="auto", effort="low")
    assert params == {"extra_body": {"reasoning_effort": "low"}}
    assert "enable_thinking" not in params["extra_body"].get("chat_template_kwargs", {})


def test_llamacpp_token_budget_uses_reasoning_budget_tokens() -> None:
    capability = _llamacpp_capability(
        effort_type="token_budget",
        efforts=["4096", "8192"],
        default_effort="4096",
    )
    params = reasoning_request_parameters(capability, mode="enabled", effort="4096")
    assert params == {
        "extra_body": {
            "chat_template_kwargs": {"enable_thinking": True},
            "reasoning_budget_tokens": 4096,
        }
    }
    assert "thinking" not in params["extra_body"]


def test_llamacpp_legacy_model_uses_local_port_adapter() -> None:
    capability = reasoning_capability(
        {"id": "local-llama-3.1-8b", "reasoning": True},
        base_url="http://127.0.0.1:18202/v1",
    )
    assert capability is not None
    assert capability["adapter"] == "llamacpp"
