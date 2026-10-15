"""Flags on provider ``models_json`` entries that affect chat / auto-routing."""

from __future__ import annotations

from typing import Any

# LocalServiceCard creates the ONNX provider with ``api_key=preset.id`` ("onnx").
_ONNX_PRESET_API_KEY = "onnx"
# Exact display / id names from the onnx preset — never substring "local"/"onnx".
_ONNX_PRESET_NAMES = frozenset({"onnx", "onnx (local)"})
# Same pattern for Ollama (placeholder api_key + exact preset names).
_OLLAMA_PRESET_API_KEY = "ollama"
_OLLAMA_PRESET_NAMES = frozenset({"ollama", "ollama (local)"})
# Common embedding-only naming conventions. ``is_vision_model`` already keys
# off name hints ("vision", "-vl", ...); embedding needs the same treatment
# because remote catalogs rarely carry an explicit ``embedding: true`` flag.
# Substrings are matched against the lower-cased model id.
_EMBEDDING_NAME_HINTS = (
    "embed",  # text-embedding-3-small, qwen*-embedding, bce-embedding, nomic-embed-text
    "bge-",  # BAAI general embedding series (bge-m3 has no "embed" substring)
    "e5-",  # e5-large-v2 family
    "gte-",  # gte-large family
)
# Rerankers must be checked *before* the embedding hints (the "bge-" family
# spans both) and excluded from chat pickers as well.
_RERANK_NAME_HINTS = ("rerank",)


def is_onnx_local_provider(
    provider_name: str | None = None,
    *,
    provider_api_key: str | None = None,
) -> bool:
    """True when this row is the local ONNX embedding preset.

    Prefer the stable placeholder API key written at create time. Fall back to
    exact preset name/id matches only — Ollama is also "local" and must not match.
    """
    if provider_api_key is not None and provider_api_key.strip().lower() == _ONNX_PRESET_API_KEY:
        return True
    if not provider_name:
        return False
    return provider_name.strip().lower() in _ONNX_PRESET_NAMES


def is_ollama_local_provider(
    provider_name: str | None = None,
    *,
    provider_api_key: str | None = None,
    provider_base_url: str | None = None,
) -> bool:
    """True when this row is the onboard Ollama preset.

    Identity only: the placeholder API key written at create time, or an
    exact preset name. ``provider_base_url`` is accepted for call-site
    compatibility and ignored — custom providers that happen to point at
    ``:11434`` / ``http://ollama`` must stay deletable.
    """
    _ = provider_base_url
    if is_onnx_local_provider(provider_name, provider_api_key=provider_api_key):
        return False
    if provider_api_key is not None and provider_api_key.strip().lower() == _OLLAMA_PRESET_API_KEY:
        return True
    if not provider_name:
        return False
    return provider_name.strip().lower() in _OLLAMA_PRESET_NAMES


def is_local_runtime_provider(
    provider_name: str | None = None,
    *,
    provider_api_key: str | None = None,
    provider_base_url: str | None = None,
) -> bool:
    """True for onboard local runtimes (ONNX / Ollama) that must not be deleted.

    URL is accepted for call-site compatibility and ignored.
    """
    return is_onnx_local_provider(
        provider_name, provider_api_key=provider_api_key
    ) or is_ollama_local_provider(
        provider_name,
        provider_api_key=provider_api_key,
        provider_base_url=provider_base_url,
    )


def is_rerank_model(model: dict[str, Any]) -> bool:
    """True when *model* is a reranker (query/document relevance scoring).

    Rerankers are a sibling capability, not embeddings: they answer ``/rerank``
    with relevance results instead of ``/embeddings`` with vectors, so they can
    neither serve as a knowledge-base embedding backend nor appear in chat
    pickers. Matched before the embedding name hints — the ``bge-`` family
    spans both (``bge-m3`` embeds, ``bge-reranker-*`` reranks).
    """
    if str(model.get("task") or "").strip().lower() == "rerank":
        return True
    model_id = str(model.get("id") or "").strip().lower()
    return any(hint in model_id for hint in _RERANK_NAME_HINTS)


def is_embedding_model(
    model: dict[str, Any],
    *,
    provider_name: str | None = None,
    provider_api_key: str | None = None,
) -> bool:
    """True when *model* is embedding-only (not for chat / auto-route).

    Explicit flags win:
    - ``embedding: true``
    - ``task: "embedding"``

    Rerankers are excluded even when their family prefix matches an embedding
    hint (``bge-reranker-*``): they cannot serve as an embedding backend
    (see :func:`is_rerank_model`).

    Name-convention fallback: many upstream model catalogs (DashScope,
    SiliconFlow, Ollama, vLLM listings, ...) ship embedding entries without an
    explicit flag, so mirror ``is_vision_model`` and recognise the common
    naming conventions too. This keeps embedding-only entries out of chat
    pickers and lets ``embedding-options`` surface remote providers (#1929).

    Legacy fallback: models under the ONNX local provider are treated as
    embedding-only even if the flag was missing.
    """
    if model.get("embedding") is True:
        return True
    task = str(model.get("task") or "").strip().lower()
    if task == "embedding":
        return True
    if is_rerank_model(model):
        return False
    model_id = str(model.get("id") or "").strip().lower()
    if model_id and any(hint in model_id for hint in _EMBEDDING_NAME_HINTS):
        return True
    return is_onnx_local_provider(provider_name, provider_api_key=provider_api_key)


def is_vision_model(model: dict[str, Any]) -> bool:
    """True when a model entry declares or conventionally supports image input."""
    model_id = str(model.get("id") or "").strip().lower()
    raw_input = model.get("input")
    if isinstance(raw_input, list) and any(
        str(modality).strip().lower() == "image" for modality in raw_input
    ):
        return True
    return any(
        hint in model_id
        for hint in (
            "-vl",
            "vision",
            "-image",
            "gpt-4o",
            "gpt-4.1",
            "claude-3",
            "gemini",
        )
    )


def is_chat_eligible_model(
    model: dict[str, Any],
    *,
    provider_name: str | None = None,
    provider_api_key: str | None = None,
) -> bool:
    """True when *model* may appear in chat pickers and auto-route candidates."""
    if not model.get("enabled", True):
        return False
    if is_embedding_model(model, provider_name=provider_name, provider_api_key=provider_api_key):
        return False
    if is_rerank_model(model):
        return False
    return bool(str(model.get("id") or "").strip())
