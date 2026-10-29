"""Route knowledge-base embeddings to local ONNX or a configured provider."""

from __future__ import annotations

from typing import Any

import httpx

from octop.infra.agents.providers.onnx_service import embed_texts
from octop.infra.agents.providers.opencode_session import ensure_opencode_session_header
from octop.infra.agents.providers.probe import provider_headers

# Remote OpenAI-compatible embedding APIs cap the number of inputs per request.
_KNOWLEDGE_EMBEDDING_BATCH_LIMIT = 20


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
    headers: dict[str, str] = {"Authorization": f"Bearer {provider.api_key}"}
    extra = ensure_opencode_session_header(
        getattr(provider, "name", None),
        provider_headers(provider),
        base_url=provider.base_url,
    )
    if extra:
        headers.update(extra)
    with httpx.Client(timeout=60.0) as client:
        return _embed_remote_batched(client, provider.base_url.rstrip("/"), headers, model, texts)


def _embed_remote_batched(
    client: httpx.Client,
    base: str,
    headers: dict[str, str],
    model: str,
    texts: list[str],
) -> list[list[float]]:
    """Request a remote embedding API in <=batch-limit slices.

    Slices preserve input order so the merged vectors stay aligned with
    ``texts`` for :meth:`KnowledgeIndex.replace_doc_chunks`.
    """
    if not texts:
        return []
    out: list[list[float]] = []
    for start in range(0, len(texts), _KNOWLEDGE_EMBEDDING_BATCH_LIMIT):
        batch = texts[start : start + _KNOWLEDGE_EMBEDDING_BATCH_LIMIT]
        response = client.post(
            f"{base}/embeddings",
            headers=headers,
            json={"model": model, "input": batch},
        )
        response.raise_for_status()
        data = response.json().get("data")
        if not isinstance(data, list):
            raise RuntimeError("knowledge embedding response has no data")
        # OpenAI-compatible embedding APIs may return results in any order
        # while supplying an ``index`` field per result. Sort by that field
        # before extracting vectors so chunk N stays aligned with embedding
        # N (GitHub issue #1453). A missing index is treated as the item's
        # position in the response for providers that do not include it.
        def _item_index(item: Any, fallback: int) -> int:
            if isinstance(item, dict):
                raw = item.get("index")
                if isinstance(raw, int):
                    return raw
            return fallback

        indexed = sorted(enumerate(data), key=lambda pair: _item_index(pair[1], pair[0]))
        out.extend(list(item["embedding"]) for _, item in indexed)
    if len(out) != len(texts):
        raise RuntimeError("knowledge embedding count mismatch")
    return out
