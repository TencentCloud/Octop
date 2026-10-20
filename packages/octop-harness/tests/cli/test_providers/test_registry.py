"""Tests for the provider preset registry."""

from __future__ import annotations

from octop_harness.cli.providers.registry import (
    PROVIDER_PRESETS,
    ModelPreset,
    ProviderPreset,
    get_preset,
    list_presets,
)


def test_registry_not_empty() -> None:
    assert len(PROVIDER_PRESETS) >= 15


def test_each_preset_has_required_fields() -> None:
    for pid, preset in PROVIDER_PRESETS.items():
        assert isinstance(preset, ProviderPreset)
        assert preset.id == pid
        assert preset.name
        assert preset.base_url.startswith("http")
        assert preset.protocol in ("openai", "anthropic")
        assert len(preset.models) >= 1
        for m in preset.models:
            assert isinstance(m, ModelPreset)
            assert m.id
            assert m.name


def test_get_preset_existing() -> None:
    preset = get_preset("deepseek")
    assert preset is not None
    assert preset.name == "DeepSeek"


def test_get_preset_missing() -> None:
    assert get_preset("nonexistent") is None


def test_list_presets_returns_all() -> None:
    presets = list_presets()
    assert len(presets) == len(PROVIDER_PRESETS)
    assert all(isinstance(p, ProviderPreset) for p in presets)


def test_ollama_preset_has_no_api_key_prefix() -> None:
    preset = get_preset("ollama")
    assert preset is not None
    assert preset.api_key_prefix == ""


def test_anthropic_uses_anthropic_protocol() -> None:
    preset = get_preset("anthropic")
    assert preset is not None
    assert preset.protocol == "anthropic"


def test_cli_provider_preset_is_core_type() -> None:
    from octop_harness.cli.providers.registry import ProviderPreset as CliPreset
    from octop_harness.providers import ProviderPreset as CorePreset

    assert CliPreset is CorePreset


def test_cli_model_preset_is_core_type() -> None:
    from octop_harness.cli.providers.registry import ModelPreset as CliPreset
    from octop_harness.providers import ModelPreset as CorePreset

    assert CliPreset is CorePreset
