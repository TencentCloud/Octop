"""Capture failures must be visible without terminating a recoverable stream."""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from octop.api.routers.browser import stream as stream_mod


async def _capture_cycles(
    results: list[dict[str, Any] | Exception], *, listen_only: bool = False
) -> tuple[list[dict[str, Any]], AsyncMock]:
    send = AsyncMock(side_effect=results)
    session = SimpleNamespace(
        _internal=SimpleNamespace(_connected=True, client=SimpleNamespace(send=send))
    )
    checks = iter([True] * len(results) + [False])
    sent: list[dict[str, Any]] = []

    async def send_json(payload: dict[str, Any]) -> None:
        sent.append(payload)

    with (
        patch.object(stream_mod, "_send_session_snapshot", new=AsyncMock()),
        patch.object(stream_mod.asyncio, "sleep", new=AsyncMock()),
    ):
        await stream_mod._stream_loop(
            send_json, lambda: next(checks), session, "user-7", listen_only=listen_only
        )
    return sent, send


@pytest.mark.asyncio
async def test_repeated_capture_timeouts_report_error_once(
    caplog: pytest.LogCaptureFixture,
) -> None:
    sent, send = await _capture_cycles([TimeoutError() for _ in range(8)])

    assert send.await_count == 8
    assert [item["status"] for item in sent if item["type"] == "status"] == [
        "browser_started",
        "streaming",
        "error",
    ]
    warnings = [record for record in caplog.records if record.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "capture" in warnings[0].message
    assert "user-7" in warnings[0].message


@pytest.mark.asyncio
async def test_successful_frame_resets_transient_failure_count(
    caplog: pytest.LogCaptureFixture,
) -> None:
    sent, _ = await _capture_cycles([{}, {}, {"data": "frame-1"}, {}, {}, {"data": "frame-2"}])

    assert [item["status"] for item in sent if item["type"] == "status"] == [
        "browser_started",
        "streaming",
    ]
    assert [item["data"] for item in sent if item["type"] == "frame"] == ["frame-1", "frame-2"]
    assert not caplog.records


@pytest.mark.asyncio
async def test_capture_recovery_restores_streaming_and_allows_later_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    sent, _ = await _capture_cycles(
        [TimeoutError(), {}, {}, {"data": "frame-1"}, {}, {}, {}, {"data": "frame-2"}]
    )

    statuses_and_frames = [item for item in sent if item["type"] in {"status", "frame"}]
    assert statuses_and_frames == [
        {"type": "status", "status": "browser_started"},
        {"type": "status", "status": "streaming"},
        {"type": "status", "status": "error"},
        {"type": "status", "status": "streaming"},
        {"type": "frame", "data": "frame-1"},
        {"type": "status", "status": "error"},
        {"type": "status", "status": "streaming"},
        {"type": "frame", "data": "frame-2"},
    ]
    assert len([record for record in caplog.records if record.levelno == logging.WARNING]) == 2


@pytest.mark.asyncio
async def test_listen_only_loop_never_captures_or_reports_capture_failure(
    caplog: pytest.LogCaptureFixture,
) -> None:
    sent, send = await _capture_cycles([{}] * 8, listen_only=True)

    send.assert_not_awaited()
    assert not any(item.get("status") == "error" for item in sent)
    assert not caplog.records
