"""Tests for ``octop_harness.config``."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from octop_harness.backends.workspace import DEFAULT_MEMORY_FILES
from octop_harness.config import (
    HarnessAgentConfig,
    ModelConfig,
    ProviderConfig,
    _is_rootfs_path,
)


class TestModelConfig:
    def test_defaults(self) -> None:
        m = ModelConfig(id="foo")
        assert m.name == "foo"
        assert m.enabled is True
        assert m.input == ["text"]
        assert m.is_multimodal is False
        assert m.api_mode == "chat_completions"
        assert m.api_fallback == "none"

    def test_multimodal_detection(self) -> None:
        assert ModelConfig(id="m", input=["text", "image"]).is_multimodal is True
        assert ModelConfig(id="m", input=["audio"]).is_multimodal is True
        assert ModelConfig(id="m", input=["text"]).is_multimodal is False

    def test_empty_id_rejected(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            ModelConfig(id="")

    def test_empty_input_rejected(self) -> None:
        with pytest.raises(ValueError, match="modality"):
            ModelConfig(id="x", input=[])

    def test_invalid_api_mode_rejected(self) -> None:
        with pytest.raises(ValueError, match="api_mode is invalid"):
            ModelConfig(id="x", api_mode="invalid")  # type: ignore[arg-type]

    def test_invalid_api_fallback_rejected(self) -> None:
        with pytest.raises(ValueError, match="api_fallback is invalid"):
            ModelConfig(id="x", api_fallback="auto")  # type: ignore[arg-type]

    def test_api_fallback_requires_responses_mode(self) -> None:
        with pytest.raises(ValueError, match="api_fallback requires api_mode='responses'"):
            ModelConfig(id="x", api_fallback="chat_completions")

    def test_api_fallback_rejects_native_tool_search(self) -> None:
        with pytest.raises(ValueError, match="api_fallback is incompatible with native_tool_search"):
            ModelConfig(
                id="x",
                api_mode="responses",
                api_fallback="chat_completions",
                native_tool_search=True,
            )


class TestProviderConfig:
    def test_minimal(self) -> None:
        p = ProviderConfig(id="p", base_url="https://x", api_key="k")
        assert p.protocol == "openai"
        assert p.enabled_models() == []

    def test_duplicate_model_id_rejected(self) -> None:
        with pytest.raises(ValueError, match="Duplicate model id"):
            ProviderConfig(
                id="p",
                base_url="https://x",
                api_key="k",
                models=[ModelConfig(id="a"), ModelConfig(id="a")],
            )

    def test_get_model(self) -> None:
        p = ProviderConfig(
            id="p",
            base_url="https://x",
            api_key="k",
            models=[ModelConfig(id="a"), ModelConfig(id="b")],
        )
        assert p.get_model("a").id == "a"  # type: ignore[union-attr]
        assert p.get_model("missing") is None

    def test_enabled_models(self) -> None:
        p = ProviderConfig(
            id="p",
            base_url="https://x",
            api_key="k",
            models=[
                ModelConfig(id="a"),
                ModelConfig(id="b", enabled=False),
                ModelConfig(id="c"),
            ],
        )
        assert [m.id for m in p.enabled_models()] == ["a", "c"]

    def test_unknown_protocol_rejected(self) -> None:
        with pytest.raises(ValueError, match="Unsupported provider protocol"):
            ProviderConfig(id="p", base_url="https://x", api_key="k", protocol="cohere")  # type: ignore[arg-type]

    def test_missing_credentials_rejected(self) -> None:
        with pytest.raises(ValueError):
            ProviderConfig(id="p", base_url="", api_key="k")
        with pytest.raises(ValueError):
            ProviderConfig(id="p", base_url="https://x", api_key="")


class TestProviderConfigId:
    def test_id_stored(self) -> None:
        p = ProviderConfig(id="myco", base_url="https://myco.com/v1", api_key="sk-x")
        assert p.id == "myco"

    def test_id_empty_raises(self) -> None:
        with pytest.raises(ValueError, match=r"ProviderConfig\.id"):
            ProviderConfig(id="", base_url="https://myco.com/v1", api_key="sk-x")

    def test_to_dict_includes_id(self) -> None:
        p = ProviderConfig(id="myco", base_url="https://myco.com/v1", api_key="sk-x")
        assert p.to_dict()["id"] == "myco"

    def test_from_dict_reads_id(self) -> None:
        d = {"id": "myco", "base_url": "https://myco.com/v1", "api_key": "sk-x"}
        p = ProviderConfig.from_dict(d)
        assert p.id == "myco"

    def test_from_dict_missing_id_raises(self) -> None:
        d = {"base_url": "https://myco.com/v1", "api_key": "sk-x"}
        with pytest.raises((KeyError, ValueError)):
            ProviderConfig.from_dict(d)


class TestHarnessAgentConfig:
    def _provider(self) -> ProviderConfig:
        return ProviderConfig(
            id="p",
            base_url="https://x",
            api_key="k",
            models=[
                ModelConfig(id="text", input=["text"]),
                ModelConfig(id="vision", input=["text", "image"]),
                ModelConfig(id="off", enabled=False),
            ],
        )

    def test_empty_providers_allowed(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Empty ``providers`` is valid — env detection is deferred to ``HarnessAgent``."""
        for var in ("OPENAI_API_KEY", "OPENAI_BASE_URL", "ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY"):
            monkeypatch.delenv(var, raising=False)
        config = HarnessAgentConfig(workspace_dir=tmp_path)
        assert config.providers == []

    def test_relative_workspace_rejected(self) -> None:
        with pytest.raises(ValueError, match=r"workspace_dir must be an absolute"):
            HarnessAgentConfig(workspace_dir=Path("relative") / "ws")

    def test_agent_facing_rootfs_workspace_allowed(self) -> None:
        """Octop-style ``/.octop/workspaces/<id>`` has no drive letter on Windows."""
        config = HarnessAgentConfig(workspace_dir="/.octop/workspaces/J1BT2X")
        assert Path(config.workspace_dir).as_posix() == "/.octop/workspaces/J1BT2X"

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("/.octop/workspaces/J1BT2X", True),
            ("\\.octop\\workspaces\\J1BT2X", True),
            ("C:/agents/ws", False),
            ("relative/ws", False),
            ("~/ws", False),
        ],
    )
    def test_rootfs_path_detection(self, value: str, expected: bool) -> None:
        """Platform-independent guard: CI only runs Linux, where every ``/x`` is absolute."""
        assert _is_rootfs_path(value) is expected

    def test_default_model_validation(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="Unknown provider"):
            HarnessAgentConfig(
                workspace_dir=tmp_path,
                providers=[self._provider()],
                default_model="other/text",
            )
        with pytest.raises(ValueError, match="has no model"):
            HarnessAgentConfig(
                workspace_dir=tmp_path,
                providers=[self._provider()],
                default_model="p/missing",
            )
        with pytest.raises(ValueError, match="disabled"):
            HarnessAgentConfig(
                workspace_dir=tmp_path,
                providers=[self._provider()],
                default_model="p/off",
            )

    def test_default_model_ref_picker(self, tmp_path: Path) -> None:
        cfg = HarnessAgentConfig(workspace_dir=tmp_path, providers=[self._provider()])
        # No default_model set → first enabled model wins.
        assert cfg.pick_default_model_ref() == "p/text"

    def test_pick_multimodal_explicit(self, tmp_path: Path) -> None:
        cfg = HarnessAgentConfig(
            workspace_dir=tmp_path,
            providers=[self._provider()],
            default_model="p/text",
            multimodal_model="p/vision",
        )
        assert cfg.pick_multimodal_model_ref() == "p/vision"

    def test_pick_multimodal_auto(self, tmp_path: Path) -> None:
        cfg = HarnessAgentConfig(
            workspace_dir=tmp_path,
            providers=[self._provider()],
            default_model="p/text",
        )
        assert cfg.pick_multimodal_model_ref() == "p/vision"

    def test_pick_multimodal_none_available(self, tmp_path: Path) -> None:
        provider = ProviderConfig(
            id="p",
            base_url="https://x",
            api_key="k",
            models=[ModelConfig(id="text-only")],
        )
        cfg = HarnessAgentConfig(workspace_dir=tmp_path, providers=[provider])
        assert cfg.pick_multimodal_model_ref() is None

    def test_resolve_model_ref(self, tmp_path: Path) -> None:
        cfg = HarnessAgentConfig(
            workspace_dir=tmp_path,
            providers=[self._provider()],
            default_model="p/text",
        )
        provider, model = cfg.resolve_model_ref("p/vision")
        assert provider.base_url == "https://x"
        assert model.id == "vision"

    def test_resolve_model_ref_malformed(self, tmp_path: Path) -> None:
        cfg = HarnessAgentConfig(
            workspace_dir=tmp_path,
            providers=[self._provider()],
            default_model="p/text",
        )
        with pytest.raises(ValueError, match="must be in the form"):
            cfg.resolve_model_ref("just-an-id")
        with pytest.raises(ValueError, match="Malformed"):
            cfg.resolve_model_ref("/text")
        with pytest.raises(ValueError, match="Malformed"):
            cfg.resolve_model_ref("p/")

    def test_default_memory_files(self, tmp_path: Path) -> None:
        cfg = HarnessAgentConfig(
            workspace_dir=tmp_path,
            providers=[self._provider()],
            default_model="p/text",
        )
        assert cfg.memory_files() == list(DEFAULT_MEMORY_FILES)

    def test_custom_memory_files(self, tmp_path: Path) -> None:
        cfg = HarnessAgentConfig(
            workspace_dir=tmp_path,
            providers=[self._provider()],
            default_model="p/text",
            memory=["only_one.md"],
        )
        assert cfg.memory_files() == ["only_one.md"]

    def test_session_log_max_bytes_must_be_positive(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="positive"):
            HarnessAgentConfig(
                workspace_dir=tmp_path,
                providers=[self._provider()],
                default_model="p/text",
                session_log_max_bytes=0,
            )


