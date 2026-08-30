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
    assert "tc-code-latest" in token_ids
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
    assert {"auto", "deepseek-v4-flash", "deepseek-v4-pro", "kimi-k2.5"} <= enterprise_ids
    assert any(mid.startswith("glm-5") for mid in enterprise_ids)
    assert any(mid.startswith("minimax-m") for mid in enterprise_ids)
    # Enterprise ids are bare model names, not vendor-prefixed routes.
    assert not any("/" in model_id for model_id in enterprise_ids)
    enterprise_deepseek = next(
        m for m in enterprise["models"] if m["id"].startswith("deepseek-v4-pro")
    )
    assert enterprise_deepseek["reasoning_config"]["adapter"] == "thinking_nested_effort"

    hy_plan = next(p for p in presets if p["id"] == "tencent-hy-token-plan")
    assert hy_plan["base_url"] == "https://api.lkeap.cloud.tencent.com/plan/v3"
    assert hy_plan.get("provider_group") == "tencent"
    assert hy_plan.get("provider_variant") == "hy_token_plan"
    hy_ids = {m["id"] for m in hy_plan["models"]}
    assert {"hy3", "hy3-preview"} <= hy_ids
    hy3 = next(m for m in hy_plan["models"] if m["id"] == "hy3")
    assert hy3["reasoning_config"]["adapter"] == "status_only"

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
