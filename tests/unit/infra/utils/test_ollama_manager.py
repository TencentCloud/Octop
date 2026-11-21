"""Tests for Ollama models-directory helpers."""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from octop.infra.utils import ollama_manager as mod
from octop.infra.utils.ollama_manager import (
    OllamaModelInfo,
    apply_models_dir,
    list_models_from_dir,
    merge_model_lists,
    names_match,
    normalize_models_dir,
    resolve_ollama_models_root,
)

posix_only = pytest.mark.skipif(os.name != "posix", reason="POSIX-only path semantics")


def _reset_apply_state(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mod, "_original_ollama_models", mod._UNSET)
    monkeypatch.setattr(mod, "_applied_models_dir", None)


def test_normalize_models_dir_empty() -> None:
    assert normalize_models_dir("  ") == ""


def test_normalize_models_dir_requires_absolute(tmp_path: Path) -> None:
    assert normalize_models_dir(str(tmp_path)) == os.path.realpath(str(tmp_path))
    with pytest.raises(ValueError, match="absolute"):
        normalize_models_dir("relative/models")


@posix_only
def test_normalize_models_dir_rejects_denied_prefix() -> None:
    with pytest.raises(ValueError, match="not allowed"):
        normalize_models_dir("/etc/ollama")
    with pytest.raises(ValueError, match="not allowed"):
        normalize_models_dir("/tmp/../etc/ollama")


@posix_only
def test_list_models_from_dir_skips_denied_prefix() -> None:
    assert list_models_from_dir("/etc") == []


def test_names_match_latest_alias() -> None:
    assert names_match("llama3", "llama3:latest")
    assert names_match("llama3:latest", "llama3")
    assert not names_match("qwen2.5", "qwen2.5:7b")


def test_list_models_from_dir_reads_manifests(tmp_path: Path) -> None:
    library = tmp_path / "manifests" / "registry.ollama.ai" / "library"
    (library / "llama3").mkdir(parents=True)
    (library / "llama3" / "latest").write_text("{}", encoding="utf-8")
    (library / "qwen2.5").mkdir(parents=True)
    (library / "qwen2.5" / "7b").write_text("{}", encoding="utf-8")
    hf = tmp_path / "manifests" / "hf.co" / "org" / "mod"
    hf.mkdir(parents=True)
    (hf / "latest").write_text("{}", encoding="utf-8")

    names = {m.name for m in list_models_from_dir(str(tmp_path))}
    assert names == {"llama3:latest", "qwen2.5:7b", "hf.co/org/mod:latest"}
    assert all(m.size == 0 for m in list_models_from_dir(str(tmp_path)))


def test_resolve_root_accepts_ollama_home(tmp_path: Path) -> None:
    models = tmp_path / "models"
    (models / "manifests").mkdir(parents=True)
    assert resolve_ollama_models_root(str(tmp_path)) == models.resolve()
    assert resolve_ollama_models_root(str(models)) == models.resolve()


def test_list_models_from_dir_via_home_parent(tmp_path: Path) -> None:
    models = tmp_path / "models"
    dest = models / "manifests" / "registry.ollama.ai" / "library" / "mistral"
    dest.mkdir(parents=True)
    (dest / "latest").write_text("{}", encoding="utf-8")
    names = {m.name for m in list_models_from_dir(str(tmp_path))}
    assert names == {"mistral:latest"}


def test_merge_prefers_api_and_keeps_disk_only() -> None:
    api = [OllamaModelInfo(name="llama3:latest", size=10)]
    disk = [
        OllamaModelInfo(name="llama3", size=0),
        OllamaModelInfo(name="custom:7b", size=2),
    ]
    merged = merge_model_lists(api, disk)
    assert [m.name for m in merged] == ["llama3:latest", "custom:7b"]
    assert merged[0].size == 10


def test_apply_models_dir_sets_and_restores_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OLLAMA_MODELS", raising=False)
    _reset_apply_state(monkeypatch)
    apply_models_dir("/data/ollama-models")
    assert os.environ["OLLAMA_MODELS"] == "/data/ollama-models"
    apply_models_dir("")
    assert "OLLAMA_MODELS" not in os.environ


def test_apply_models_dir_restores_preexisting_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLLAMA_MODELS", "/original")
    _reset_apply_state(monkeypatch)
    apply_models_dir("/override")
    assert os.environ["OLLAMA_MODELS"] == "/override"
    apply_models_dir(None)
    assert os.environ["OLLAMA_MODELS"] == "/original"


def test_model_info_from_sdk_dict_and_object() -> None:
    as_dict = {"model": "llama3:8b", "size": 3, "digest": "abc"}
    info = mod._model_info_from_sdk(as_dict)
    assert info is not None
    assert info.name == "llama3:8b"
    assert info.size == 3

    named = {"name": "mistral", "size": 0}
    info2 = mod._model_info_from_sdk(named)
    assert info2 is not None
    assert info2.name == "mistral"

    obj = SimpleNamespace(model="qwen2.5:7b", size=9, digest=None, modified_at=None)
    info3 = mod._model_info_from_sdk(obj)
    assert info3 is not None
    assert info3.name == "qwen2.5:7b"


def test_start_ollama_server_inherits_models_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OLLAMA_MODELS", raising=False)
    _reset_apply_state(monkeypatch)
    apply_models_dir("/data/ollama-models")
    captured: dict[str, object] = {}

    monkeypatch.setattr(mod.shutil, "which", lambda _name: "/usr/bin/ollama")
    monkeypatch.setattr(mod.time, "sleep", lambda _s: None)
    monkeypatch.setattr(mod, "_is_ollama_reachable", lambda: True)

    def fake_popen(cmd: list[str], **kwargs: object) -> MagicMock:
        captured["cmd"] = cmd
        captured["env"] = kwargs.get("env")
        return MagicMock()

    monkeypatch.setattr(mod.subprocess, "Popen", fake_popen)
    mod._start_ollama_server()
    env = captured["env"]
    assert isinstance(env, dict)
    assert env.get("OLLAMA_MODELS") == "/data/ollama-models"
    assert captured["cmd"] == ["/usr/bin/ollama", "serve"]
