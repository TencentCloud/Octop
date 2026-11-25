"""Agent id -> display name lookup for metric attributes."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any, Protocol


class AgentNameSource(Protocol):
    """Anything shaped like ``AgentRepo.get`` (the row exposes ``.name``)."""

    def get(self, agent_id: str) -> Any | None: ...


class AgentNameResolver:
    """TTL-cached name lookup; never raises (an unknown name is just ``""``)."""

    def __init__(
        self,
        source: AgentNameSource,
        *,
        ttl_s: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._source = source
        self._ttl_s = ttl_s
        self._clock = clock
        self._cache: dict[str, tuple[float, str]] = {}

    def name_for(self, agent_id: str) -> str:
        if not agent_id:
            return ""
        now = self._clock()
        hit = self._cache.get(agent_id)
        if hit is not None and now - hit[0] < self._ttl_s:
            return hit[1]
        try:
            row = self._source.get(agent_id)
        except Exception:  # noqa: BLE001 - telemetry must never break a turn
            return ""
        name = str(getattr(row, "name", "") or "") if row is not None else ""
        self._cache[agent_id] = (now, name)
        return name
