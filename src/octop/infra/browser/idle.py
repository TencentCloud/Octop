"""Idle reaper for the Octop-managed browser.

harness-browser intentionally keeps its Chromium process running after a
session closes (profile reuse, sticky CDP targets), so on a headless server
a single browser use leaves a permanent ~500MB RSS / ~260MB PSS resident
process (see issue #485). This monitor periodically checks whether the
browser is actually in use and terminates it after a configurable idle
window. The next browser_tool / dashboard open relaunches it automatically
(``launch_or_attach`` + stale-lock cleanup in ``setup.py``).

Activity model (conservative, avoids killing a busy browser):

- ``notify_activity()`` — any Octop-side touch of the browser (session
  resolve, stream message, tab ops). Agent-driven ``browser_tool`` calls go
  through harness-browser directly and are not visible here, so activity is
  also inferred from the browser itself:
- active page targets (anything other than about:blank / chrome://newtab)
  count as in-use, and
- an open ``/api/browser-stream/ws`` connection counts as in-use.

A browser is reaped only when ALL of the following hold:

1. ``browser_idle_timeout_minutes > 0`` (opt-in),
2. no live stream WS connection,
3. no non-blank page target,
4. no ``notify_activity`` within the timeout window,
5. the CDP port still responds (Chrome is alive).

Reaping closes registered sessions (CDP connection) then kills the Chrome
process tree for the profile's user-data-dir (reuses ``pkill_chrome_profile``
from ``setup.py``); login cookies survive on disk, so relaunch is cheap.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 检查周期: 后台任务每 60s 跑一次, 判定期望在 timeout 窗口内多次命中
_CHECK_INTERVAL_S = 60.0

_BLANK_URLS = {"about:blank", "chrome://newtab/", "chrome://newtab"}


class BrowserIdleMonitor:
    """Track browser activity and reap the Chrome process after idle timeout."""

    def __init__(self, timeout_minutes: int, profiles_dir: Any) -> None:
        self._timeout_s = max(int(timeout_minutes), 0) * 60
        self._profiles_dir = profiles_dir
        self._last_activity = time.monotonic()
        self._stream_conns = 0
        self._task: asyncio.Task[None] | None = None

    @property
    def enabled(self) -> bool:
        return self._timeout_s > 0

    def notify_activity(self) -> None:
        """Record any Octop-side browser activity."""
        self._last_activity = time.monotonic()

    def notify_stream_open(self) -> None:
        self._stream_conns += 1
        self.notify_activity()

    def notify_stream_close(self) -> None:
        self._stream_conns = max(0, self._stream_conns - 1)
        self.notify_activity()

    def start(self) -> None:
        if not self.enabled or self._task is not None:
            return
        self._task = asyncio.create_task(self._run(), name="browser-idle-monitor")
        logger.info(
            "browser idle monitor started: reap after %ds without activity",
            self._timeout_s,
        )

    async def shutdown(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    # ------------------------------------------------------------------

    async def _run(self) -> None:
        while True:
            await asyncio.sleep(_CHECK_INTERVAL_S)
            try:
                await self._check_once()
            except Exception:  # noqa: BLE001 - never kill the loop
                logger.debug("browser idle check failed", exc_info=True)

    async def _check_once(self) -> None:
        if self._stream_conns > 0:
            return
        if time.monotonic() - self._last_activity < self._timeout_s:
            return
        if not await self._cdp_alive():
            return
        if await self._has_active_pages():
            self.notify_activity()  # 页面还在用, 重新计时
            return
        logger.info(
            "browser idle for %.0fs (timeout %ds), reaping Chrome",
            time.monotonic() - self._last_activity,
            self._timeout_s,
        )
        await self._reap()

    async def _cdp_alive(self) -> bool:
        try:
            import aiohttp

            from harness_browser.profile import ProfileManager  # noqa: PLC0415

            pm = ProfileManager(base_dir=self._profiles_dir)
            ports = [p.cdp_port for p in pm.list_profiles()] or [9222]
            async with aiohttp.ClientSession() as session:
                for port in ports:
                    try:
                        async with session.get(
                            f"http://127.0.0.1:{port}/json/version",
                            timeout=aiohttp.ClientTimeout(total=2),
                        ) as resp:
                            if resp.status == 200:
                                return True
                    except Exception:  # noqa: BLE001
                        continue
            return False
        except Exception:  # noqa: BLE001
            return False

    async def _has_active_pages(self) -> bool:
        try:
            import aiohttp

            from harness_browser.profile import ProfileManager  # noqa: PLC0415

            pm = ProfileManager(base_dir=self._profiles_dir)
            ports = [p.cdp_port for p in pm.list_profiles()] or [9222]
            async with aiohttp.ClientSession() as session:
                for port in ports:
                    try:
                        async with session.get(
                            f"http://127.0.0.1:{port}/json/list",
                            timeout=aiohttp.ClientTimeout(total=2),
                        ) as resp:
                            targets = await resp.json(content_type=None)
                        if any(
                            t.get("type") == "page"
                            and t.get("url") not in _BLANK_URLS
                            for t in targets
                            if isinstance(t, dict)
                        ):
                            return True
                    except Exception:  # noqa: BLE001
                        continue
            return False
        except Exception:  # noqa: BLE001
            return False

    async def _reap(self) -> None:
        # 1) 关闭 Octop 进程内缓存的 harness sessions (断 CDP 连接)
        try:
            from harness_browser.tool_interface import _registry  # noqa: PLC0415

            for name, sess in list(_registry.items()):
                _registry.pop(name, None)
                with contextlib.suppress(Exception):
                    await sess.close()
        except Exception:  # noqa: BLE001
            logger.debug("closing harness registry failed", exc_info=True)
        # 2) 按 user-data-dir 杀 Chrome 进程树 + 清锁
        #    不依赖 profiles_dir 配置推断：直接从运行中 Chrome 进程扫描实际
        #    user-data-dir（Octop 可能 relocate 到 /tmp/harness-browser-profiles-*）。
        try:
            import re
            import subprocess

            from octop.infra.browser.setup import (  # noqa: PLC0415
                clear_profile_locks,
                pkill_chrome_profile,
            )

            out = subprocess.run(
                ["pgrep", "-af", "chrome"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            ).stdout
            dirs = {Path(d) for d in re.findall(r"user-data-dir=([^\s]+)", out)}
            for d in dirs:
                await asyncio.to_thread(pkill_chrome_profile, d)
                await asyncio.to_thread(clear_profile_locks, d)
        except Exception as exc:  # noqa: BLE001
            logger.warning("browser reap failed: %s", exc)
        self._last_activity = time.monotonic()  # 防止紧接的重启风暴
        logger.info("browser reaped; next use will relaunch automatically")
