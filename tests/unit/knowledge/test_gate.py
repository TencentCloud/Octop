"""Unit tests for the knowledge-base capability gate."""

from __future__ import annotations

import pytest

from octop.infra.knowledge import gate


def test_capability_is_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gate, "local_embedding_deps_available", lambda: True)
    monkeypatch.setattr(gate, "is_model_downloaded", lambda _model: True)

    capability = gate.get_capability(lambda _key: None)

    assert capability["feature_enabled"] is False
    assert capability["selected_model"] == ""
    assert capability["prerequisites_ok"] is False
    assert capability["usable"] is False
    assert capability["checks"] == {
        "model_selected": False,
        "model_downloaded": False,
        "deps_available": True,
        "provider_ready": False,
    }


def test_enabled_capability_uses_selected_model_not_onnx_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = "BAAI/bge-small-zh-v1.5"
    monkeypatch.setattr(
        gate,
        "embedding_prerequisites_ok_for_model",
        lambda candidate: candidate == model,
    )
    monkeypatch.setattr(gate, "is_model_downloaded", lambda candidate: candidate == model)
    monkeypatch.setattr(gate, "local_embedding_deps_available", lambda: True)

    values = {
        "knowledge_bases_enabled": "true",
        "knowledge_embedding_model": model,
        "onnx_local_service": '{"enabled": false}',
    }
    capability = gate.get_capability(values.get)

    assert capability["feature_enabled"] is True
    assert capability["selected_model"] == model
    assert capability["prerequisites_ok"] is True
    assert capability["usable"] is True


def test_enabling_requires_model_and_persists_verified_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values: dict[str, str] = {}
    model = "BAAI/bge-small-zh-v1.5"
    monkeypatch.setattr(
        gate,
        "require_embedding_prerequisites_for_model",
        lambda candidate: candidate.strip(),
    )

    with pytest.raises(ValueError, match="requires an embedding model"):
        gate.set_feature_enabled(values.get, values.__setitem__, enabled=True, model=None)

    gate.set_feature_enabled(values.get, values.__setitem__, enabled=True, model=model)

    assert values == {
        "knowledge_bases_enabled": "true",
        "knowledge_embedding_backend": "onnx",
        "knowledge_embedding_model": model,
        "knowledge_embedding_provider_id": "",
    }


def test_assert_knowledge_usable_distinguishes_disabled_from_prerequisites(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(gate, "embedding_prerequisites_ok_for_model", lambda _model: False)
    with pytest.raises(RuntimeError, match="disabled"):
        gate.assert_knowledge_usable(lambda _key: None)

    settings = {
        "knowledge_bases_enabled": "true",
        "knowledge_embedding_model": "BAAI/bge-small-zh-v1.5",
    }
    with pytest.raises(RuntimeError, match="prerequisites"):
        gate.assert_knowledge_usable(settings.get)


def test_remote_capability_requires_enabled_embedding_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = type(
        "Provider",
        (),
        {
            "enabled": True,
            "api_key": "key",
            "base_url": "https://example.test/v1",
            "name": "Remote",
            "get_models": lambda self: [{"id": "embed-1", "embedding": True}],
        },
    )()
    monkeypatch.setattr(gate, "_provider_for_settings", lambda _repo, _id: provider)

    values = {
        "knowledge_bases_enabled": "true",
        "knowledge_embedding_backend": "remote",
        "knowledge_embedding_model": "embed-1",
        "knowledge_embedding_provider_id": "7",
    }
    capability = gate.get_capability(values.get)

    assert capability["backend"] == "remote"
    assert capability["provider_id"] == "7"
    assert capability["prerequisites_ok"] is True
    assert capability["checks"]["provider_ready"] is True
