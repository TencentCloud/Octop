"""Resource exhaustion must not emit a traceback for every accept attempt."""

from __future__ import annotations

import asyncio
import errno
import logging

import pytest

from octop.infra.utils.accept_errors import coalesce_accept_errors


@pytest.mark.asyncio
async def test_accept_burst_keeps_first_traceback_and_flushes_count(caplog):
    loop = asyncio.get_running_loop()
    previous = loop.get_exception_handler()
    context = {
        "message": "socket.accept() out of system resource",
        "exception": OSError(errno.EMFILE, "Too many open files"),
    }
    with caplog.at_level(logging.WARNING), coalesce_accept_errors(loop):
        for _ in range(2048):
            loop.call_exception_handler(context)
        assert len(caplog.records) == 1
        assert caplog.records[0].exc_info[1] is context["exception"]
    assert loop.get_exception_handler() is previous
    assert len(caplog.records) == 2
    assert "2047" in caplog.records[-1].getMessage()


@pytest.mark.asyncio
async def test_other_exceptions_reach_existing_handler():
    loop = asyncio.get_running_loop()
    previous = loop.get_exception_handler()
    seen = []

    def handler(_loop, context):
        seen.append(context)

    loop.set_exception_handler(handler)
    contexts = [
        {"message": "task failed", "exception": OSError(errno.EMFILE, "file open failed")},
        {
            "message": "socket.accept() out of system resource",
            "exception": OSError(errno.EBADF, "bad fd"),
        },
    ]
    try:
        with coalesce_accept_errors(loop):
            for context in contexts:
                loop.call_exception_handler(context)
        assert seen == contexts
        assert loop.get_exception_handler() is handler
    finally:
        loop.set_exception_handler(previous)


@pytest.mark.asyncio
async def test_window_flushes_while_the_server_keeps_running(monkeypatch, caplog):
    from octop.infra.utils import accept_errors

    monkeypatch.setattr(accept_errors, "ACCEPT_ERROR_WINDOW_SECONDS", 0)
    loop = asyncio.get_running_loop()
    context = {
        "message": "socket.accept() out of system resource",
        "exception": OSError(errno.ENFILE, "file table overflow"),
    }
    with caplog.at_level(logging.WARNING), coalesce_accept_errors(loop):
        for _ in range(3):
            loop.call_exception_handler(context)
        await asyncio.sleep(0.001)
        assert len(caplog.records) == 2
        assert "2 additional" in caplog.records[-1].getMessage()
        loop.call_exception_handler(context)
        assert len(caplog.records) == 3
