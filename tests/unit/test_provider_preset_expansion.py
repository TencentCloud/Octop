"""Unit tests for harness-backed provider presets."""

from __future__ import annotations

from octop.infra.agents.providers.presets import load_provider_presets


def test_load_provider_presets_integration() -> None:
    presets = load_provider_presets()
    ids = {p["id"] for p in presets}
    assert "moonshot" not in ids
    assert "kimi-cn" in ids
    assert "minimax-intl" in ids
    assert "zhipu-intl-codingplan" in ids
    assert "siliconflow-intl" in ids

    deepseek = next(p for p in presets if p["id"] == "deepseek")
    deepseek_ids = {m["id"] for m in deepseek["models"]}
    assert "deepseek-v4-flash" in deepseek_ids
    assert "deepseek-v4-pro" in deepseek_ids
    flash = next(m for m in deepseek["models"] if m["id"] == "deepseek-v4-flash")
    assert flash["reasoning_config"]["adapter"] == "thinking"

    token_plan = next(p for p in presets if p["id"] == "tencent-token-plan")
    token_ids = {m["id"] for m in token_plan["models"]}
    # Match by prefix: harness-agent tags token-plan model ids with a release
    # date suffix (e.g. deepseek-v4-flash-202605) and bumps catalog entries
    # over time, so assert the model family is present rather than an exact id.
    assert any(mid.startswith("deepseek-v4-flash") for mid in token_ids)
    assert any(mid.startswith("deepseek-v4-pro") for mid in token_ids)
    assert token_plan.get("vendor") == "tencent"
    assert token_plan.get("provider_group") == "tencent"
    token_deepseek = next(m for m in token_plan["models"] if m["id"].startswith("deepseek-v4"))
    assert token_deepseek["reasoning_config"]["adapter"] == "thinking_nested_effort"

    coding_plan = next(p for p in presets if p["id"] == "tencent-coding-plan")
    assert "kimi-k2.5" in {m["id"] for m in coding_plan["models"]}

    openai = next(p for p in presets if p["id"] == "openai")
    gpt4o = next(m for m in openai["models"] if m["id"] == "gpt-4o")
    assert gpt4o.get("input") == ["text", "image"]
    gpt5 = next(m for m in openai["models"] if m["id"] == "gpt-5")
    assert gpt5["reasoning_config"]["adapter"] == "openai_reasoning_effort"

    kimi_cn = next(p for p in presets if p["id"] == "kimi-cn")
    kimi_k25 = next(m for m in kimi_cn["models"] if m["id"] == "kimi-k2.5")
    assert kimi_k25.get("input") == ["text", "image"]
    assert kimi_cn.get("vendor") == "kimi"

    volc_open = next(p for p in presets if p["id"] == "volcengine-cn")
    assert len(volc_open["models"]) >= 8

    coding = next(p for p in presets if p["id"] == "volcengine-cn-codingplan")
    coding_ids = {m["id"] for m in coding["models"]}
    assert "DeepSeek-V4-Flash" in coding_ids
    assert "kimi-k2.6" in coding_ids

    assert {"opencode-zen-openai", "opencode-zen-anthropic", "opencode-go"} <= ids
    assert {"opencode-go-openai", "opencode-go-anthropic"}.isdisjoint(ids)

    zen_oai = next(p for p in presets if p["id"] == "opencode-zen-openai")
    assert zen_oai["base_url"] == "https://opencode.ai/zen/v1"
    assert zen_oai.get("provider_group") == "opencode"
    assert zen_oai.get("provider_variant") == "zen_compatible"
    assert zen_oai.get("protocol") == "openai"

    zen_ant = next(p for p in presets if p["id"] == "opencode-zen-anthropic")
    assert zen_ant["base_url"] == "https://opencode.ai/zen"
    assert zen_ant.get("protocol") == "anthropic"

    go = next(p for p in presets if p["id"] == "opencode-go")
    assert go["name"] == "opencode-go"
    assert go["base_url"] == "https://opencode.ai/zen/go/v1"
    assert go.get("protocol") == "openai"
    assert go.get("provider_group") == "opencode"
    assert go.get("provider_variant") == "go"

    by_wire: dict[str, set[str]] = {}
    for model in go["models"]:
        by_wire.setdefault(model["wire_api"], set()).add(model["id"])
    assert by_wire == {
        "openai_responses": {
            "grok-4.6",
            "gpt-5.6-luna",
            "muse-spark-1.2-contributor",
        },
        "openai_chat_completions": {
            "glm-5.3-flash",
            "glm-5.3",
            "glm-5.2",
            "glm-5.1",
            "kimi-k3",
            "kimi-k2.7-code",
            "kimi-k2.6",
            "longcat-2.0",
            "deepseek-v4-pro",
            "deepseek-v4-flash",
            "deepseek-v4-flash-vision-exp",
            "mimo-v2.5",
            "mimo-v2.5-pro",
            "hy3",
        },
        "anthropic_messages": {
            "minimax-m3",
            "minimax-m2.7",
            "qwen3.8-max",
            "qwen3.7-max",
            "qwen3.7-plus",
            "qwen3.6-plus",
        },
    }
    assert len(go["models"]) == 23
    assert not any(model["id"] == "minimax-m2.5" for model in go["models"])

    grok = next(m for m in go["models"] if m["id"] == "grok-4.6")
    assert grok["context_window"] == 500_000
    assert grok["max_output_tokens"] == 500_000
    assert grok["input"] == ["text", "image"]
    assert grok["reasoning_config"]["adapter"] == "openai_reasoning_effort"

    luna = next(m for m in go["models"] if m["id"] == "gpt-5.6-luna")
    assert luna["max_input_tokens"] == 922_000

    glm52 = next(m for m in go["models"] if m["id"] == "glm-5.2")
    assert glm52["max_input_tokens"] == 262_144
    assert glm52["context_window"] == 1_000_000

    minimax_m3 = next(m for m in go["models"] if m["id"] == "minimax-m3")
    assert minimax_m3.get("input", ["text"]) == ["text"]

    qwen = next(m for m in go["models"] if m["id"] == "qwen3.8-max")
    assert "endpoint_base_url" not in qwen
