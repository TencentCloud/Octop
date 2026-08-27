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
    assert token_ids == {
        "tc-code-latest",
        "deepseek-v4-flash-202605",
        "deepseek-v4-pro-202606",
        "minimax-m2.7",
        "glm-5",
        "glm-5.1",
        "glm-5.2",
    }
    assert token_plan.get("vendor") == "tencent"
    assert token_plan.get("provider_group") == "tencent"
    assert token_plan.get("provider_variant") == "token_plan"
    token_deepseek = next(m for m in token_plan["models"] if m["id"].startswith("deepseek-v4"))
    assert token_deepseek["reasoning_config"]["adapter"] == "thinking_nested_effort"

    enterprise = next(p for p in presets if p["id"] == "tencent-token-plan-enterprise-cn")
    enterprise_ids = {m["id"] for m in enterprise["models"]}
    assert enterprise["base_url"] == "https://tokenhub.tencentmaas.com/plan/v3"
    assert enterprise.get("provider_group") == "tencent"
    assert enterprise.get("provider_variant") == "token_plan_enterprise_cn"
    assert enterprise_ids == {
        "auto",
        "deepseek-v4-flash",
        "deepseek-v4-flash-0731",
        "deepseek-v4-flash-202605",
        "deepseek-v4-pro",
        "deepseek-v4-pro-0813",
        "deepseek-v4-pro-202606",
        "glm-5",
        "glm-5-turbo",
        "glm-5.1",
        "glm-5.2",
        "glm-5.3",
        "kimi-k2.5",
        "kimi-k2.6",
        "kimi-k2.7-code",
        "kimi-k2.7-code-highspeed",
        "minimax-m2.5",
        "minimax-m2.7",
        "minimax-m3",
    }
    assert not any("/" in model_id for model_id in enterprise_ids)
    enterprise_deepseek = next(
        m for m in enterprise["models"] if m["id"] == "deepseek-v4-pro-202606"
    )
    assert enterprise_deepseek["reasoning_config"]["adapter"] == "thinking_nested_effort"

    hy_plan = next(p for p in presets if p["id"] == "tencent-hy-token-plan")
    assert hy_plan["base_url"] == "https://api.lkeap.cloud.tencent.com/plan/v3"
    assert hy_plan.get("provider_group") == "tencent"
    assert hy_plan.get("provider_variant") == "hy_token_plan"
    assert {m["id"] for m in hy_plan["models"]} == {"hy3", "hy3-preview"}
    assert all(m["reasoning_config"]["adapter"] == "status_only" for m in hy_plan["models"])

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

    opencode_ids = {
        "opencode-zen-openai",
        "opencode-zen-anthropic",
        "opencode-go-openai",
        "opencode-go-anthropic",
    }
    assert opencode_ids <= ids

    zen_oai = next(p for p in presets if p["id"] == "opencode-zen-openai")
    assert zen_oai["base_url"] == "https://opencode.ai/zen/v1"
    assert zen_oai.get("provider_group") == "opencode"
    assert zen_oai.get("provider_variant") == "zen_compatible"
    assert zen_oai.get("protocol") == "openai"

    zen_ant = next(p for p in presets if p["id"] == "opencode-zen-anthropic")
    assert zen_ant["base_url"] == "https://opencode.ai/zen"
    assert zen_ant.get("protocol") == "anthropic"

    go_oai = next(p for p in presets if p["id"] == "opencode-go-openai")
    assert go_oai["base_url"] == "https://opencode.ai/zen/go/v1"

    go_ant = next(p for p in presets if p["id"] == "opencode-go-anthropic")
    assert go_ant["base_url"] == "https://opencode.ai/zen/go"
