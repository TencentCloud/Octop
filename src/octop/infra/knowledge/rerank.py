"""Optional second-stage ranking of retrieved knowledge chunks.

Vector search is recall-oriented: it brings back passages that look like the
question. A reranker reads the question together with each passage and scores
how well the passage answers it, so retrieval fetches a wider candidate set and
keeps the reranker's top ``k``.

The model is a ``/rerank`` endpoint of a configured provider (the Jina / Cohere
request shape, which SiliconFlow, vLLM, Xinference and TEI also serve).
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from octop.infra.agents.providers.model_flags import is_rerank_model
from octop.infra.agents.providers.opencode_session import ensure_opencode_session_header
from octop.infra.agents.providers.probe import provider_headers

_ENABLED_KEY = "knowledge_rerank_enabled"
_PROVIDER_ID_KEY = "knowledge_rerank_provider_id"
_MODEL_KEY = "knowledge_rerank_model"

# How many vector hits the reranker gets to choose from, relative to ``k``.
_CANDIDATE_MULTIPLIER = 4
_MIN_CANDIDATES = 20
_MAX_CANDIDATES = 50
_TIMEOUT_SEC = 30.0


def _as_bool(value: str | None) -> bool:
    if value is None:
        return False
    try:
        decoded: Any = json.loads(value)
    except json.JSONDecodeError:
        decoded = value
    if isinstance(decoded, bool):
        return decoded
    return str(decoded).strip().lower() == "true"


def rerank_models(provider: Any) -> list[dict[str, str]]:
    """Rerank models a provider offers, as ``{id, name}``."""
    return [
        {"id": str(model["id"]), "name": str(model.get("name") or model["id"])}
        for model in provider.get_models()
        if str(model.get("id") or "").strip() and is_rerank_model(model)
    ]


def _provider(provider_repo: Any, provider_id: str) -> Any | None:
    if provider_repo is None or not provider_id.isdigit():
        return None
    return provider_repo.get(int(provider_id))


def _ready(provider: Any | None, model: str) -> bool:
    return bool(
        provider
        and provider.enabled
        and provider.api_key
        and provider.base_url
        and any(candidate["id"] == model for candidate in rerank_models(provider))
    )


def get_rerank_capability(settings_get: Any, provider_repo: Any = None) -> dict[str, Any]:
    """Stored rerank choice and whether it can be used right now."""
    provider_id = (settings_get(_PROVIDER_ID_KEY) or "").strip()
    model = (settings_get(_MODEL_KEY) or "").strip()
    enabled = _as_bool(settings_get(_ENABLED_KEY))
    ready = _ready(_provider(provider_repo, provider_id), model)
    return {
        "enabled": enabled,
        "provider_id": provider_id,
        "model": model,
        "ready": ready,
        "usable": enabled and ready,
    }


def set_rerank_settings(
    settings_set: Any,
    *,
    enabled: bool,
    provider_id: str | None,
    model: str | None,
    provider_repo: Any,
) -> None:
    """Persist the rerank choice; enabling requires a provider that serves the model."""
    provider_id = (provider_id or "").strip()
    model = (model or "").strip()
    if enabled and not _ready(_provider(provider_repo, provider_id), model):
        raise ValueError("knowledge rerank model is not available on the selected provider")
    settings_set(_ENABLED_KEY, "true" if enabled else "false")
    if provider_id or model or not enabled:
        settings_set(_PROVIDER_ID_KEY, provider_id)
        settings_set(_MODEL_KEY, model)


def candidate_count(k: int) -> int:
    """Vector hits to fetch so the reranker has something to choose from."""
    return max(k, min(max(k * _CANDIDATE_MULTIPLIER, _MIN_CANDIDATES), _MAX_CANDIDATES))


def rerank_scores(services: Any, query: str, texts: list[str]) -> list[float] | None:
    """Relevance score per text, aligned with ``texts``; None when reranking is off.

    Raises when the provider call fails, so the caller can fall back to the
    vector order and say why.
    """
    capability = get_rerank_capability(services.settings_repo.get, services.provider_repo)
    if not capability["usable"] or not texts:
        return None
    provider = services.provider_repo.get(int(capability["provider_id"]))
    headers: dict[str, str] = {"Authorization": f"Bearer {provider.api_key}"}
    extra = ensure_opencode_session_header(
        getattr(provider, "name", None),
        provider_headers(provider),
        base_url=provider.base_url,
    )
    if extra:
        headers.update(extra)
    with httpx.Client(timeout=_TIMEOUT_SEC) as client:
        response = client.post(
            f"{provider.base_url.rstrip('/')}/rerank",
            headers=headers,
            json={
                "model": capability["model"],
                "query": query,
                "documents": texts,
                "top_n": len(texts),
            },
        )
    response.raise_for_status()
    return _parse_scores(response.json(), len(texts))


def _parse_scores(payload: Any, count: int) -> list[float]:
    """Read ``results[].{index, relevance_score}`` (also ``output.results`` and ``score``)."""
    results = payload
    if isinstance(payload, dict):
        output = payload.get("output")
        results = payload.get("results") or (
            output.get("results") if isinstance(output, dict) else None
        )
    if not isinstance(results, list):
        raise RuntimeError("knowledge rerank response has no results")
    # Texts a provider leaves out (it may ignore ``top_n``) rank below every scored one.
    scores = [float("-inf")] * count
    for item in results:
        if not isinstance(item, dict):
            raise RuntimeError("knowledge rerank response has an invalid result")
        index = item.get("index")
        score = item.get("relevance_score", item.get("score"))
        if not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < count:
            raise RuntimeError("knowledge rerank response has an invalid index")
        if not isinstance(score, (int, float)) or isinstance(score, bool):
            raise RuntimeError("knowledge rerank response has an invalid score")
        scores[index] = float(score)
    return scores
