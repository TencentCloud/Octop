"""In-process remote desktop session registry."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from octop.infra.desktop.capture import ScreenCapture
from octop.infra.desktop.input import InputInjector

_capture_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="desktop-capture")
_input_executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="desktop-input")

_MAX_DESKTOP_SESSIONS = 3
_sessions: dict[str, DesktopSession] = {}
_active_disconnects: dict[str, Callable[[], Awaitable[None]]] = {}
_lock = asyncio.Lock()

DisconnectHandler = Callable[[], Awaitable[None]]


class DesktopSessionLimitError(Exception):
    """Raised when the global concurrent desktop stream cap is reached."""

    def __init__(self, *, limit: int, active: int) -> None:
        self.limit = limit
        self.active = active
        super().__init__(f"desktop session limit exceeded ({active}/{limit})")


@dataclass
class DesktopSession:
    display: str | None
    monitor: int = 0
    capture: ScreenCapture = field(init=False)
    input: InputInjector = field(init=False)

    def __post_init__(self) -> None:
        self.capture = ScreenCapture(display=self.display, monitor=self.monitor)
        self.input = InputInjector(display=self.display)

    def close(self) -> None:
        self.capture.close()


async def supersede_user_stream(
    user_id: str,
    disconnect: DisconnectHandler,
) -> None:
    """Close any still-open stream for *user_id* before starting a new one."""
    async with _lock:
        prev = _active_disconnects.get(user_id)
        _active_disconnects[user_id] = disconnect
    if prev is not None and prev is not disconnect:
        await prev()


async def clear_user_stream(user_id: str, disconnect: DisconnectHandler) -> None:
    async with _lock:
        if _active_disconnects.get(user_id) is disconnect:
            _active_disconnects.pop(user_id, None)


async def disconnect_all_streams() -> None:
    """Close every active desktop WebSocket and release capture sessions."""
    async with _lock:
        handlers = list(_active_disconnects.values())
        sessions = list(_sessions.values())
        _active_disconnects.clear()
        _sessions.clear()
    for handler in handlers:
        with contextlib.suppress(Exception):
            await handler()
    for session in sessions:
        with contextlib.suppress(Exception):
            session.close()


async def acquire_session(
    *,
    user_id: str,
    display: str | None,
    monitor: int,
) -> DesktopSession:
    """Reserve a capture session for *user_id*, replacing any stale connection."""
    async with _lock:
        stale = _sessions.pop(user_id, None)
        if stale is not None:
            stale.close()

        if len(_sessions) >= _MAX_DESKTOP_SESSIONS:
            raise DesktopSessionLimitError(
                limit=_MAX_DESKTOP_SESSIONS,
                active=len(_sessions),
            )

        session = DesktopSession(display=display, monitor=monitor)

        _sessions[user_id] = session
        return session


async def release_session(*, user_id: str, session: DesktopSession | None) -> None:
    """Drop *session* only when it is still the active slot for *user_id*."""
    if session is None:
        return
    async with _lock:
        if _sessions.get(user_id) is session:
            _sessions.pop(user_id, None)
        session.close()


def active_session_count() -> int:
    return len(_sessions)


def session_limit() -> int:
    return _MAX_DESKTOP_SESSIONS


def capture_executor() -> ThreadPoolExecutor:
    return _capture_executor


def input_executor() -> ThreadPoolExecutor:
    return _input_executor
