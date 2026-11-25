"""Models available for online knowledge-base embeddings and reranking."""

from __future__ import annotations

from typing import Any, Literal

from octop.infra.agents.providers.model_flags import (
    is_embedding_model,
    is_onnx_local_provider,
    is_rerank_model,
    provider_purpose_from_extra,
)
from octop.infra.agents.providers.probe import parse_provider_extra


def remote_models(provider: Any, task: Literal["embedding", "rerank"]) -> list[dict[str, str]]:
    if not (provider and provider.enabled and provider.api_key and provider.base_url):
        return []
    if is_onnx_local_provider(provider.name, provider_api_key=provider.api_key):
        return []
    embedding_service = provider_purpose_from_extra(parse_provider_extra(provider)) == "embedding"
    options = []
    for model in provider.get_models():
        model_id = str(model.get("id") or "").strip()
        if not model_id or not model.get("enabled", True):
            continue
        matches = (
            is_rerank_model(model)
            if task == "rerank"
            else is_embedding_model(model, embedding_service=embedding_service)
        )
        if matches:
            options.append({"id": model_id, "name": str(model.get("name") or model_id)})
    return options
