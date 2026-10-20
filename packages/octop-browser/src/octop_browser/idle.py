"""Per-profile browser activity tracking and idle reaping."""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from octop_browser.profile import Profile
    from octop_browser.settings import OctopSettings

logger = logging.getLogger(__name__)

_CHECK_INTERVAL_SECONDS = 60.0
_LOCAL_CDP_HOSTS = {"localhost", "127.0.0.1", "::1"}
_controllers: dict[tuple[Path, str, int], BrowserIdleController] = {}


class BrowserIdleController:
    """Track real CDP activity and stop one local profile after a timeout."""

    def __init__(
        self,
        profile: Profile,
        cfg: OctopSettings,
        *,
        timeout_seconds: float,
        key: tuple[Path, str, int],
    ) -> None:
        self._profile = profile
        self._cfg = cfg
        self._timeout_seconds = timeout_seconds
        self._key = key
        self._last_activity = time.monotonic()
        self._active_commands = 0
        self._task: asyncio.Task[None] | None = None
        self._reaped = False
        self._reaping = False

    def start(self) -> None:
        if self._task is None and not self._reaped:
            self._task = asyncio.create_task(
                self._run(),
                name=f"browser-idle-{self._profile.name}",
            )

    def activity_started(self) -> None:
        if self._reaped:
            return
        self._active_commands += 1
        self._last_activity = time.monotonic()

    def activity_finished(self) -> None:
        if self._reaped:
            return
        self._active_commands = max(0, self._active_commands - 1)
        self._last_activity = time.monotonic()

    def _cancel_watchdog(self) -> None:
        task = self._task
        if task is None or task.done():
            return
        if task is asyncio.current_task():
            return
        task.cancel()

    async def reap_now(self) -> bool:
        """Stop this profile immediately and retire its idle controller."""
        if self._reaped or self._reaping:
            return False
        self._reaping = True
        from octop_browser.cdp.launcher import terminate_browser  # noqa: PLC0415
        from octop_browser.tool_interface import _drop_session  # noqa: PLC0415

        try:
            await _drop_session(self._profile.name)
            stopped = await terminate_browser(
                self._profile,
                cdp_host=self._cfg.cdp_host,
            )
        finally:
            self._reaping = False
        if not stopped:
            retry_delay = min(_CHECK_INTERVAL_SECONDS, self._timeout_seconds)
            self._last_activity = time.monotonic() - self._timeout_seconds + retry_delay
            return False

        self._reaped = True
        self._cancel_watchdog()
        current = _controllers.get(self._key)
        if current is self:
            _controllers.pop(self._key, None)
        return True

    async def _check_once(self) -> bool:
        if self._reaped or self._active_commands:
            return False
        idle_for = time.monotonic() - self._last_activity
        if idle_for < self._timeout_seconds:
            return False
        logger.info(
            "Browser profile %r idle for %.0fs; stopping Chrome",
            self._profile.name,
            idle_for,
        )
        return await self.reap_now()

    async def _run(self) -> None:
        try:
            while not self._reaped:
                remaining = self._timeout_seconds - (
                    time.monotonic() - self._last_activity
                )
                await asyncio.sleep(min(_CHECK_INTERVAL_SECONDS, max(remaining, 0.1)))
                await self._check_once()
        except asyncio.CancelledError:
            raise
        except Exception:  # pylint: disable=broad-except
            logger.exception(
                "Idle reaper failed for browser profile %r",
                self._profile.name,
            )
        finally:
            current = _controllers.get(self._key)
            if current is self and self._reaped:
                _controllers.pop(self._key, None)


def idle_controller_for(
    profile: Profile,
    cfg: OctopSettings,
) -> BrowserIdleController | None:
    """Return the shared local idle controller configured for ``profile``."""
    timeout_seconds = max(float(cfg.idle_timeout_minutes), 0.0) * 60.0
    if timeout_seconds <= 0 or cfg.cdp_ws_url or cfg.cdp_host not in _LOCAL_CDP_HOSTS:
        return None

    key = (Path(profile.data_dir).resolve(), cfg.cdp_host, profile.cdp_port)
    controller = _controllers.get(key)
    if controller is None or controller._reaped:
        controller = BrowserIdleController(
            profile,
            cfg,
            timeout_seconds=timeout_seconds,
            key=key,
        )
        _controllers[key] = controller
    return controller
