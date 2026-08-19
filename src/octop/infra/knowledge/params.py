"""Instance-wide knowledge indexing and retrieval parameters."""

from __future__ import annotations

from collections.abc import Callable

DEFAULT_CHUNK_SIZE = 800
DEFAULT_CHUNK_OVERLAP = 120
DEFAULT_RETRIEVAL_K = 8
DEFAULT_CONTEXT_CHAR_BUDGET = 6000

_CHUNK_SIZE_KEY = "knowledge_chunk_size"
_CHUNK_OVERLAP_KEY = "knowledge_chunk_overlap"
_RETRIEVAL_K_KEY = "knowledge_retrieval_k"
_CONTEXT_CHAR_BUDGET_KEY = "knowledge_context_char_budget"

_MIN_CHUNK_SIZE = 100
_MAX_CHUNK_SIZE = 8000
_MIN_RETRIEVAL_K = 1
_MAX_RETRIEVAL_K = 20
_MIN_CONTEXT_CHAR_BUDGET = 500
_MAX_CONTEXT_CHAR_BUDGET = 50_000

SettingsGet = Callable[[str], str | None]
SettingsSet = Callable[[str, str], None]


def _as_int(value: str | None, *, default: int, minimum: int, maximum: int) -> int:
    """Parse a stored integer setting; invalid or out-of-range values use *default*."""
    if value is None or not str(value).strip():
        return default
    try:
        parsed = int(str(value).strip())
    except ValueError:
        return default
    if parsed < minimum or parsed > maximum:
        return default
    return parsed


def _validate_chunk_window(size: int, overlap: int) -> None:
    if size < _MIN_CHUNK_SIZE or size > _MAX_CHUNK_SIZE:
        raise ValueError(f"chunk_size must be between {_MIN_CHUNK_SIZE} and {_MAX_CHUNK_SIZE}")
    if overlap < 0 or overlap >= size:
        raise ValueError("chunk_overlap must be non-negative and smaller than chunk_size")


def get_advanced_settings(settings_get: SettingsGet) -> dict[str, int]:
    """Return resolved indexing/retrieval knobs (missing values use defaults)."""
    size = _as_int(
        settings_get(_CHUNK_SIZE_KEY),
        default=DEFAULT_CHUNK_SIZE,
        minimum=_MIN_CHUNK_SIZE,
        maximum=_MAX_CHUNK_SIZE,
    )
    overlap = _as_int(
        settings_get(_CHUNK_OVERLAP_KEY),
        default=DEFAULT_CHUNK_OVERLAP,
        minimum=0,
        maximum=max(size - 1, 0),
    )
    if overlap >= size:
        overlap = min(DEFAULT_CHUNK_OVERLAP, size - 1) if size > 1 else 0
    return {
        "chunk_size": size,
        "chunk_overlap": overlap,
        "retrieval_k": _as_int(
            settings_get(_RETRIEVAL_K_KEY),
            default=DEFAULT_RETRIEVAL_K,
            minimum=_MIN_RETRIEVAL_K,
            maximum=_MAX_RETRIEVAL_K,
        ),
        "context_char_budget": _as_int(
            settings_get(_CONTEXT_CHAR_BUDGET_KEY),
            default=DEFAULT_CONTEXT_CHAR_BUDGET,
            minimum=_MIN_CONTEXT_CHAR_BUDGET,
            maximum=_MAX_CONTEXT_CHAR_BUDGET,
        ),
    }


def set_advanced_settings(
    settings_get: SettingsGet,
    settings_set: SettingsSet,
    *,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
    retrieval_k: int | None = None,
    context_char_budget: int | None = None,
) -> None:
    """Persist provided advanced settings; omitted fields stay unchanged."""
    current = get_advanced_settings(settings_get)
    next_size = current["chunk_size"] if chunk_size is None else int(chunk_size)
    next_overlap = current["chunk_overlap"] if chunk_overlap is None else int(chunk_overlap)
    if chunk_size is not None or chunk_overlap is not None:
        _validate_chunk_window(next_size, next_overlap)
        if chunk_size is not None:
            settings_set(_CHUNK_SIZE_KEY, str(next_size))
        if chunk_overlap is not None:
            settings_set(_CHUNK_OVERLAP_KEY, str(next_overlap))
    if retrieval_k is not None:
        value = int(retrieval_k)
        if value < _MIN_RETRIEVAL_K or value > _MAX_RETRIEVAL_K:
            raise ValueError(
                f"retrieval_k must be between {_MIN_RETRIEVAL_K} and {_MAX_RETRIEVAL_K}"
            )
        settings_set(_RETRIEVAL_K_KEY, str(value))
    if context_char_budget is not None:
        value = int(context_char_budget)
        if value < _MIN_CONTEXT_CHAR_BUDGET or value > _MAX_CONTEXT_CHAR_BUDGET:
            raise ValueError(
                "context_char_budget must be between "
                f"{_MIN_CONTEXT_CHAR_BUDGET} and {_MAX_CONTEXT_CHAR_BUDGET}"
            )
        settings_set(_CONTEXT_CHAR_BUDGET_KEY, str(value))