class TestHarnessAgentConfigAutoEnv:
    """Config itself does not read provider env vars — that happens in ``HarnessAgent``."""

    def test_empty_providers_not_auto_detected(self, tmp_path: Path) -> None:
        """``providers=[]`` stays empty at config construction even when env is set."""
        env = {
            "OPENAI_API_KEY": "sk-test",
            "OPENAI_BASE_URL": "https://api.openai.com/v1",
        }
        with patch.dict("os.environ", env, clear=True):
            config = HarnessAgentConfig(workspace_dir=tmp_path)
        assert config.providers == []

    def test_empty_providers_without_env_allowed(self, tmp_path: Path) -> None:
        with patch.dict("os.environ", {}, clear=True):
            config = HarnessAgentConfig(workspace_dir=tmp_path)
        assert config.providers == []

    def test_harness_default_model_not_read_at_config_time(self, tmp_path: Path) -> None:
        """``HARNESS_DEFAULT_MODEL`` is applied by ``HarnessAgent``, not ``HarnessAgentConfig``."""
        env = {
            "OPENAI_API_KEY": "sk-test",
            "OPENAI_BASE_URL": "https://api.openai.com/v1",
            "HARNESS_DEFAULT_MODEL": "openai/gpt-4o-mini",
        }
        with patch.dict("os.environ", env, clear=True):
            config = HarnessAgentConfig(workspace_dir=tmp_path)
        assert config.default_model is None

    def test_explicit_default_model_on_config(self, tmp_path: Path) -> None:
        config = HarnessAgentConfig(
            workspace_dir=tmp_path,
            providers=[
                ProviderConfig(
                    id="openai",
                    base_url="https://api.openai.com/v1",
                    api_key="sk-test",
                    models=[ModelConfig(id="gpt-4o-mini")],
                )
            ],
            default_model="openai/gpt-4o-mini",
        )
        assert config.default_model == "openai/gpt-4o-mini"

    def test_explicit_providers_not_overridden_by_env(self, tmp_path: Path) -> None:
        """If providers is explicitly passed, env detection must NOT run."""
        env = {"OPENAI_API_KEY": "sk-env-key"}
        with patch.dict("os.environ", env, clear=True):
            config = HarnessAgentConfig(
                workspace_dir=tmp_path,
                providers=[ProviderConfig(id="myco", api_key="explicit", base_url="https://myco.com/v1")],
            )
        assert [p.id for p in config.providers] == ["myco"]

    def test_from_env_returns_empty_providers(self, tmp_path: Path) -> None:
        """``from_env()`` is sugar for ``providers=[]``; detection happens in ``HarnessAgent``."""
        env = {
            "OPENAI_API_KEY": "sk-from-env",
            "OPENAI_BASE_URL": "https://api.openai.com/v1",
        }
        with patch.dict("os.environ", env, clear=True):
            config = HarnessAgentConfig.from_env(workspace_dir=tmp_path)
        assert config.providers == []
        assert Path(config.workspace_dir) == tmp_path

    def test_from_env_without_env_vars_succeeds(self, tmp_path: Path) -> None:
        with patch.dict("os.environ", {}, clear=True):
            config = HarnessAgentConfig.from_env(workspace_dir=tmp_path)
        assert config.providers == []


