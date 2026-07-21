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
    reasoner = next(m for m in deepseek["models"] if m["id"] == "deepseek-reasoner")
    assert reasoner.get("reasoning") is True

    token_plan = next(p for p in presets if p["id"] == "tencent-token-plan")
    token_ids = {m["id"] for m in token_plan["models"]}
    # Match by prefix: harness-agent tags token-plan model ids with a release
    # date suffix (e.g. deepseek-v4-flash-202605) and bumps the Kimi minor
    # version over time, so assert the model family is present rather than an
    # exact id that drifts with every upstream release.
    assert any(mid.startswith("deepseek-v4-flash") for mid in token_ids)
    assert any(mid.startswith("kimi-k2") for mid in token_ids)
    assert token_plan.get("vendor") == "tencent"
    assert token_plan.get("provider_group") == "tencent"

    coding_plan = next(p for p in presets if p["id"] == "tencent-coding-plan")
    assert "kimi-k2.5" in {m["id"] for m in coding_plan["models"]}

    openai = next(p for p in presets if p["id"] == "openai")
    gpt4o = next(m for m in openai["models"] if m["id"] == "gpt-4o")
    assert gpt4o.get("input") == ["text", "image"]

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
