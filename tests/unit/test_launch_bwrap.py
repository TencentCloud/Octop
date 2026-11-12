"""Tests for non-blocking bubblewrap provisioning in ``octop run``."""

from __future__ import annotations

import asyncio
import threading

import pytest

from octop import launch


@pytest.mark.parametrize("platform", ["darwin", "win32"])
def test_schedule_skips_non_linux(
    monkeypatch: pytest.MonkeyPatch,
    platform: str,
) -> None:
    monkeypatch.setattr(launch.sys, "platform", platform)
    assert launch._schedule_linux_bubblewrap_ensure() is None


@pytest.mark.asyncio
async def test_schedule_runs_linux_ensure_in_background(monkeypatch: pytest.MonkeyPatch) -> None:
    started = threading.Event()
    release = threading.Event()

    def ensure() -> None:
        started.set()
        release.wait(timeout=30)

    monkeypatch.setattr(launch, "_ensure_linux_bubblewrap", ensure)
    # Lie about the platform only for the schedule check. Leaving sys.platform
    # as "linux" on Windows breaks the running Proactor loop's thread wakeup,
    # so the background to_thread never starts.
    original_platform = launch.sys.platform
    monkeypatch.setattr(launch.sys, "platform", "linux")
    task = launch._schedule_linux_bubblewrap_ensure()
    monkeypatch.setattr(launch.sys, "platform", original_platform)
    assert task is not None
    try:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + 10
        while not started.is_set() and loop.time() < deadline and not task.done():
            await asyncio.sleep(0.05)
        if task.done() and not started.is_set():
            await task
        assert started.is_set()
        assert not task.done()
    finally:
        release.set()
    await task


@pytest.mark.asyncio
async def test_cancel_background_task_is_noop_when_missing() -> None:
    await launch._cancel_background_task(None)


@pytest.mark.asyncio
async def test_cancel_background_task_drops_pending() -> None:
    started = asyncio.Event()

    async def hang() -> None:
        started.set()
        await asyncio.sleep(60)

    task = asyncio.create_task(hang())
    await started.wait()
    await launch._cancel_background_task(task)
    assert task.cancelled() or task.done()


def test_background_ensure_swallows_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail() -> dict[str, str]:
        raise RuntimeError("boom")

    monkeypatch.setattr("octop.infra.utils.bwrap.ensure_bubblewrap", fail)
    launch._ensure_linux_bubblewrap()


def test_server_keeps_websocket_pings_but_ignores_late_pongs() -> None:
    assert launch._WS_PING_INTERVAL == 20.0
    assert launch._WS_PING_TIMEOUT is None
