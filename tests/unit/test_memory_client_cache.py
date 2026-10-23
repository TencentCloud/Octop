"""Memory dashboard cache must release replaced / evicted / invalidated instances."""

from __future__ import annotations

from unittest.mock import patch

from octop.api.common.memory_client import _MemoryCache


class _FakeMemory:
    def __init__(self, namespace: str) -> None:
        self.namespace = namespace
        self.closed = False

    def close(self) -> None:
        self.closed = True


class _FakeBridge:
    def __init__(self, memory: _FakeMemory) -> None:
        self.memory = memory
        self.closed = False

    def close(self) -> None:
        self.closed = True


def _open(cache: _MemoryCache, agent_id: str, fingerprint: str) -> tuple[_FakeMemory, _FakeBridge]:
    memory, bridge = cache.get_or_open(
        agent_id,
        backend="sqlite",
        backend_config=None,
        fingerprint=fingerprint,
    )
    return memory, bridge


def test_cache_closes_replaced_evicted_and_invalidated_instances() -> None:
    """Replace / evict / invalidate must call close instead of leaking instances."""
    with (
        patch("octop_memory.core.Memory", side_effect=lambda **kw: _FakeMemory(kw["namespace"])),
        patch(
            "octop_memory.adapters.bridge.handlers.Bridge",
            side_effect=lambda memory: _FakeBridge(memory),
        ),
    ):
        cache = _MemoryCache(max_size=1)

        first_mem, first_bridge = _open(cache, "a1", "f1")
        # Fingerprint change replaces the entry: the old pair is released.
        second_mem, second_bridge = _open(cache, "a1", "f2")
        assert first_mem.closed and first_bridge.closed
        assert not second_mem.closed and not second_bridge.closed

        # Opening another agent evicts a1 (max_size=1): its pair is released.
        _open(cache, "a2", "f1")
        assert second_mem.closed and second_bridge.closed

        # invalidate() releases whatever remains.
        _open(cache, "a3", "f1")
        cache.invalidate()
        assert cache._entries == {}


def test_cache_keeps_instance_on_same_fingerprint() -> None:
    """Control: same fingerprint reuses the cached pair without closing it."""
    with (
        patch("octop_memory.core.Memory", side_effect=lambda **kw: _FakeMemory(kw["namespace"])),
        patch(
            "octop_memory.adapters.bridge.handlers.Bridge",
            side_effect=lambda memory: _FakeBridge(memory),
        ),
    ):
        cache = _MemoryCache(max_size=4)

        mem_a, bridge_a = _open(cache, "a1", "f1")
        mem_b, bridge_b = _open(cache, "a1", "f1")
        assert mem_a is mem_b and bridge_a is bridge_b
        assert not mem_a.closed and not bridge_a.closed


def test_close_failure_is_swallowed() -> None:
    """A raising close() must not break cache maintenance."""

    class _RaisingMemory(_FakeMemory):
        def close(self) -> None:
            raise RuntimeError("boom")

    mem = _RaisingMemory("ns")

    # Should not raise even though close() explodes.
    from octop.api.common.memory_client import _close_memory_instances

    _close_memory_instances(mem, _FakeBridge(mem))
