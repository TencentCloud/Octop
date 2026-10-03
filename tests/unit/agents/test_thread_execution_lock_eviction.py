"""Thread execution locks must not accumulate, and must not be swapped while queued.

``#960`` added per-(agent, thread) locks so a dashboard turn and a HITL resume
cannot drive one LangGraph checkpoint concurrently. The map was never pruned
(``#995``), so a long-lived process kept one entry per thread ever seen.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from octop.infra.agents.manager import AgentManager


def _manager() -> AgentManager:
    manager = AgentManager.__new__(AgentManager)
    manager._harness_manager = SimpleNamespace(shared_factory=None)
    manager._thread_execution_locks = {}
    manager._thread_execution_lock_refs = {}
    return manager


async def test_lock_entries_are_evicted_once_turns_finish() -> None:
    """N finished threads leave nothing behind (before: N entries)."""
    manager = _manager()
    for i in range(50):
        async with manager._thread_execution_lock("01AGENT", f"thr-{i}"):
            pass
    assert manager._thread_execution_locks == {}
    assert manager._thread_execution_lock_refs == {}


async def test_queued_turn_keeps_the_same_lock_object() -> None:
    """A turn already waiting must not be handed a different, idle lock."""
    manager = _manager()
    concurrent = 0
    max_concurrent = 0
    seen: list[asyncio.Lock] = []

    async def turn() -> None:
        nonlocal concurrent, max_concurrent
        async with manager._thread_execution_lock("01AGENT", "thr") as lock:
            seen.append(lock)
            concurrent += 1
            max_concurrent = max(max_concurrent, concurrent)
            await asyncio.sleep(0.01)
            concurrent -= 1

    first = asyncio.create_task(turn())
    await asyncio.sleep(0.001)  # first turn now holds the lock
    second = asyncio.create_task(turn())
    await asyncio.sleep(0.001)  # second turn resolved the key and is queued
    third = asyncio.create_task(turn())  # resolves while the key is still live
    await asyncio.gather(first, second, third)

    assert max_concurrent == 1, "turns must never drive one checkpoint concurrently"
    assert len({id(lock) for lock in seen}) == 1, "queued turns must share one lock"
    assert manager._thread_execution_locks == {}


async def test_delete_evicts_idle_locks_but_keeps_live_ones() -> None:
    """Deleting an expert reclaims its entries, but never one with a live turn."""
    manager = _manager()
    async with manager._thread_execution_lock("01AGENT", "idle"):
        pass
    # A finished turn leaves nothing behind, so there is nothing to reclaim here.
    assert manager._thread_execution_locks == {}

    async def held() -> None:
        async with manager._thread_execution_lock("01AGENT", "busy"):
            await asyncio.sleep(0.05)

    task = asyncio.create_task(held())
    await asyncio.sleep(0.001)  # the turn now holds ("01AGENT", "busy")

    manager._evict_idle_thread_locks("01AGENT")

    # Deleting the expert must not orphan the running turn onto a fresh lock.
    assert ("01AGENT", "busy") in manager._thread_execution_locks
    await task
    assert manager._thread_execution_locks == {}
