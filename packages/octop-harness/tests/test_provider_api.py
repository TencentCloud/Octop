# tests/test_provider_api.py
from __future__ import annotations

from octop_harness.providers import ModelPreset, ProviderPreset, serialize_model_preset, serialize_provider_preset


def test_serialize_model_includes_input() -> None:
    m = ModelPreset("kimi-k2.5", "Kimi K2.5", 131072, input=("text", "image"))
    out = serialize_model_preset(m)
    assert out["input"] == ["text", "image"]
    assert "input" not in serialize_model_preset(ModelPreset("x", "X"))


def test_serialize_model_keeps_token_limits_distinct() -> None:
    m = ModelPreset(
        "deepseek-v4-pro",
        "DeepSeek V4 Pro",
        900_000,
        context_window=1_000_000,
        max_output_tokens=384_000,
    )
    out = serialize_model_preset(m)
    assert out["max_input_tokens"] == 900_000
    assert out["context_window"] == 1_000_000
    assert out["max_output_tokens"] == 384_000


def test_serialize_model_includes_reasoning() -> None:
    m = ModelPreset("deepseek-reasoner", "DeepSeek Reasoner", reasoning=True)
    assert serialize_model_preset(m)["reasoning"] is True
    assert "reasoning" not in serialize_model_preset(ModelPreset("deepseek-chat", "DeepSeek Chat"))


def test_serialize_provider_maps_vendor_aliases() -> None:
    p = ProviderPreset(
        id="kimi-cn",
        name="Kimi (China)",
        base_url="https://api.moonshot.cn/v1",
        vendor="kimi",
        vendor_name="Kimi",
        variant="open_platform_cn",
        logo="moonshot.webp",
        models=[ModelPreset("kimi-k2.5", "Kimi K2.5", 131072, input=("text", "image"))],
    )
    out = serialize_provider_preset(p)
    assert out["vendor"] == "kimi"
    assert out["provider_group"] == "kimi"
    assert out["provider_variant"] == "open_platform_cn"
    assert out["logo_id"] == "moonshot"
    assert out["models"][0]["input"] == ["text", "image"]
