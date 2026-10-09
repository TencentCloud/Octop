"""Regression tests for the dashboard memory cache's connection lifetime.

The cache used to hold ``Memory`` instances forever: idle timeout, LRU
eviction, config change and explicit invalidation all dropped the dict entry
without closing anything. On PostgreSQL each dropped-but-open entry keeps one
backend connection plus a checkpointer pool (``min_size=1``), so a long-running
server accumulated connections until the database refused new ones.
"""

from __future__ import annotations

import sys
import types
from typing import Any

import pytest

from octop.api.common import memory_client


class _FakeMemory:
    def __init__(self, namespace: str, backend: str, backend_config: dict[str, Any] | None) -> None:
        self.namespace = namespace
        self.backend = backend
        self.backend_config = backend_config
        self.closed = False


class _FakeBridge:
    def __init__(self, memory: _FakeMemory) -> None:
        self.memory = memory


@pytest.fixture
def closed_memories(monkeypatch: pytest.MonkeyPatch) -> list[_FakeMemory]:
    """Stub the lazily imported octop-memory pieces and record every close."""
    core = types.ModuleType("octop_memory.core")
    core.Memory = _FakeMemory
    handlers = types.ModuleType("octop_memory.adapters.bridge.handlers")
    handlers.Bridge = _FakeBridge
    monkeypatch.setitem(sys.modules, "octop_memory.core", core)
    monkeypatch.setitem(sys.modules, "octop_memory.adapters.bridge.handlers", handlers)

    closed: list[_FakeMemory] = []

    def _close(memory: _FakeMemory) -> None:
        memory.closed = True
        closed.append(memory)

    monkeypatch.setattr("octop_harness.memory.store.close_memory_resources", _close)
    return closed


def _open(cache: memory_client._MemoryCache, agent_id: str, fingerprint: str = "fp") -> Any:
    memory, _bridge = cache.get_or_open(
        agent_id,
        backend="postgres",
        backend_config={"dsn": "postgresql://localhost/octop_memory"},
        fingerprint=fingerprint,
    )
    return memory


def test_cache_hit_reuses_instance_without_closing(closed_memories: list[_FakeMemory]) -> None:
    cache = memory_client._MemoryCache()
    first = _open(cache, "agent_a")
    second = _open(cache, "agent_a")
    assert first is second
    assert closed_memories == []


def test_config_change_closes_replaced_entry(closed_memories: list[_FakeMemory]) -> None:
    cache = memory_client._MemoryCache()
    stale = _open(cache, "agent_a", fingerprint="old")
    fresh = _open(cache, "agent_a", fingerprint="new")
    assert stale is not fresh
    assert stale.closed is True
    assert closed_memories == [stale]


def test_lru_eviction_closes_oldest_entry(closed_memories: list[_FakeMemory]) -> None:
    cache = memory_client._MemoryCache(max_size=1)
    oldest = _open(cache, "agent_a")
    _open(cache, "agent_b")
    assert oldest.closed is True
    assert closed_memories == [oldest]


def test_idle_sweep_closes_and_drops_stale_entry(closed_memories: list[_FakeMemory]) -> None:
    cache = memory_client._MemoryCache(idle_ttl=0.0)
    stale = _open(cache, "agent_a")
    cache.sweep_idle()
    assert stale.closed is True
    assert closed_memories == [stale]
    # Dropped, so the next RPC rebuilds instead of handing back a dead backend.
    assert _open(cache, "agent_a") is not stale


def test_idle_sweep_keeps_recently_used_entry(closed_memories: list[_FakeMemory]) -> None:
    cache = memory_client._MemoryCache(idle_ttl=60.0)
    live = _open(cache, "agent_a")
    cache.sweep_idle()
    assert live.closed is False
    assert closed_memories == []


def test_invalidate_closes_entry(closed_memories: list[_FakeMemory]) -> None:
    cache = memory_client._MemoryCache()
    live = _open(cache, "agent_a")
    cache.invalidate("agent_a")
    assert live.closed is True
    assert closed_memories == [live]


def test_close_failure_does_not_escape_eviction(monkeypatch: pytest.MonkeyPatch) -> None:
    """A failing close must not turn an eviction into an RPC error."""
    core = types.ModuleType("octop_memory.core")
    core.Memory = _FakeMemory
    handlers = types.ModuleType("octop_memory.adapters.bridge.handlers")
    handlers.Bridge = _FakeBridge
    monkeypatch.setitem(sys.modules, "octop_memory.core", core)
    monkeypatch.setitem(sys.modules, "octop_memory.adapters.bridge.handlers", handlers)

    def _boom(_memory: Any) -> None:
        raise RuntimeError("connection already gone")

    monkeypatch.setattr("octop_harness.memory.store.close_memory_resources", _boom)
    cache = memory_client._MemoryCache(max_size=1)
    _open(cache, "agent_a")
    survivor = _open(cache, "agent_b")
    assert survivor.closed is False
