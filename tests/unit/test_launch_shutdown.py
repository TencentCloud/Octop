"""Shutdown signals must drain the process instead of killing it."""

from __future__ import annotations

import signal
from typing import Any
from unittest.mock import MagicMock

import pytest
import uvicorn

from octop.launch import (
    _capture_shutdown_signals,
    _OctopUvicornServer,
)


def _server() -> uvicorn.Server:
    config = uvicorn.Config(app=lambda scope, receive, send: None)  # type: ignore[arg-type]
    return _OctopUvicornServer(config)


def test_uvicorn_server_does_not_capture_signals() -> None:
    """``capture_signals`` is a no-op so uvicorn cannot re-raise SIGTERM."""
    server = _server()
    before = signal.getsignal(signal.SIGTERM)

    with server.capture_signals():
        assert signal.getsignal(signal.SIGTERM) is before

    assert signal.getsignal(signal.SIGTERM) is before


def test_first_signal_drains_and_second_forces_exit() -> None:
    srv = MagicMock()
    servers: list[Any] = [
        MagicMock(should_exit=False, force_exit=False),
        MagicMock(should_exit=False, force_exit=False),
    ]
    before = signal.getsignal(signal.SIGTERM)

    with _capture_shutdown_signals(servers, srv):
        handler = signal.getsignal(signal.SIGTERM)
        assert handler is not before
        # Returning normally is the point: uvicorn restores SIG_DFL and
        # re-raises, which kills the process before the drain can persist.
        handler(signal.SIGTERM, None)  # type: ignore[operator]

        assert [server.should_exit for server in servers] == [True, True]
        assert [server.force_exit for server in servers] == [False, False]
        srv.begin_shutdown.assert_called_once_with()

        handler(signal.SIGTERM, None)  # type: ignore[operator]
        assert [server.force_exit for server in servers] == [True, True]
        assert srv.begin_shutdown.call_count == 1

    assert signal.getsignal(signal.SIGTERM) is before


def test_begin_shutdown_failure_does_not_block_exit() -> None:
    srv = MagicMock()
    srv.begin_shutdown.side_effect = RuntimeError("boom")
    servers: list[Any] = [MagicMock(should_exit=False, force_exit=False)]

    with _capture_shutdown_signals(servers, srv):
        handler = signal.getsignal(signal.SIGTERM)
        handler(signal.SIGTERM, None)  # type: ignore[operator]

    assert servers[0].should_exit is True


def test_sigbreak_is_drained_on_windows() -> None:
    sigbreak = getattr(signal, "SIGBREAK", None)
    if sigbreak is None:
        pytest.skip("SIGBREAK is Windows only")

    srv = MagicMock()
    servers: list[Any] = [MagicMock(should_exit=False, force_exit=False)]

    with _capture_shutdown_signals(servers, srv):
        handler = signal.getsignal(sigbreak)
        handler(sigbreak, None)  # type: ignore[operator]

    assert servers[0].should_exit is True