class TestHarnessAgentConfigProvidersList:
    def _provider(self, pid: str = "p") -> ProviderConfig:
        return ProviderConfig(
            id=pid,
            base_url="https://example.com/v1",
            api_key="sk-x",
            models=[ModelConfig(id="m")],
        )

    def test_providers_is_list(self, tmp_path: Path) -> None:
        cfg = HarnessAgentConfig(
            workspace_dir=tmp_path,
            providers=[self._provider("p")],
            default_model="p/m",
        )
        assert isinstance(cfg.providers, list)
        assert cfg.providers[0].id == "p"

    def test_duplicate_provider_id_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match=r"Duplicate provider id"):
            HarnessAgentConfig(
                workspace_dir=tmp_path,
                providers=[self._provider("p"), self._provider("p")],
                default_model="p/m",
            )

    def test_resolve_model_ref_list(self, tmp_path: Path) -> None:
        cfg = HarnessAgentConfig(
            workspace_dir=tmp_path,
            providers=[self._provider("p")],
            default_model="p/m",
        )
        provider, model = cfg.resolve_model_ref("p/m")
        assert provider.id == "p"
        assert model.id == "m"

    def test_pick_default_from_list(self, tmp_path: Path) -> None:
        cfg = HarnessAgentConfig(
            workspace_dir=tmp_path,
            providers=[self._provider("p")],
        )
        assert cfg.pick_default_model_ref() == "p/m"

    def test_from_env_uses_empty_list(self, tmp_path: Path) -> None:
        """``from_env()`` always starts with ``providers=[]``."""
        env = {"OPENAI_API_KEY": "sk-test"}
        with patch.dict("os.environ", env, clear=True):
            cfg = HarnessAgentConfig.from_env(workspace_dir=tmp_path)
        assert isinstance(cfg.providers, list)
        assert cfg.providers == []
