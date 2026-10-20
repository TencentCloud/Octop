"""Tests for ``octop_harness.config.env``."""

from __future__ import annotations

from importlib import resources
from unittest.mock import patch

from octop_harness.config.env import detect_providers_from_env
from octop_harness.providers import load_provider_templates

_BUNDLED_TEMPLATE = resources.files("octop_harness.providers").joinpath("provider_template.json")


class TestDetectHarnessPrefix:
    def test_harness_provider_single(self) -> None:
        env = {
            "HARNESS_PROVIDER_MYCO_API_KEY": "sk-myco-key",
            "HARNESS_PROVIDER_MYCO_BASE_URL": "https://api.myco.com/v1",
        }
        with patch.dict("os.environ", env, clear=True):
            providers, _default_model = detect_providers_from_env()
        assert any(p.id == "myco" for p in providers)
        myco = next(p for p in providers if p.id == "myco")
        assert myco.api_key == "sk-myco-key"
        assert myco.base_url == "https://api.myco.com/v1"
        assert myco.protocol == "openai"

    def test_harness_provider_with_protocol(self) -> None:
        env = {
            "HARNESS_PROVIDER_CLAUDE_API_KEY": "sk-ant-key",
            "HARNESS_PROVIDER_CLAUDE_BASE_URL": "https://api.anthropic.com/v1",
            "HARNESS_PROVIDER_CLAUDE_PROTOCOL": "anthropic",
        }
        with patch.dict("os.environ", env, clear=True):
            providers, _ = detect_providers_from_env()
        assert next(p for p in providers if p.id == "claude").protocol == "anthropic"

    def test_harness_provider_key_lowercased(self) -> None:
        env = {
            "HARNESS_PROVIDER_MYAPI_API_KEY": "key123",
            "HARNESS_PROVIDER_MYAPI_BASE_URL": "https://api.example.com/v1",
        }
        with patch.dict("os.environ", env, clear=True):
            providers, _ = detect_providers_from_env()
        assert any(p.id == "myapi" for p in providers)

    def test_harness_default_model(self) -> None:
        env = {
            "HARNESS_PROVIDER_FOO_API_KEY": "key",
            "HARNESS_PROVIDER_FOO_BASE_URL": "https://foo.com/v1",
            "HARNESS_DEFAULT_MODEL": "foo/gpt-turbo",
        }
        with patch.dict("os.environ", env, clear=True):
            _providers, default_model = detect_providers_from_env()
        assert default_model == "foo/gpt-turbo"

    def test_no_env_vars_returns_empty(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            providers, default_model = detect_providers_from_env()
        assert providers == []
        assert default_model is None

    def test_harness_provider_missing_base_url_skipped(self) -> None:
        env = {"HARNESS_PROVIDER_NOURL_API_KEY": "key"}
        with patch.dict("os.environ", env, clear=True):
            providers, _ = detect_providers_from_env()
        assert not any(p.id == "nourl" for p in providers)

    def test_lowercase_env_var_not_matched(self) -> None:
        env = {
            "harness_provider_foo_api_key": "key",
            "harness_provider_foo_base_url": "https://foo.com/v1",
        }
        with patch.dict("os.environ", env, clear=True):
            providers, _ = detect_providers_from_env()
        assert not any(p.id == "foo" for p in providers)


class TestDetectOpenAIFallback:
    def test_openai_api_key_creates_provider(self) -> None:
        env = {"OPENAI_API_KEY": "sk-openai-key"}
        with patch.dict("os.environ", env, clear=True):
            providers, _ = detect_providers_from_env()
        assert any(p.id == "openai" for p in providers)
        openai = next(p for p in providers if p.id == "openai")
        assert openai.api_key == "sk-openai-key"
        assert openai.base_url == "https://api.openai.com/v1"

    def test_openai_base_url_override(self) -> None:
        env = {
            "OPENAI_API_KEY": "sk-key",
            "OPENAI_BASE_URL": "https://custom.endpoint.com/v1",
        }
        with patch.dict("os.environ", env, clear=True):
            providers, _ = detect_providers_from_env()
        assert next(p for p in providers if p.id == "openai").base_url == "https://custom.endpoint.com/v1"

    def test_openai_model_name_sets_default_model(self) -> None:
        env = {
            "OPENAI_API_KEY": "sk-key",
            "OPENAI_MODEL_NAME": "gpt-4o-mini",
        }
        with patch.dict("os.environ", env, clear=True):
            providers, default_model = detect_providers_from_env()
        assert default_model == "openai/gpt-4o-mini"
        openai = next(p for p in providers if p.id == "openai")
        assert any(m.id == "gpt-4o-mini" for m in openai.models)

    def test_harness_prefix_wins_over_openai(self) -> None:
        env = {
            "HARNESS_PROVIDER_OPENAI_API_KEY": "harness-key",
            "HARNESS_PROVIDER_OPENAI_BASE_URL": "https://harness.endpoint.com/v1",
            "OPENAI_API_KEY": "standard-key",
        }
        with patch.dict("os.environ", env, clear=True):
            providers, _ = detect_providers_from_env()
        assert next(p for p in providers if p.id == "openai").api_key == "harness-key"

    def test_template_preset_deepseek_detected(self) -> None:
        env = {"DEEPSEEK_API_KEY": "sk-deepseek"}
        with patch.dict("os.environ", env, clear=True):
            providers, _ = detect_providers_from_env()
        assert any(p.id == "deepseek" for p in providers)
        deepseek = next(p for p in providers if p.id == "deepseek")
        assert deepseek.base_url == "https://api.deepseek.com/v1"
        assert deepseek.api_key == "sk-deepseek"

    def test_sole_provider_default_model_auto_set(self) -> None:
        env = {"DEEPSEEK_API_KEY": "sk-deepseek"}
        with patch.dict("os.environ", env, clear=True):
            _providers, default_model = detect_providers_from_env()
        assert default_model is not None
        assert default_model.startswith("deepseek/")

    def test_harness_default_model_takes_priority(self) -> None:
        env = {
            "OPENAI_API_KEY": "sk-key",
            "OPENAI_MODEL_NAME": "gpt-4o",
            "HARNESS_DEFAULT_MODEL": "openai/gpt-4o-mini",
        }
        with patch.dict("os.environ", env, clear=True):
            _, default_model = detect_providers_from_env()
        assert default_model == "openai/gpt-4o-mini"


class TestTemplatePresetModelInput:
    def test_tencent_hai_propagates_image_input(self, monkeypatch) -> None:
        presets = load_provider_templates(templates_path=_BUNDLED_TEMPLATE)
        monkeypatch.setattr("octop_harness.config.env._load_template_presets", lambda: presets)
        env = {"TENCENT_HAI_API_KEY": "sk-hai"}
        with patch.dict("os.environ", env, clear=True):
            providers, _ = detect_providers_from_env()
        hai = next(p for p in providers if p.id == "tencent-hai")
        kimi = next(m for m in hai.models if m.id == "Kimi-K2.5")
        assert kimi.input == ["text", "image"]
        assert kimi.is_multimodal is True

    def test_openai_preset_propagates_image_input(self, monkeypatch) -> None:
        presets = load_provider_templates(templates_path=_BUNDLED_TEMPLATE)
        monkeypatch.setattr("octop_harness.config.env._load_template_presets", lambda: presets)
        env = {"OPENAI_API_KEY": "sk-openai"}
        with patch.dict("os.environ", env, clear=True):
            providers, _ = detect_providers_from_env()
        openai = next(p for p in providers if p.id == "openai")
        gpt4o = next(m for m in openai.models if m.id == "gpt-4o")
        assert gpt4o.input == ["text", "image"]
