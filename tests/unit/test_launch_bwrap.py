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
        release.wait(timeout=5)

    monkeypatch.setattr(launch.sys, "platform", "linux")
    monkeypatch.setattr(launch, "_ensure_linux_bubblewrap", ensure)

    task = launch._schedule_linux_bubblewrap_ensure()
    assert task is not None
    try:
        assert await asyncio.to_thread(started.wait, 1)
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
