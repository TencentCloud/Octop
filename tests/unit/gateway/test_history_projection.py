from __future__ import annotations

import asyncio

import pytest

from octop.infra.gateway.history_backfill import HistoryBackfillQueue
from octop.infra.gateway.process.history_projection import TurnHistoryTracker


def test_turn_tracker_keeps_only_latest_user_turn_and_dedupes_replay() -> None:
    tracker = TurnHistoryTracker.from_request(
        {"messages": [{"role": "user", "content": "latest", "id": "u2"}]}
    )
    state = [
        {"role": "user", "content": "old", "id": "u1"},
        {"role": "assistant", "content": "old answer", "id": "a1"},
        {"role": "user", "content": "latest", "id": "u2"},
        {"role": "assistant", "content": "new answer", "id": "a2"},
    ]
    tracker.observe({"type": "state_snapshot", "data": {"messages": state}})
    tracker.observe({"type": "state_update", "data": {"messages": state}})

    assert [item.message_id for item in tracker.inputs] == ["u2", "a2"]


@pytest.mark.asyncio
async def test_backfill_queue_runs_one_job_at_a_time_and_dedupes() -> None:
    queue = HistoryBackfillQueue(max_pending=2)
    first_started = asyncio.Event()
    release_first = asyncio.Event()
    order: list[str] = []

    async def first() -> None:
        order.append("first:start")
        first_started.set()
        await release_first.wait()
        order.append("first:end")

    async def second() -> None:
        order.append("second")

    assert queue.enqueue("thr-1", first) is True
    assert queue.enqueue("thr-1", first) is True
    assert queue.enqueue("thr-2", second) is True
    assert queue.available_slots == 0
    assert queue.active_jobs == 2
    assert queue.contains("thr-1") is True
    await first_started.wait()
    assert order == ["first:start"]
    assert queue.available_slots == 1
    release_first.set()
    await asyncio.wait_for(queue._queue.join(), timeout=1)  # noqa: SLF001
    assert order == ["first:start", "first:end", "second"]
    assert queue.active_jobs == 0
    assert queue.available_slots == 2
    assert queue.contains("thr-1") is False
    await queue.close()
