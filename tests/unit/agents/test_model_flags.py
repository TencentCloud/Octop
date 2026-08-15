"""Tests for embedding / chat-eligibility model flags."""

from __future__ import annotations

from types import SimpleNamespace

from octop.infra.agents.providers.model_flags import (
    is_chat_eligible_model,
    is_embedding_model,
)
from octop.infra.agents.providers.resolved import list_resolved_models


def test_embedding_flag_and_task() -> None:
    assert is_embedding_model({"id": "a", "embedding": True})
    assert is_embedding_model({"id": "a", "task": "embedding"})
    assert not is_embedding_model({"id": "a", "enabled": True})


def test_onnx_provider_identity_marks_models_embedding() -> None:
    assert is_embedding_model(
        {"id": "BAAI/bge-small-zh-v1.5", "enabled": True},
        provider_name="ONNX (Local)",
        provider_api_key="onnx",
    )
    assert is_embedding_model(
        {"id": "BAAI/bge-small-zh-v1.5", "enabled": True},
        provider_name="ONNX (Local)",
    )
    assert not is_embedding_model(
        {"id": "gpt-4o", "enabled": True},
        provider_name="My ONNX Cloud Proxy",
    )
    assert not is_embedding_model(
        {"id": "gpt-4o", "enabled": True},
        provider_name="OpenAI",
    )


def test_is_onnx_local_provider() -> None:
    from octop.infra.agents.providers.model_flags import is_onnx_local_provider

    assert is_onnx_local_provider(provider_api_key="onnx")
    assert is_onnx_local_provider(provider_name="ONNX (Local)")
    assert is_onnx_local_provider(provider_name="onnx")
    # Ollama is also local — must not match via "local" substring heuristics.
    assert not is_onnx_local_provider(provider_name="Ollama (Local)")
    assert not is_onnx_local_provider(provider_name="My ONNX Cloud Proxy")
    assert not is_onnx_local_provider(provider_name="OpenAI")
    assert not is_onnx_local_provider(provider_name=None)


def test_is_local_runtime_provider() -> None:
    from octop.infra.agents.providers.model_flags import is_local_runtime_provider

    assert is_local_runtime_provider(provider_api_key="onnx")
    assert is_local_runtime_provider(provider_name="ONNX (Local)")
    assert is_local_runtime_provider(provider_api_key="ollama")
    assert is_local_runtime_provider(provider_name="Ollama (Local)")
    assert is_local_runtime_provider(provider_base_url="http://127.0.0.1:11434")
    assert not is_local_runtime_provider(
        provider_name="OpenAI",
        provider_api_key="sk-x",
        provider_base_url="https://api.openai.com/v1",
    )
    assert not is_local_runtime_provider(
        provider_name="My ONNX Cloud Proxy",
        provider_api_key="sk-x",
        provider_base_url="https://proxy.example/v1",
    )


def test_chat_eligible_excludes_embedding() -> None:
    assert is_chat_eligible_model({"id": "gpt", "enabled": True})
    assert not is_chat_eligible_model({"id": "emb", "enabled": True, "embedding": True})
    assert not is_chat_eligible_model({"id": "gpt", "enabled": False})


def test_list_resolved_models_skips_embedding() -> None:
    providers = [
        SimpleNamespace(
            id=1,
            name="ONNX (Local)",
            kind="openai",
            enabled=True,
            api_key="onnx",
            base_url="",
            get_models=lambda: [
                {
                    "id": "BAAI/bge-small-zh-v1.5",
                    "name": "bge",
                    "enabled": True,
                    "embedding": True,
                }
            ],
        ),
        SimpleNamespace(
            id=2,
            name="OpenAI",
            kind="openai",
            enabled=True,
            api_key="sk-x",
            base_url="https://api.openai.com/v1",
            get_models=lambda: [
                {"id": "gpt-4o", "name": "GPT-4o", "enabled": True},
            ],
        ),
    ]
    resolved = list_resolved_models(providers)
    assert [r["model"] for r in resolved] == ["gpt-4o"]
