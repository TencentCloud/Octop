"""Route knowledge-base embeddings to local ONNX or a configured provider."""

from __future__ import annotations

from typing import Any

import httpx

from octop.infra.agents.providers.onnx_service import embed_texts


def embed_knowledge_texts(services: Any, texts: list[str]) -> list[list[float]]:
    """Embed texts through the selected knowledge embedding backend."""
    settings = services.settings_repo
    backend = (settings.get("knowledge_embedding_backend") or "onnx").strip().lower()
    model = (settings.get("knowledge_embedding_model") or "").strip()
    if backend != "remote":
        return embed_texts(model, texts)

    provider_id = (settings.get("knowledge_embedding_provider_id") or "").strip()
    provider = services.provider_repo.get(int(provider_id)) if provider_id.isdigit() else None
    if provider is None or not provider.base_url or not provider.api_key:
        raise RuntimeError("knowledge remote embedding provider is not ready")
    with httpx.Client(timeout=60.0) as client:
        response = client.post(
            f"{provider.base_url.rstrip('/')}/embeddings",
            headers={"Authorization": f"Bearer {provider.api_key}"},
            json={"model": model, "input": texts},
        )
        response.raise_for_status()
    data = response.json().get("data")
    if not isinstance(data, list):
        raise RuntimeError("knowledge embedding response has no data")
    return [list(item["embedding"]) for item in data]
