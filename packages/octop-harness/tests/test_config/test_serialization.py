"""Tests for ``HarnessAgentConfig`` serialization (to_dict / to_file / from_*)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from octop_harness.config import (
    DEFAULT_CONFIG_FILENAME,
    HarnessAgentConfig,
    MediaGenerationConfig,
    ModelConfig,
    ProviderConfig,
)


def _provider() -> ProviderConfig:
    return ProviderConfig(
        id="ex",
        base_url="https://api.example.com/v1",
        api_key="sk-test-1234567890",
        name="Example",
        protocol="openai",
        headers={"X-Trace": "1"},
        models=[
            ModelConfig(id="text-only", input=["text"]),
            ModelConfig(id="multimodal", input=["text", "image"], enabled=True),
            ModelConfig(id="off", enabled=False),
        ],
    )


def _full_config(tmp_path: Path) -> HarnessAgentConfig:
    return HarnessAgentConfig(
        name="serializable-agent",
        workspace_dir=tmp_path,
        skills_dir="skills_extra",
        backend={"type": "filesystem", "root_dir": str(tmp_path)},
        providers=[_provider()],
        default_model="ex/text-only",
        multimodal_model="ex/multimodal",
        memory=["AGENTS.md", "MEMORY.md"],
        memory_backend={"type": "sqlite", "db_path": str(tmp_path / "memory.db")},
        memory_backend_config={"timeout": 30},
        memory_extract_trigger_mode="interval",
        memory_extract_idle_seconds=120.0,
        memory_extract_interval_seconds=600.0,
        memory_extract_max_tokens=1024,
        memory_aux_light_timeout_s=45,
        memory_aux_heavy_timeout_s=90,
        memory_aux_thinking="off",
        system_prompt="be helpful",
        subagents=[{"name": "researcher", "description": "research", "system_prompt": "..."}],
        task_tool_last=False,
        session_log_enabled=True,
        session_log_max_bytes=10 * 1024 * 1024,
        model_retry_max_retries=3,
        pii_strategy="redact",
        pii_surfaces=("input",),
        debug=True,
    )


# ---------------------------------------------------------------------------
# ModelConfig / ProviderConfig
# ---------------------------------------------------------------------------


class TestModelConfigSerialization:
    def test_round_trip(self) -> None:
        m = ModelConfig(id="gpt-x", input=["text", "image"], enabled=False)
        restored = ModelConfig.from_dict(m.to_dict())
        assert restored == m

    def test_to_dict_is_jsonable(self) -> None:
        # Must survive json.dumps without coercion.
        json.dumps(ModelConfig(id="m").to_dict())

    def test_from_dict_accepts_context_window_alias(self) -> None:
        m = ModelConfig.from_dict({"id": "mm", "context_window": 1_000_000})
        assert m.max_input_tokens == 1_000_000
        assert m.context_window == 1_000_000

    def test_from_dict_keeps_context_input_and_output_limits_distinct(self) -> None:
        m = ModelConfig.from_dict(
            {
                "id": "mm",
                "max_input_tokens": 200_000,
                "context_window": 1_000_000,
                "max_output_tokens": 131_072,
            }
        )
        assert m.max_input_tokens == 200_000
        assert m.context_window == 1_000_000
        assert m.max_output_tokens == 131_072
        assert m.input_token_budget(reserved_output_tokens=131_072) == 200_000

    def test_input_budget_reserves_requested_output_from_total_context(self) -> None:
        m = ModelConfig(id="mm", max_input_tokens=1_000_000, context_window=1_000_000)
        assert m.input_token_budget(reserved_output_tokens=64_000) == 936_000

    def test_round_trip_preserves_native_tool_search(self) -> None:
        model = ModelConfig(id="tool-search", native_tool_search=True)
        assert ModelConfig.from_dict(model.to_dict()).native_tool_search is True

    def test_round_trip_preserves_api_mode(self) -> None:
        model = ModelConfig(id="responses-model", api_mode="responses")
        assert ModelConfig.from_dict(model.to_dict()).api_mode == "responses"

    def test_round_trip_preserves_api_fallback(self) -> None:
        model = ModelConfig(
            id="responses-model",
            api_mode="responses",
            api_fallback="chat_completions",
        )
        assert ModelConfig.from_dict(model.to_dict()).api_fallback == "chat_completions"


class TestProviderConfigSerialization:
    def test_round_trip(self) -> None:
        p = _provider()
        restored = ProviderConfig.from_dict(p.to_dict())
        assert restored == p

    def test_api_key_is_persisted_verbatim(self) -> None:
        # Per Q2 in the design discussion, api_key is stored as-is.
        p = _provider()
        assert p.to_dict()["api_key"] == "sk-test-1234567890"

    def test_models_are_round_tripped(self) -> None:
        p = _provider()
        restored = ProviderConfig.from_dict(p.to_dict())
        assert [m.id for m in restored.models] == ["text-only", "multimodal", "off"]
        assert restored.models[2].enabled is False

    def test_session_header_round_trip(self) -> None:
        p = ProviderConfig(
            id="go",
            base_url="https://opencode.ai/zen/go/v1",
            api_key="sk",
            session_header="x-opencode-session",
        )
        assert ProviderConfig.from_dict(p.to_dict()).session_header == "x-opencode-session"


# ---------------------------------------------------------------------------
# HarnessAgentConfig.to_dict / from_dict round trip
# ---------------------------------------------------------------------------


class TestHarnessAgentConfigRoundTrip:
    def test_memory_extraction_defaults_to_five_minutes_idle(self) -> None:
        cfg = HarnessAgentConfig()
        assert cfg.memory_extract_on_session_end is True
        assert cfg.memory_extract_trigger_mode == "idle"
        assert cfg.memory_extract_idle_seconds == 300.0
        assert cfg.memory_extract_max_tokens is None
        assert cfg.memory_aux_light_timeout_s is None
        assert cfg.memory_aux_thinking == "auto"

    def test_aux_call_limits_reject_bad_values(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="memory_extract_max_tokens"):
            HarnessAgentConfig(name="a", workspace_dir=tmp_path, memory_extract_max_tokens=1)
        with pytest.raises(ValueError, match="memory_aux_light_timeout_s"):
            HarnessAgentConfig(name="a", workspace_dir=tmp_path, memory_aux_light_timeout_s=5)
        with pytest.raises(ValueError, match="memory_aux_thinking"):
            HarnessAgentConfig(name="a", workspace_dir=tmp_path, memory_aux_thinking="maybe")  # type: ignore[arg-type]

    def test_memory_aux_call_options_default_to_unset(self) -> None:
        cfg = HarnessAgentConfig()
        assert cfg.memory_aux_light_timeout_s is None
        assert cfg.memory_aux_heavy_timeout_s is None
        assert cfg.memory_aux_max_tokens is None
        assert cfg.memory_aux_extra_body is None

    def test_round_trip_preserves_memory_aux_call_options(self, tmp_path: Path) -> None:
        cfg = HarnessAgentConfig(
            name="aux-options",
            workspace_dir=tmp_path,
            memory_aux_light_timeout_s=42.0,
            memory_aux_heavy_timeout_s=90.0,
            memory_aux_max_tokens=1024,
            memory_aux_extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        )
        restored = HarnessAgentConfig.from_dict(json.loads(json.dumps(cfg.to_dict())))

        assert restored.memory_aux_light_timeout_s == 42.0
        assert restored.memory_aux_heavy_timeout_s == 90.0
        assert restored.memory_aux_max_tokens == 1024
        assert restored.memory_aux_extra_body == {"chat_template_kwargs": {"enable_thinking": False}}

    def test_memory_aux_call_options_validation(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="memory_aux_light_timeout_s"):
            HarnessAgentConfig(name="t", workspace_dir=tmp_path, memory_aux_light_timeout_s=0.0)
        with pytest.raises(ValueError, match="memory_aux_heavy_timeout_s"):
            HarnessAgentConfig(name="t", workspace_dir=tmp_path, memory_aux_heavy_timeout_s=-1.0)
        with pytest.raises(ValueError, match="memory_aux_max_tokens"):
            HarnessAgentConfig(name="t", workspace_dir=tmp_path, memory_aux_max_tokens=0)
        with pytest.raises(ValueError, match="memory_aux_extra_body"):
            HarnessAgentConfig(name="t", workspace_dir=tmp_path, memory_aux_extra_body="enable_thinking=false")

    def test_to_dict_is_jsonable(self, tmp_path: Path) -> None:
        cfg = _full_config(tmp_path)
        json.dumps(cfg.to_dict())  # must not raise

    def test_round_trip_preserves_scalars(self, tmp_path: Path) -> None:
        cfg = _full_config(tmp_path)
        data = cfg.to_dict()
        restored = HarnessAgentConfig.from_dict(data)

        assert restored.name == cfg.name
        assert restored.system_files_path == cfg.system_files_path
        assert str(restored.workspace_dir) == str(cfg.workspace_dir)
        assert restored.default_model == cfg.default_model
        assert restored.multimodal_model == cfg.multimodal_model
        assert restored.system_prompt == cfg.system_prompt
        assert restored.subagents == cfg.subagents
        assert restored.subagents is not None
        assert restored.subagents[0]["name"] == "researcher"
        assert restored.task_tool_last is False
        assert restored.session_log_max_bytes == cfg.session_log_max_bytes
        assert restored.model_retry_max_retries == cfg.model_retry_max_retries
        assert restored.pii_strategy == "redact"
        assert restored.memory_extract_trigger_mode == "interval"
        assert restored.memory_extract_idle_seconds == 120.0
        assert restored.memory_extract_interval_seconds == 600.0
        assert restored.memory_extract_max_tokens == 1024
        assert restored.memory_aux_light_timeout_s == 45
        assert restored.memory_aux_heavy_timeout_s == 90
        assert restored.memory_aux_thinking == "off"
        # tuple field round-trips through list and back to tuple.
        assert restored.pii_surfaces == ("input",)
        assert restored.debug is True

    def test_round_trip_preserves_providers(self, tmp_path: Path) -> None:
        cfg = _full_config(tmp_path)
        restored = HarnessAgentConfig.from_dict(cfg.to_dict())
        assert restored.providers == cfg.providers

    def test_round_trip_preserves_backend_dict(self, tmp_path: Path) -> None:
        cfg = _full_config(tmp_path)
        restored = HarnessAgentConfig.from_dict(cfg.to_dict())
        assert restored.backend == cfg.backend

    def test_round_trip_preserves_memory_backend_config(self, tmp_path: Path) -> None:
        cfg = _full_config(tmp_path)
        restored = HarnessAgentConfig.from_dict(cfg.to_dict())
        assert restored.memory_backend == cfg.memory_backend
        assert restored.memory_backend_config == cfg.memory_backend_config

    def test_round_trip_preserves_skills_dir_string(self, tmp_path: Path) -> None:
        cfg = _full_config(tmp_path)
        restored = HarnessAgentConfig.from_dict(cfg.to_dict())
        # Single string skills_dir round-trips as string.
        assert restored.skills_dir == "skills_extra"

    def test_round_trip_preserves_skills_dir_list(self, tmp_path: Path) -> None:
        cfg = HarnessAgentConfig(
            workspace_dir=tmp_path,
            skills_dir=["a", "b", "c"],
            providers=[_provider()],
            default_model="ex/text-only",
        )
        restored = HarnessAgentConfig.from_dict(cfg.to_dict())
        assert list(restored.skills_dir or []) == ["a", "b", "c"]  # type: ignore[arg-type]

    def test_round_trip_preserves_skills_disabled(self, tmp_path: Path) -> None:
        cfg = HarnessAgentConfig(
            workspace_dir=tmp_path,
            providers=[_provider()],
            default_model="ex/text-only",
            skills_disabled=frozenset({"alpha", "beta"}),
        )
        restored = HarnessAgentConfig.from_dict(cfg.to_dict())
        assert restored.skills_disabled == frozenset({"alpha", "beta"})

    def test_round_trip_preserves_tools_disabled(self, tmp_path: Path) -> None:
        cfg = HarnessAgentConfig(
            workspace_dir=tmp_path,
            providers=[_provider()],
            default_model="ex/text-only",
            tools_disabled=frozenset({"web_fetch", "execute"}),
        )
        restored = HarnessAgentConfig.from_dict(cfg.to_dict())
        assert restored.tools_disabled == frozenset({"web_fetch", "execute"})

    def test_round_trip_preserves_deferred_tool_policy(self, tmp_path: Path) -> None:
        cfg = HarnessAgentConfig(
            workspace_dir=tmp_path,
            providers=[_provider()],
            default_model="ex/text-only",
            deferred_tools=frozenset({"generate_image", "generate_video"}),
            defer_mcp_tools=True,
            tool_search_mode="native",
            tool_search_fallback="error",
        )

        restored = HarnessAgentConfig.from_dict(cfg.to_dict())

        assert restored.deferred_tools == frozenset({"generate_image", "generate_video"})
        assert restored.defer_mcp_tools is True
        assert restored.tool_search_mode == "native"
        assert restored.tool_search_fallback == "error"

    def test_round_trip_preserves_media_generation(self, tmp_path: Path) -> None:
        media = MediaGenerationConfig(
            api_key="ark-test",
            image_model="seedream-test",
            video_model="seedance-test",
            output_dir="artifacts/generated",
            video_poll_interval_seconds=1.5,
        )
        cfg = HarnessAgentConfig(
            workspace_dir=tmp_path,
            providers=[_provider()],
            default_model="ex/text-only",
            media_generation=media,
        )

        restored = HarnessAgentConfig.from_dict(cfg.to_dict())

        assert restored.media_generation == media
        assert restored.media_generation is not None
        assert restored.media_generation.api_key == ""
        assert "ark-test" not in json.dumps(cfg.to_dict())
        json.dumps(cfg.to_dict())

    def test_round_trip_preserves_team_fields(self, tmp_path: Path) -> None:
        cfg = HarnessAgentConfig(
            workspace_dir=tmp_path,
            providers=[_provider()],
            default_model="ex/text-only",
            team_enabled=False,
            team_peers=("data-analyst", "researcher"),
            peer_invoke_mode="async",
        )
        restored = HarnessAgentConfig.from_dict(cfg.to_dict())
        assert restored.team_enabled is False
        assert restored.team_peers == ("data-analyst", "researcher")
        assert restored.peer_invoke_mode == "async"

    def test_team_defaults(self) -> None:
        cfg = HarnessAgentConfig()
        assert cfg.team_enabled is True
        assert cfg.team_peers is None
        assert cfg.peer_invoke_mode == "both"

    def test_invalid_peer_invoke_mode_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="peer_invoke_mode"):
            HarnessAgentConfig(
                workspace_dir=tmp_path,
                providers=[_provider()],
                default_model="ex/text-only",
                peer_invoke_mode="maybe",  # type: ignore[arg-type]
            )


def test_media_generation_rejects_workspace_escape() -> None:
    with pytest.raises(ValueError, match="must stay inside"):
        MediaGenerationConfig(api_key="ark-test", output_dir="../outside")


def test_media_generation_resolves_api_key_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_ARK_API_KEY", "ark-from-env")

    config = MediaGenerationConfig(api_key_env="TEST_ARK_API_KEY")

    assert config.resolve_api_key() == "ark-from-env"


def test_bedrock_rejects_native_tool_search() -> None:
    with pytest.raises(ValueError, match="only supported for openai and anthropic"):
        ProviderConfig(
            id="bedrock",
            base_url="https://bedrock.example",
            api_key="unused",
            protocol="bedrock",
            models=[ModelConfig(id="claude", native_tool_search=True)],
        )


class TestUnserializableFields:
    """Live Python objects must be silently dropped from the output."""

    def test_callable_model_selector_is_dropped(self, tmp_path: Path) -> None:
        cfg = HarnessAgentConfig(
            workspace_dir=tmp_path,
            providers=[_provider()],
            default_model="ex/text-only",
            model_selector=lambda _state, _config: None,
        )
        assert "model_selector" not in cfg.to_dict()

    def test_live_backend_instance_is_dropped(self, tmp_path: Path) -> None:
        live_backend = MagicMock(name="backend-instance")
        cfg = HarnessAgentConfig(
            workspace_dir=tmp_path,
            providers=[_provider()],
            default_model="ex/text-only",
            backend=live_backend,
        )
        # The ``backend`` key is omitted entirely when the value is a live instance.
        assert "backend" not in cfg.to_dict()

    def test_tools_and_middleware_dropped(self, tmp_path: Path) -> None:
        cfg = HarnessAgentConfig(
            workspace_dir=tmp_path,
            providers=[_provider()],
            default_model="ex/text-only",
            tools=[MagicMock(name="custom-tool")],
            middleware=[MagicMock(name="custom-mw")],
        )
        out = cfg.to_dict()
        assert "tools" not in out
        assert "middleware" not in out

    def test_live_memory_backend_instance_is_dropped(self, tmp_path: Path) -> None:
        live_backend = MagicMock(name="memory-backend-instance")
        cfg = HarnessAgentConfig(
            workspace_dir=tmp_path,
            providers=[_provider()],
            default_model="ex/text-only",
            memory_backend=live_backend,
        )
        assert "memory_backend" not in cfg.to_dict()

    def test_from_dict_ignores_unserializable_keys_in_input(self, tmp_path: Path) -> None:
        """Forward-compat: hand-edited files with extra keys must not break load."""
        data = {
            "workspace_dir": str(tmp_path),
            "providers": {
                "p": {
                    "id": "p",
                    "base_url": "https://x",
                    "api_key": "k",
                    "models": [{"id": "m"}],
                },
            },
            "default_model": "p/m",
            # These should be silently ignored.
            "model_selector": "<callable>",
            "tools": ["dummy"],
            "checkpointer": "<obj>",
            "unknown_future_field": 42,
        }
        cfg = HarnessAgentConfig.from_dict(data)
        assert cfg.model_selector is None
        assert cfg.tools is None


# ---------------------------------------------------------------------------
# to_file / from_file
# ---------------------------------------------------------------------------


class TestFileRoundTrip:
    def test_explicit_path_round_trip(self, tmp_path: Path) -> None:
        cfg = _full_config(tmp_path)
        target = tmp_path / "custom-name.json"
        written = cfg.to_file(target)
        assert written == target.absolute()
        assert target.is_file()

        restored = HarnessAgentConfig.from_file(target)
        assert restored.providers == cfg.providers
        assert restored.default_model == cfg.default_model

    def test_default_save_path_uses_workspace(self, tmp_path: Path) -> None:
        cfg = _full_config(tmp_path)
        written = cfg.to_file()
        expected = tmp_path / DEFAULT_CONFIG_FILENAME
        assert written == expected.absolute()
        assert expected.is_file()

    def test_save_creates_missing_parent_dirs(self, tmp_path: Path) -> None:
        cfg = _full_config(tmp_path)
        # Workspace dir doesn't exist yet — save should mkdir it.
        nested = tmp_path / "deeply" / "nested" / "config.json"
        cfg.to_file(nested)
        assert nested.is_file()

    def test_default_load_path_uses_cwd(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Set up a config file at ``./octop-harness.json`` relative to CWD.
        cfg = _full_config(tmp_path)
        monkeypatch.chdir(tmp_path)
        (tmp_path / DEFAULT_CONFIG_FILENAME).write_text(
            json.dumps(cfg.to_dict()),
            encoding="utf-8",
        )

        loaded = HarnessAgentConfig.from_file()
        assert loaded.name == cfg.name

    def test_load_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            HarnessAgentConfig.from_file(tmp_path / "does-not-exist.json")

    def test_load_invalid_data_type_raises(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.json"
        bad.write_text("[]", encoding="utf-8")  # list, not dict
        with pytest.raises(TypeError, match="expected a dict"):
            HarnessAgentConfig.from_file(bad)

    def test_load_uses_utf8(self, tmp_path: Path) -> None:
        """Non-ASCII content (e.g. Chinese name field) must round-trip cleanly."""
        cfg = HarnessAgentConfig(
            name="测试代理",  # Chinese characters in the agent name
            workspace_dir=tmp_path,
            providers=[_provider()],
            default_model="ex/text-only",
            system_prompt="你是一个有用的助手",
        )
        target = tmp_path / "cfg.json"
        cfg.to_file(target)
        # Verify the raw file contains the literal Chinese (no \uXXXX escapes).
        raw = target.read_text(encoding="utf-8")
        assert "测试代理" in raw
        restored = HarnessAgentConfig.from_file(target)
        assert restored.name == "测试代理"
        assert restored.system_prompt == "你是一个有用的助手"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_minimal_config_round_trip(self, tmp_path: Path) -> None:
        """A minimal config (only the required fields) round-trips intact."""
        cfg = HarnessAgentConfig(
            workspace_dir=tmp_path,
            providers=[_provider()],
            default_model="ex/text-only",
        )
        restored = HarnessAgentConfig.from_dict(cfg.to_dict())
        assert restored.name == cfg.name  # default name preserved
        assert restored.providers == cfg.providers

    def test_backend_string_form_round_trips(self, tmp_path: Path) -> None:
        cfg = HarnessAgentConfig(
            workspace_dir=tmp_path,
            providers=[_provider()],
            default_model="ex/text-only",
            backend="filesystem",
        )
        assert HarnessAgentConfig.from_dict(cfg.to_dict()).backend == "filesystem"

    def test_backend_none_round_trips(self, tmp_path: Path) -> None:
        cfg = HarnessAgentConfig(
            workspace_dir=tmp_path,
            providers=[_provider()],
            default_model="ex/text-only",
            backend=None,
        )
        assert HarnessAgentConfig.from_dict(cfg.to_dict()).backend is None


# ---------------------------------------------------------------------------
# language field
# ---------------------------------------------------------------------------


class TestLanguageField:
    def test_default_language_is_zh(self, tmp_path: Path) -> None:
        cfg = HarnessAgentConfig(
            workspace_dir=tmp_path,
            providers=[_provider()],
            default_model="ex/text-only",
        )
        assert cfg.language == "zh"

    def test_language_round_trips_through_dict(self, tmp_path: Path) -> None:
        cfg = HarnessAgentConfig(
            workspace_dir=tmp_path,
            providers=[_provider()],
            default_model="ex/text-only",
            language="en",
        )
        data = cfg.to_dict()
        assert data["language"] == "en"
        restored = HarnessAgentConfig.from_dict(data)
        assert restored.language == "en"

    def test_invalid_language_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="language"):
            HarnessAgentConfig(
                workspace_dir=tmp_path,
                providers=[_provider()],
                default_model="ex/text-only",
                language="fr",  # type: ignore[arg-type]
            )


# ---------------------------------------------------------------------------
# Backward-compat: old dict-format providers
# ---------------------------------------------------------------------------


class TestProvidersDictBackwardCompat:
    """from_dict must silently migrate old dict-format providers."""

    def test_old_dict_format_migrated_to_list(self, tmp_path: Path) -> None:
        data = {
            "workspace_dir": str(tmp_path),
            "providers": {
                "openai": {
                    "base_url": "https://api.openai.com/v1",
                    "api_key": "sk-old",
                    "models": [{"id": "gpt-4", "name": "GPT-4"}],
                }
            },
            "default_model": "openai/gpt-4",
        }
        cfg = HarnessAgentConfig.from_dict(data)
        assert isinstance(cfg.providers, list)
        assert len(cfg.providers) == 1
        assert cfg.providers[0].id == "openai"
        assert cfg.providers[0].api_key == "sk-old"

    def test_new_list_format_round_trips(self, tmp_path: Path) -> None:
        cfg = HarnessAgentConfig(
            workspace_dir=tmp_path,
            providers=[
                ProviderConfig(
                    id="myco",
                    base_url="https://myco.com/v1",
                    api_key="sk-x",
                    models=[ModelConfig(id="m1")],
                )
            ],
            default_model="myco/m1",
        )
        d = cfg.to_dict()
        assert isinstance(d["providers"], list)
        assert d["providers"][0]["id"] == "myco"

        cfg2 = HarnessAgentConfig.from_dict(d)
        assert cfg2.providers[0].id == "myco"
        assert cfg2.default_model == "myco/m1"


class TestLegacyLogFieldsIgnored:
    def test_to_dict_omits_runtime_log_fields(self) -> None:
        cfg = HarnessAgentConfig(
            providers=[
                ProviderConfig(
                    id="p",
                    base_url="https://x",
                    api_key="k",
                    models=[ModelConfig(id="text")],
                ),
            ],
        )
        data = cfg.to_dict()
        assert "log_dir" not in data
        assert "log_agent_id" not in data
        assert "log_level" not in data
        assert "log_max_bytes" not in data
        assert "log_backup_count" not in data

    def test_from_dict_ignores_legacy_log_keys(self) -> None:
        restored = HarnessAgentConfig.from_dict(
            {
                "providers": [
                    {
                        "id": "p",
                        "base_url": "https://x",
                        "api_key": "k",
                        "models": [{"id": "text"}],
                    }
                ],
                "log_dir": "my_logs",
                "log_agent_id": "aid1",
                "log_level": "DEBUG",
                "log_max_bytes": 5 * 1024 * 1024,
                "log_backup_count": 3,
            }
        )
        assert "log_dir" not in vars(restored)
        data = restored.to_dict()
        assert "log_dir" not in data
        assert "log_agent_id" not in data
        assert "log_level" not in data
        assert "log_max_bytes" not in data
        assert "log_backup_count" not in data

    def test_constructor_accepts_legacy_log_kwargs(self, tmp_path: Path) -> None:
        cfg = HarnessAgentConfig(
            workspace_dir=tmp_path,
            log_dir=str(tmp_path / "octop-logs"),
            log_agent_id="aid1",
            log_level="DEBUG",
            log_max_bytes=1024,
            log_backup_count=2,
            providers=[
                ProviderConfig(
                    id="p",
                    base_url="https://x",
                    api_key="k",
                    models=[ModelConfig(id="text")],
                ),
            ],
        )
        assert "log_dir" not in vars(cfg)
        assert "log_dir" not in cfg.to_dict()
