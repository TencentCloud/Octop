"""Curated ONNX / fastembed embedding model catalog."""

from __future__ import annotations

from typing import Any

# Finnie Memory page defaults (recommended).
ONNX_PRESET_MODEL_IDS: tuple[str, ...] = (
    "BAAI/bge-small-zh-v1.5",
    "jinaai/jina-embeddings-v2-base-zh",
    "intfloat/multilingual-e5-large",
)

_EXTRA_CATALOG_IDS: tuple[str, ...] = (
    "BAAI/bge-small-en-v1.5",
    "BAAI/bge-base-en-v1.5",
    "BAAI/bge-large-en-v1.5",
    "BAAI/bge-base-zh-v1.5",
    "jinaai/jina-embeddings-v2-base-en",
    "jinaai/jina-embeddings-v2-small-en",
    "intfloat/multilingual-e5-base",
    "intfloat/multilingual-e5-small",
    "sentence-transformers/all-MiniLM-L6-v2",
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    "thenlper/gte-base",
    "thenlper/gte-large",
)

# Approximate sizes (GB) when fastembed metadata is unavailable.
_FALLBACK_SIZE_GB: dict[str, float] = {
    "BAAI/bge-small-zh-v1.5": 0.09,
    "jinaai/jina-embeddings-v2-base-zh": 0.32,
    "intfloat/multilingual-e5-large": 1.2,
    "BAAI/bge-small-en-v1.5": 0.13,
    "BAAI/bge-base-en-v1.5": 0.21,
    "BAAI/bge-large-en-v1.5": 0.53,
    "BAAI/bge-base-zh-v1.5": 0.4,
    "intfloat/multilingual-e5-base": 0.44,
    "intfloat/multilingual-e5-small": 0.13,
    "sentence-transformers/all-MiniLM-L6-v2": 0.09,
}


def _model_entry(
    model_id: str,
    *,
    recommended: bool = False,
    size_gb: float | None = None,
    hf_source: str | None = None,
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "id": model_id,
        "name": model_id,
        "recommended": recommended,
    }
    if size_gb is not None:
        entry["size_gb"] = size_gb
    if hf_source:
        entry["hf_source"] = hf_source
    return entry


def _fastembed_meta_map() -> dict[str, dict[str, Any]]:
    try:
        from fastembed import TextEmbedding
    except ImportError:
        return {}
    try:
        raw = TextEmbedding.list_supported_models()
    except Exception:
        return {}
    out: dict[str, dict[str, Any]] = {}
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        model = item.get("model") or item.get("model_name") or item.get("id")
        if not isinstance(model, str) or not model:
            continue
        out[model] = item
    return out


def get_onnx_model_meta(model_id: str) -> dict[str, Any]:
    """Return size / HF source metadata for a model id."""
    meta = _fastembed_meta_map().get(model_id) or {}
    size = meta.get("size_in_GB")
    size_gb: float | None
    try:
        size_gb = float(size) if size is not None else None
    except (TypeError, ValueError):
        size_gb = None
    if size_gb is None:
        size_gb = _FALLBACK_SIZE_GB.get(model_id)
    sources = meta.get("sources") if isinstance(meta.get("sources"), dict) else {}
    hf_source = sources.get("hf") if isinstance(sources, dict) else None
    if not isinstance(hf_source, str) or not hf_source.strip():
        hf_source = None
    return {
        "id": model_id,
        "size_gb": size_gb,
        "hf_source": hf_source,
        "supported": bool(meta),
    }


def list_onnx_catalog_models() -> list[dict[str, Any]]:
    """Return catalog entries for the Models local ONNX panel."""
    meta_map = _fastembed_meta_map()
    recommended = set(ONNX_PRESET_MODEL_IDS)

    def enrich(model_id: str, *, rec: bool) -> dict[str, Any]:
        info = get_onnx_model_meta(model_id) if not meta_map else None
        if meta_map and model_id in meta_map:
            item = meta_map[model_id]
            size = item.get("size_in_GB")
            try:
                size_gb = float(size) if size is not None else _FALLBACK_SIZE_GB.get(model_id)
            except (TypeError, ValueError):
                size_gb = _FALLBACK_SIZE_GB.get(model_id)
            sources = item.get("sources") if isinstance(item.get("sources"), dict) else {}
            hf = sources.get("hf") if isinstance(sources, dict) else None
            return _model_entry(
                model_id,
                recommended=rec,
                size_gb=size_gb,
                hf_source=hf if isinstance(hf, str) else None,
            )
        if info:
            return _model_entry(
                model_id,
                recommended=rec,
                size_gb=info.get("size_gb"),
                hf_source=info.get("hf_source"),
            )
        return _model_entry(
            model_id,
            recommended=rec,
            size_gb=_FALLBACK_SIZE_GB.get(model_id),
        )

    if meta_map:
        ordered = list(ONNX_PRESET_MODEL_IDS) + sorted(
            mid for mid in meta_map if mid not in recommended
        )
        return [enrich(mid, rec=mid in recommended) for mid in ordered]

    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for mid in ONNX_PRESET_MODEL_IDS:
        seen.add(mid)
        out.append(enrich(mid, rec=True))
    for mid in _EXTRA_CATALOG_IDS:
        if mid in seen:
            continue
        seen.add(mid)
        out.append(enrich(mid, rec=False))
    return out
