"""Host restore drains one middleware without stopping other experts."""

from __future__ import annotations

import threading
from types import SimpleNamespace

import pytest

from octop_harness.middleware.memory import MemoryMiddleware


def test_pause_drains_only_this_middleware_and_reopens_on_timeout():
    entered, release = threading.Event(), threading.Event()

    def extract(*args, **kwargs):
        entered.set()
        assert release.wait(3)

    middleware = MemoryMiddleware(service=SimpleNamespace(extract=extract), jsonl_enabled=False)
    middleware.end_session("one")
    assert entered.wait(1)
    with pytest.raises(TimeoutError), middleware.pause_background(timeout=0.01):
        pytest.fail("must not restore while extraction is running")
    release.set()
    with middleware.pause_background(timeout=2):
        middleware.end_session("blocked", background=False)
        assert middleware._background_active == 0
        other = MemoryMiddleware(service=SimpleNamespace(extract=lambda *a, **k: None), jsonl_enabled=False)
        other.end_session("other", background=False)
        other.shutdown()
    middleware.shutdown()


def test_pause_rejects_new_background_work_and_releases_after_exception():
    calls = []
    middleware = MemoryMiddleware(service=SimpleNamespace(extract=lambda *a, **k: calls.append(a)), jsonl_enabled=False)
    with pytest.raises(ValueError), middleware.pause_background(timeout=1):
        middleware.end_session("blocked", background=False)
        middleware.end_session("blocked-async")
        raise ValueError("restore rejected")
    assert not calls
    middleware.end_session("allowed", background=False)
    assert len(calls) == 1
    middleware.shutdown()
