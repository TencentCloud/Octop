# tests/test_provider_preset_core.py
from __future__ import annotations

import json
from importlib import resources
from pathlib import Path

import pytest

from octop_harness.providers import ModelPreset, ProviderPreset, load_provider_templates

_BUNDLED_TEMPLATE = resources.files("octop_harness.providers").joinpath("provider_template.json")


class TestCoreProviderPresets:
    def test_model_preset_dataclass(self) -> None:
        m = ModelPreset(id="gpt-4o", name="GPT-4o", input=("text", "image"))
        assert m.id == "gpt-4o"
        assert m.name == "GPT-4o"
        assert m.input == ("text", "image")
        assert m.is_multimodal is True

    def test_model_preset_defaults_to_text_only(self) -> None:
        m = ModelPreset(id="deepseek-chat", name="DeepSeek Chat")
        assert m.input == ("text",)
        assert m.is_multimodal is False
        assert m.reasoning is False

    def test_model_preset_reasoning_flag(self) -> None:
        m = ModelPreset(id="deepseek-reasoner", name="DeepSeek Reasoner", reasoning=True)
        assert m.reasoning is True

    def test_provider_preset_dataclass(self) -> None:
        p = ProviderPreset(
            id="openai",
            name="OpenAI",
            base_url="https://api.openai.com/v1",
        )
        assert p.id == "openai"
        assert p.protocol == "openai"  # default value

    def test_load_builtin_templates(self) -> None:
        presets = load_provider_templates()
        assert isinstance(presets, list)
        assert len(presets) >= 17
        ids = {p.id for p in presets}
        assert "deepseek" in ids
        assert "openai" in ids

    def test_bundled_templates_use_vendor_sites(self) -> None:
        presets = load_provider_templates(templates_path=_BUNDLED_TEMPLATE)
        ids = {p.id for p in presets}
        assert "kimi-cn" in ids
        assert "moonshot" not in ids
        kimi = next(p for p in presets if p.id == "kimi-cn")
        assert kimi.vendor == "kimi"
        assert kimi.variant == "open_platform_cn"

    def test_bundled_templates_include_iflytek_astron_token_plan(self) -> None:
        presets = {p.id: p for p in load_provider_templates(templates_path=_BUNDLED_TEMPLATE)}
        token = presets["iflytek-astron-token-plan"]
        assert token.base_url == "https://maas-token-api.cn-huabei-1.xf-yun.com/v2"
        assert token.protocol == "openai"
        assert token.vendor == "iflytek"
        assert token.vendor_name == "iFlytek Astron"
        assert token.variant == "token_plan"
        assert token.models[0].id == "spark-x2.5"
        models = {m.id: m for m in token.models}
        assert models["xopkimik26"].is_multimodal is True
        assert models["spark-x2.5"].is_multimodal is False
        logo = resources.files("octop_harness.providers.logos").joinpath(token.logo)
        assert logo.is_file()

    def test_load_custom_path(self, tmp_path: Path) -> None:
        custom = tmp_path / "my_providers.json"
        custom.write_text(
            json.dumps(
                [
                    {
                        "id": "custom",
                        "name": "Custom",
                        "base_url": "https://custom.example/v1",
                        "protocol": "openai",
                        "api_key_env": "CUSTOM_API_KEY",
                        "api_key_prefix": "",
                        "models": [{"id": "m1", "name": "Model One"}],
                    }
                ]
            ),
            encoding="utf-8",
        )
        presets = load_provider_templates(templates_path=custom)
        assert len(presets) == 1
        assert presets[0].id == "custom"
        assert presets[0].models[0].id == "m1"
        assert presets[0].models[0].input == ("text",)

    def test_load_custom_path_with_input_modalities(self, tmp_path: Path) -> None:
        custom = tmp_path / "my_providers.json"
        custom.write_text(
            json.dumps(
                [
                    {
                        "id": "custom",
                        "name": "Custom",
                        "base_url": "https://custom.example/v1",
                        "protocol": "openai",
                        "api_key_env": "CUSTOM_API_KEY",
                        "api_key_prefix": "",
                        "models": [
                            {
                                "id": "vision",
                                "name": "Vision",
                                "input": ["text", "image"],
                            }
                        ],
                    }
                ]
            ),
            encoding="utf-8",
        )
        presets = load_provider_templates(templates_path=custom)
        assert presets[0].models[0].input == ("text", "image")

    def test_load_custom_path_with_reasoning_flag(self, tmp_path: Path) -> None:
        custom = tmp_path / "reasoning.json"
        custom.write_text(
            json.dumps(
                [
                    {
                        "id": "custom",
                        "name": "Custom",
                        "base_url": "https://custom.example/v1",
                        "models": [
                            {
                                "id": "deepseek-reasoner",
                                "name": "DeepSeek Reasoner",
                                "reasoning": True,
                            }
                        ],
                    }
                ]
            ),
            encoding="utf-8",
        )
        presets = load_provider_templates(templates_path=custom)
        assert presets[0].models[0].reasoning is True

    def test_load_custom_path_rejects_invalid_input_modality(self, tmp_path: Path) -> None:
        custom = tmp_path / "my_providers.json"
        custom.write_text(
            json.dumps(
                [
                    {
                        "id": "custom",
                        "name": "Custom",
                        "base_url": "https://custom.example/v1",
                        "protocol": "openai",
                        "api_key_env": "CUSTOM_API_KEY",
                        "api_key_prefix": "",
                        "models": [
                            {
                                "id": "bad",
                                "name": "Bad",
                                "input": ["text", "smell"],
                            }
                        ],
                    }
                ]
            ),
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match=r"invalid input modality 'smell'"):
            load_provider_templates(templates_path=custom)

    def test_deepseek_bundle_only_lists_current_v4_models(self) -> None:
        presets = {p.id: p for p in load_provider_templates(templates_path=_BUNDLED_TEMPLATE)}
        ds = presets["deepseek"]
        assert {m.id for m in ds.models} == {"deepseek-v4-flash", "deepseek-v4-pro"}
        assert {m.max_input_tokens for m in ds.models} == {1_000_000}
        assert {m.max_output_tokens for m in ds.models} == {384_000}

    def test_hai_kimi_k25_supports_image(self) -> None:
        presets = {p.id: p for p in load_provider_templates(templates_path=_BUNDLED_TEMPLATE)}
        hai = presets["tencent-hai"]
        models = {m.id: m for m in hai.models}
        kimi = models["Kimi-K2.5"]
        assert kimi.input == ("text", "image")
        assert kimi.is_multimodal is True
        assert kimi.max_input_tokens == 262_144
        assert models["MiniMax-M2.7"].max_input_tokens == 204_800
        assert models["GLM-5.1-FP8"].max_input_tokens == 200_000
        assert models["Qwen3.5-397B-A17B-FP8"].max_input_tokens == 262_144
        assert models["Qwen3.5-397B-A17B-FP8"].input == ("text", "image")
        assert models["Qwen3-32B-FP8"].max_input_tokens == 40_960
        assert models["Qwen3-VL-32B-Instruct-FP8"].max_input_tokens == 262_144
        assert models["Qwen2.5-VL-32B-Instruct"].max_input_tokens == 32_768
        assert models["Qwen3-VL-2B-Instruct"].max_input_tokens == 262_144
        # HAI-hosted DeepSeek routes keep their platform cap instead of
        # inheriting the direct DeepSeek API's 1M context window.
        assert models["DeepSeek-V4-Pro"].max_input_tokens == 128_000

    def test_openai_gpt4o_supports_image(self) -> None:
        presets = {p.id: p for p in load_provider_templates(templates_path=_BUNDLED_TEMPLATE)}
        openai = presets["openai"]
        gpt4o = next(m for m in openai.models if m.id == "gpt-4o")
        assert gpt4o.input == ("text", "image")

    def test_load_missing_path_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_provider_templates(templates_path=tmp_path / "nonexistent.json")

    def test_load_invalid_json_raises_value_error(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.json"
        bad.write_text("not valid json {{", encoding="utf-8")
        with pytest.raises(ValueError, match=r"Invalid JSON"):
            load_provider_templates(templates_path=bad)

    def test_load_non_list_json_raises_value_error(self, tmp_path: Path) -> None:
        bad = tmp_path / "obj.json"
        bad.write_text(json.dumps({"key": "value"}), encoding="utf-8")
        with pytest.raises(ValueError, match=r"Expected a JSON array"):
            load_provider_templates(templates_path=bad)

    def test_load_missing_required_field_raises_value_error(self, tmp_path: Path) -> None:
        bad = tmp_path / "missing_field.json"
        bad.write_text(json.dumps([{"id": "test"}]), encoding="utf-8")
        with pytest.raises(ValueError, match=r"Invalid provider preset"):
            load_provider_templates(templates_path=bad)

    def test_deepseek_preset_fields(self) -> None:
        presets = {p.id: p for p in load_provider_templates(templates_path=_BUNDLED_TEMPLATE)}
        ds = presets["deepseek"]
        assert ds.base_url == "https://api.deepseek.com/v1"
        assert ds.api_key_env == "DEEPSEEK_API_KEY"
        assert len(ds.models) >= 2
        v4 = {model.id: model for model in ds.models if model.id.startswith("deepseek-v4-")}
        assert {model.max_input_tokens for model in v4.values()} == {1_000_000}
        assert {model.max_output_tokens for model in v4.values()} == {384_000}

    def test_tencent_token_plan_excludes_retired_and_not_yet_available_models(self) -> None:
        presets = {p.id: p for p in load_provider_templates(templates_path=_BUNDLED_TEMPLATE)}
        token_plan = presets["tencent-token-plan"]
        models = {model.id: model for model in token_plan.models}
        assert token_plan.base_url == "https://api.lkeap.cloud.tencent.com/plan/v3"
        assert token_plan.api_key_prefix == "sk-tp-"
        assert set(models) == {
            "tc-code-latest",
            "minimax-m2.7",
            "glm-5",
            "glm-5.1",
            "glm-5.2",
            "deepseek-v4-flash-202605",
            "deepseek-v4-pro-202606",
        }
        assert models["glm-5.2"].max_input_tokens == 1_000_000
        assert models["deepseek-v4-pro-202606"].max_output_tokens == 384_000
        assert all(model.reasoning for model_id, model in models.items() if model_id != "tc-code-latest")

    def test_tencent_enterprise_and_hy_token_plan_presets(self) -> None:
        presets = {p.id: p for p in load_provider_templates(templates_path=_BUNDLED_TEMPLATE)}

        enterprise = presets["tencent-token-plan-enterprise-cn"]
        assert enterprise.name == "Tencent Cloud Token Plan Enterprise"
        assert enterprise.base_url == "https://tokenhub.tencentmaas.com/plan/v3"
        assert enterprise.protocol == "openai"
        assert enterprise.api_key_prefix == "sk-tp-"
        assert enterprise.variant == "token_plan_enterprise_cn"
        enterprise_models = {model.id: model for model in enterprise.models}
        assert set(enterprise_models) == {
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
        assert enterprise_models["glm-5.3"].max_input_tokens == 1_000_000
        assert enterprise_models["deepseek-v4-pro-0813"].max_output_tokens == 384_000
        assert enterprise_models["kimi-k2.6"].is_multimodal is True
        assert not any("/" in model_id for model_id in enterprise_models)

        hy_plan = presets["tencent-hy-token-plan"]
        assert hy_plan.base_url == "https://api.lkeap.cloud.tencent.com/plan/v3"
        assert hy_plan.variant == "hy_token_plan"
        assert {model.id for model in hy_plan.models} == {"hy3", "hy3-preview"}
        assert {model.max_input_tokens for model in hy_plan.models} == {256_000}
        assert {model.max_output_tokens for model in hy_plan.models} == {64_000}

    def test_zhipu_glm_context_windows_match_provider_catalog(self) -> None:
        presets = {p.id: p for p in load_provider_templates(templates_path=_BUNDLED_TEMPLATE)}
        for provider_id in (
            "zhipu-cn",
            "zhipu-intl",
            "zhipu-cn-codingplan",
            "zhipu-intl-codingplan",
        ):
            models = {model.id: model for model in presets[provider_id].models}
            assert models["glm-5.1"].max_input_tokens == 200_000
            assert models["glm-5.2"].max_input_tokens == 1_000_000
            assert models["glm-5.2"].max_output_tokens == 131_072

    def test_kimi_minimax_mimo_and_aliyun_catalog_limits(self) -> None:
        presets = {p.id: p for p in load_provider_templates(templates_path=_BUNDLED_TEMPLATE)}

        for provider_id in ("kimi-cn", "kimi-intl"):
            models = {model.id: model for model in presets[provider_id].models}
            assert models["kimi-k3"].max_input_tokens == 1_000_000
            assert models["kimi-k2.7-code"].max_input_tokens == 262_144
            assert models["kimi-k2.5"].max_input_tokens == 262_144
            assert models["kimi-k2-0711-preview"].max_input_tokens == 131_072

        for provider_id in ("minimax-cn", "minimax-intl"):
            assert {m.max_input_tokens for m in presets[provider_id].models} == {204_800}

        mimo = {model.id: model for model in presets["mimo"].models}
        assert mimo["mimo-v2.5"].max_input_tokens == 1_048_576
        assert mimo["mimo-v2.5"].max_output_tokens == 131_072
        assert mimo["mimo-v2-flash"].max_input_tokens == 262_144

        aliyun = {model.id: model for model in presets["aliyun-codingplan-cn"].models}
        assert aliyun["qwen3.7-plus"].max_input_tokens == 1_000_000
        assert aliyun["qwen3-coder-plus"].max_input_tokens == 1_000_000
        assert aliyun["qwen3-max-2026-01-23"].max_input_tokens == 262_144
        assert aliyun["MiniMax-M2.5"].max_input_tokens == 196_608

    def test_opencode_presets_in_bundle(self) -> None:
        presets = {p.id: p for p in load_provider_templates(templates_path=_BUNDLED_TEMPLATE)}
        for pid in (
            "opencode-zen-openai",
            "opencode-zen-anthropic",
            "opencode-go-openai",
            "opencode-go-anthropic",
        ):
            assert pid in presets

        zen_oai = presets["opencode-zen-openai"]
        assert zen_oai.protocol == "openai"
        assert zen_oai.base_url == "https://opencode.ai/zen/v1"
        assert zen_oai.vendor == "opencode"
        assert zen_oai.variant == "zen_compatible"
        assert zen_oai.api_key_env == "OPENCODE_API_KEY"
        assert any(m.id == "kimi-k3" for m in zen_oai.models)
        assert not any(m.id.startswith("gpt-") for m in zen_oai.models)
        assert not any(m.id.startswith("gemini-") for m in zen_oai.models)

        zen_ant = presets["opencode-zen-anthropic"]
        assert zen_ant.protocol == "anthropic"
        assert zen_ant.base_url == "https://opencode.ai/zen"
        assert zen_ant.variant == "zen_anthropic"
        assert any(m.id.startswith("claude-") for m in zen_ant.models)

        go_oai = presets["opencode-go-openai"]
        assert go_oai.protocol == "openai"
        assert go_oai.base_url == "https://opencode.ai/zen/go/v1"
        assert go_oai.variant == "go_compatible"
        assert any(m.id == "deepseek-v4-flash" for m in go_oai.models)

        go_ant = presets["opencode-go-anthropic"]
        assert go_ant.protocol == "anthropic"
        assert go_ant.base_url == "https://opencode.ai/zen/go"
        assert go_ant.variant == "go_anthropic"
        assert any(m.id == "minimax-m3" for m in go_ant.models)


class TestProviderPresetPublicExport:
    def test_model_preset_importable_from_root(self) -> None:
        from octop_harness import ModelPreset as RootModelPreset
        from octop_harness.providers import ModelPreset as CoreModelPreset

        assert RootModelPreset is CoreModelPreset

    def test_provider_preset_importable_from_root(self) -> None:
        from octop_harness import ProviderPreset as RootProviderPreset
        from octop_harness.providers import ProviderPreset as CoreProviderPreset

        assert RootProviderPreset is CoreProviderPreset

    def test_in_all(self) -> None:
        import octop_harness

        assert "ModelPreset" in octop_harness.__all__
        assert "ProviderPreset" in octop_harness.__all__
