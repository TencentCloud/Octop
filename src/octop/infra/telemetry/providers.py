"""Octop provider name -> ``gen_ai.provider.name`` lookup."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any, Protocol

# Octop provider ``kind`` -> well-known ``gen_ai.provider.name`` value.
KIND_TO_PROVIDER_NAME: dict[str, str] = {
    "openai": "openai",
    "anthropic": "anthropic",
    "ollama": "ollama",
    "azure": "azure.ai.openai",
    "gemini": "gcp.gemini",
}


class ProviderSource(Protocol):
    """Anything shaped like ``ProviderRepo.get_by_name`` (the row exposes ``.kind``)."""

    def get_by_name(self, name: str) -> Any | None: ...


class ProviderNameResolver:
    """TTL-cached lookup; an unknown provider falls back to its own configured name."""

    def __init__(
        self,
        source: ProviderSource,
        *,
        ttl_s: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._source = source
        self._ttl_s = ttl_s
        self._clock = clock
        self._cache: dict[str, tuple[float, str]] = {}

    def name_for(self, provider: str) -> str:
        if not provider:
            return ""
        now = self._clock()
        hit = self._cache.get(provider)
        if hit is not None and now - hit[0] < self._ttl_s:
            return hit[1]
        try:
            row = self._source.get_by_name(provider)
        except Exception:  # noqa: BLE001 - telemetry must never break a turn
            return provider
        kind = str(getattr(row, "kind", "") or "").lower() if row is not None else ""
        resolved = KIND_TO_PROVIDER_NAME.get(kind, provider)
        self._cache[provider] = (now, resolved)
        return resolved
