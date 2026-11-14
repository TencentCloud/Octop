"""LLMTR is a named OpenAI-compatible preset added in this repository."""

from __future__ import annotations

from octop.infra.agents.providers.presets import load_provider_presets


def test_llmtr_preset_is_openai_compatible() -> None:
    presets = load_provider_presets()
    matches = [p for p in presets if p["id"] == "llmtr"]
    assert len(matches) == 1
    llmtr = matches[0]
    assert llmtr["name"] == "LLMTR"
    assert llmtr["base_url"] == "https://llmtr.com/v1"
    assert llmtr["protocol"] == "openai"
    assert llmtr.get("models") == []
    assert not llmtr.get("logo_id")
