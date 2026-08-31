"""Browser idle monitor unit tests (issue #485 follow-up)."""

from __future__ import annotations

import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from octop.infra.browser.idle import BrowserIdleMonitor


def _monitor(timeout_minutes: int = 30) -> BrowserIdleMonitor:
    m = BrowserIdleMonitor(
        timeout_minutes=timeout_minutes,
        profiles_dir=Path("/tmp/octop-test-profiles"),
    )
    m._last_activity = time.monotonic() - (timeout_minutes * 60 + 60)  # 已超时
    return m


@pytest.mark.asyncio
async def test_disabled_when_timeout_zero() -> None:
    m = BrowserIdleMonitor(timeout_minutes=0, profiles_dir=Path("/tmp/x"))
    assert not m.enabled
    m.start()  # 不应启动任务
    assert m._task is None


@pytest.mark.asyncio
async def test_skip_when_stream_connection_open() -> None:
    m = _monitor()
    m.notify_stream_open()
    with patch.object(m, "_cdp_alive", new=AsyncMock(return_value=True)), patch.object(
        m, "_reap", new=AsyncMock()
    ):
        await m._check_once()
    m._reap.assert_not_awaited()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_skip_within_timeout_window() -> None:
    m = _monitor()
    m.notify_activity()  # 重置计时
    with patch.object(m, "_cdp_alive", new=AsyncMock(return_value=True)), patch.object(
        m, "_reap", new=AsyncMock()
    ):
        await m._check_once()
    m._reap.assert_not_awaited()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_skip_when_active_pages_present() -> None:
    m = _monitor()
    with patch.object(m, "_cdp_alive", new=AsyncMock(return_value=True)), patch.object(
        m, "_has_active_pages", new=AsyncMock(return_value=True)
    ), patch.object(m, "_reap", new=AsyncMock()):
        await m._check_once()
    m._reap.assert_not_awaited()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_reap_when_idle_and_no_pages() -> None:
    m = _monitor()
    with patch.object(m, "_cdp_alive", new=AsyncMock(return_value=True)), patch.object(
        m, "_has_active_pages", new=AsyncMock(return_value=False)
    ), patch.object(m, "_reap", new=AsyncMock()):
        await m._check_once()
    m._reap.assert_awaited_once()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_reap_ignores_missing_browser() -> None:
    m = _monitor()
    with patch.object(m, "_cdp_alive", new=AsyncMock(return_value=False)), patch.object(
        m, "_reap", new=AsyncMock()
    ):
        await m._check_once()
    m._reap.assert_not_awaited()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_reap_closes_registry_and_kills_chrome() -> None:
    """_reap 应关闭 _registry session 并 pkill 实际 user-data-dir 的 Chrome。"""
    m = _monitor()

    class _FakeSess:
        async def close(self) -> None:
            pass

    fake_registry = {"default": _FakeSess()}
    fake_pgrep = "1234 chrome --remote-debugging-port=9222 --user-data-dir=/tmp/prof/default\n"

    with (
        patch(
            "harness_browser.tool_interface._registry", fake_registry, create=True
        ),
        patch(
            "subprocess.run",
            return_value=SimpleNamespace(stdout=fake_pgrep),
        ) as mock_run,
        patch("octop.infra.browser.setup.pkill_chrome_profile", AsyncMock()),
        patch("octop.infra.browser.setup.clear_profile_locks", AsyncMock()),
    ):
        await m._reap()
    assert not fake_registry  # session 已弹出
    mock_run.assert_called()
