"""Unit tests for model flag helpers against issue #1929.

Remote catalogs (DashScope, SiliconFlow, Ollama, vLLM listings, ...) ship
embedding entries without an explicit ``embedding: true`` flag, so
``is_embedding_model`` must also recognise common naming conventions —
mirroring how ``is_vision_model`` already keys off name hints.

Rerankers (review feedback on this PR) are a sibling capability: excluded
from chat pickers like embeddings, but they must NOT serve as a knowledge
base embedding backend — they answer ``/rerank`` with relevance scores, not
``/embeddings`` with vectors.
"""

from __future__ import annotations

import pytest

from octop.infra.agents.providers.model_flags import (
    is_chat_eligible_model,
    is_embedding_model,
    is_rerank_model,
)

EMBEDDING_BY_NAME = [
    "text-embedding-3-small",  # OpenAI
    "text-embedding-v3",  # DashScope
    "qwen3.7-text-embedding-flash",  # DashScope (real-world case from #1929)
    "Qwen3-Embedding-8B",  # uppercase must match too
    "bge-m3",  # BAAI / Ollama
    "nomic-embed-text",  # Ollama builtin
    "bce-embedding-base_v1",  # NetEase BCE
    "e5-large-v2",
    "gte-large-zh",
]

CHAT_MODELS = [
    "gpt-4o",
    "deepseek-chat",
    "qwen-max",
    "qwen3-235b-a22b",
    "glm-4.6",
    "claude-sonnet-4",
]

RERANK_MODELS = [
    "bge-reranker-v2-m3",  # BAAI — family prefix also matches the embedding hint
    "jina-reranker-v2-base-multilingual",
    "qwen3-reranker-8b",
]


@pytest.mark.parametrize("model_id", EMBEDDING_BY_NAME)
def test_embedding_recognised_by_name_convention(model_id: str) -> None:
    assert is_embedding_model({"id": model_id}) is True


@pytest.mark.parametrize("model_id", CHAT_MODELS)
def test_chat_models_not_flagged_as_embedding(model_id: str) -> None:
    assert is_embedding_model({"id": model_id}) is False


@pytest.mark.parametrize("model_id", RERANK_MODELS)
def test_rerankers_are_rerank_not_embedding(model_id: str) -> None:
    assert is_rerank_model({"id": model_id}) is True
    # A reranker must not become a knowledge-base embedding backend...
    assert is_embedding_model({"id": model_id}) is False
    # ...nor re-enter the chat pickers.
    assert is_chat_eligible_model({"id": model_id, "enabled": True}) is False


def test_explicit_flags_still_win() -> None:
    assert is_embedding_model({"id": "any-model", "embedding": True}) is True
    assert is_embedding_model({"id": "any-model", "task": "embedding"}) is True
    assert is_rerank_model({"id": "any-model", "task": "rerank"}) is True


def test_onnx_provider_fallback_unchanged() -> None:
    assert is_embedding_model({}, provider_name="onnx (local)", provider_api_key="onnx") is True


def test_blank_or_missing_id_is_not_embedding() -> None:
    assert is_embedding_model({}) is False
    assert is_embedding_model({"id": ""}) is False


def test_chat_eligible_excludes_embedding_models() -> None:
    assert is_chat_eligible_model({"id": "text-embedding-3-small", "enabled": True}) is False
    assert is_chat_eligible_model({"id": "gpt-4o", "enabled": True}) is True


def test_mixed_provider_keeps_chat_drops_embedding() -> None:
    """One provider serving both: chat stays, embedding leaves the pickers."""
    models = [
        {"id": "deepseek-chat", "enabled": True},
        {"id": "text-embedding-v3", "enabled": True},
    ]
    kwargs = {"provider_name": "acme", "provider_api_key": "k"}
    chat = [m["id"] for m in models if is_chat_eligible_model(m, **kwargs)]
    assert chat == ["deepseek-chat"]


def test_embedding_only_provider_serves_kb_only() -> None:
    """An embedding-only provider: usable by the knowledge base, no chat."""
    models = [{"id": "text-embedding-v3", "enabled": True}]
    kwargs = {"provider_name": "acme", "provider_api_key": "k"}
    assert is_embedding_model(models[0], **kwargs) is True
    assert not [m for m in models if is_chat_eligible_model(m, **kwargs)]
