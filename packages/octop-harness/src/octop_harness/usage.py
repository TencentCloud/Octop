"""Provider-neutral token usage normalization."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def _nonnegative_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _detail_total(details: Mapping[str, Any], *names: str) -> int:
    direct = sum(_nonnegative_int(details.get(name)) for name in names)
    prefixed = sum(
        _nonnegative_int(value)
        for key, value in details.items()
        if isinstance(key, str) and any(key.endswith(f"_{name}") for name in names)
    )
    return direct + prefixed


def normalize_usage_metadata(raw: Mapping[str, Any]) -> dict[str, int]:
    """Return disjoint usage buckets from LangChain or provider wire metadata.

    LangChain normalizes ``input_tokens`` to the complete prompt size, including
    cache reads and cache creation.  ``uncached_input_tokens`` therefore removes
    those two subdivisions while ``input_tokens`` remains the context-pressure
    value expected by existing consumers.
    """
    input_details_raw = raw.get("input_token_details") or raw.get("prompt_tokens_details") or {}
    input_details = input_details_raw if isinstance(input_details_raw, Mapping) else {}
    output_details_raw = raw.get("output_token_details") or raw.get("completion_tokens_details") or {}
    output_details = output_details_raw if isinstance(output_details_raw, Mapping) else {}

    cache_read = _nonnegative_int(raw.get("cache_read_tokens")) or _detail_total(
        input_details,
        "cache_read",
        "cached_tokens",
    )
    cache_read = cache_read or _nonnegative_int(raw.get("prompt_cache_hit_tokens"))
    cache_write = _nonnegative_int(raw.get("cache_write_tokens")) or _detail_total(
        input_details,
        "cache_creation",
        "cache_write",
    )
    reasoning = _nonnegative_int(raw.get("reasoning_tokens")) or _detail_total(
        output_details,
        "reasoning",
        "reasoning_tokens",
    )

    input_tokens = _nonnegative_int(raw.get("input_tokens") or raw.get("prompt_tokens"))
    explicit_uncached = raw.get("uncached_input_tokens")
    if explicit_uncached is not None:
        uncached_input = _nonnegative_int(explicit_uncached)
        if input_tokens == 0:
            input_tokens = uncached_input + cache_read + cache_write
    else:
        uncached_input = max(0, input_tokens - cache_read - cache_write)
    output_tokens = _nonnegative_int(raw.get("output_tokens") or raw.get("completion_tokens"))

    return {
        "input_tokens": input_tokens,
        "uncached_input_tokens": uncached_input,
        "cache_read_tokens": cache_read,
        "cache_write_tokens": cache_write,
        "output_tokens": output_tokens,
        "reasoning_tokens": reasoning,
        "total_tokens": input_tokens + output_tokens,
    }


__all__ = ["normalize_usage_metadata"]
