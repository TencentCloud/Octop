"""Listen-only browser-stream must not launch Chrome and must stay connected."""

from __future__ import annotations

import sys
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from starlette.websockets import WebSocketState

from octop.api.routers.browser import stream as stream_mod
from octop.api.routers.browser.harness import resolve_harness_session


class _FakeWs:
    def __init__(self) -> None:
        self.application_state = WebSocketState.CONNECTED
        self.sent: list[dict[str, Any]] = []
        self._ticks = 0

    async def send_text(self, raw: str) -> None:
        import json

        self.sent.append(json.loads(raw))
        self._ticks += 1
        # Exit the listen loop after a couple of snapshots.
        if self._ticks >= 4:
            self.application_state = WebSocketState.DISCONNECTED


@pytest.mark.asyncio
async def test_listen_state_loop_idle_without_session() -> None:
    ws = _FakeWs()
    with (
        patch.object(
            stream_mod,
            "resolve_harness_session",
            new=AsyncMock(return_value=None),
        ) as resolve,
        patch.object(stream_mod.asyncio, "sleep", new=AsyncMock()),
    ):
        await stream_mod._listen_state_loop(ws, "default")  # type: ignore[arg-type]

    assert resolve.await_count >= 1
    assert all(c.kwargs.get("create") is False for c in resolve.await_args_list)

    updates = [m for m in ws.sent if m.get("type") == "session_update"]
    assert updates
    assert updates[0]["state"] == "idle"
    assert updates[0]["session_id"] == "default"
    assert updates[0]["current_url"] == ""


@pytest.mark.asyncio
async def test_listen_state_loop_attaches_existing_session() -> None:
    ws = _FakeWs()
    sess = SimpleNamespace()
    with (
        patch.object(
            stream_mod,
            "resolve_harness_session",
            new=AsyncMock(return_value=sess),
        ) as resolve,
        patch.object(
            stream_mod,
            "harness_page_url",
            new=AsyncMock(return_value="https://example.com"),
        ),
        patch.object(
            stream_mod,
            "harness_list_tabs",
            new=AsyncMock(
                return_value=[
                    {
                        "id": "1",
                        "url": "https://example.com",
                        "title": "Ex",
                        "active": True,
                    }
                ]
            ),
        ),
        patch.object(stream_mod.asyncio, "sleep", new=AsyncMock()),
    ):
        await stream_mod._listen_state_loop(ws, "default")  # type: ignore[arg-type]

    assert all(c.kwargs.get("create") is False for c in resolve.await_args_list)
    updates = [m for m in ws.sent if m.get("type") == "session_update"]
    assert updates
    assert updates[0]["state"] == "streaming"
    assert updates[0]["current_url"] == "https://example.com"
    # No JPEG frames on the listen-only path.
    assert not any(m.get("type") == "frame" for m in ws.sent)


@pytest.mark.asyncio
async def test_resolve_harness_session_create_false_returns_none() -> None:
    fake_registry: dict[str, Any] = {}
    tool_iface = SimpleNamespace(_registry=fake_registry)
    hb = SimpleNamespace(BrowserSession=object, tool_interface=tool_iface)
    with patch.dict(
        sys.modules,
        {"harness_browser": hb, "harness_browser.tool_interface": tool_iface},
    ):
        result = await resolve_harness_session("default", create=False)
    assert result is None
