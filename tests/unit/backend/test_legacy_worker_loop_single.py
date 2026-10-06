"""One adapter instance must own exactly one worker loop."""

from __future__ import annotations

import asyncio
import threading

from octop.infra.backend import compat


def test_concurrent_first_calls_share_one_worker_loop(monkeypatch):
    real_new_event_loop = asyncio.new_event_loop
    entered = threading.Semaphore(0)
    release = threading.Event()
    concurrent_entries = 0

    def _slow_new_event_loop():
        nonlocal concurrent_entries
        concurrent_entries += 1
        entered.release()
        release.wait(timeout=5)
        return real_new_event_loop()

    monkeypatch.setattr(asyncio, "new_event_loop", _slow_new_event_loop)

    backend = compat._LegacyProtocolBackend(inner=object())
    results: list[asyncio.AbstractEventLoop] = []
    lock = threading.Lock()

    def _call():
        loop = backend._worker_loop()
        with lock:
            results.append(loop)

    threads = [threading.Thread(target=_call, daemon=True) for _ in range(2)]
    for thread in threads:
        thread.start()
    # The first caller is inside initialization now.
    assert entered.acquire(timeout=5)
    # The second one must be waiting on the instance lock rather than starting a
    # second event loop - that is the whole point of serializing initialization.
    assert not entered.acquire(timeout=1.0), "a second worker loop was started concurrently"
    release.set()
    for thread in threads:
        thread.join(timeout=10)

    assert len(results) == 2, "both callers must return a loop"
    assert results[0] is results[1], "the adapter started more than one worker loop"
    assert concurrent_entries == 1, "initialization ran more than once"
