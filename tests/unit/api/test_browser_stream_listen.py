"""Listen-only browser-stream must not launch Chrome and must stay connected."""

from __future__ import annotations

import sys
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from octop.api.routers.browser import stream as stream_mod
from octop.api.routers.browser.harness import resolve_harness_session


class _ListenProbe:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []
        self._ticks = 0
        self._connected = True

    async def send_json(self, payload: dict[str, Any]) -> None:
        self.sent.append(payload)
        self._ticks += 1
        # Exit the listen loop after a couple of snapshots.
        if self._ticks >= 4:
            self._connected = False

    def is_connected(self) -> bool:
        return self._connected


@pytest.mark.asyncio
async def test_listen_state_loop_idle_without_session() -> None:
    probe = _ListenProbe()
    with (
        patch.object(
            stream_mod,
            "resolve_harness_session",
            new=AsyncMock(return_value=None),
        ) as resolve,
        patch.object(stream_mod.asyncio, "sleep", new=AsyncMock()),
    ):
        await stream_mod._listen_state_loop(probe.send_json, probe.is_connected, "default")

    assert resolve.await_count >= 1
    assert all(c.kwargs.get("create") is False for c in resolve.await_args_list)

    updates = [m for m in probe.sent if m.get("type") == "session_update"]
    assert updates
    assert updates[0]["state"] == "idle"
    assert updates[0]["session_id"] == "default"
    assert updates[0]["current_url"] == ""


@pytest.mark.asyncio
async def test_listen_state_loop_attaches_existing_session() -> None:
    probe = _ListenProbe()
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
        await stream_mod._listen_state_loop(probe.send_json, probe.is_connected, "default")

    assert all(c.kwargs.get("create") is False for c in resolve.await_args_list)
    updates = [m for m in probe.sent if m.get("type") == "session_update"]
    assert updates
    assert updates[0]["state"] == "streaming"
    assert updates[0]["current_url"] == "https://example.com"
    # No JPEG frames on the listen-only path.
    assert not any(m.get("type") == "frame" for m in probe.sent)


@pytest.mark.asyncio
async def test_resolve_harness_session_create_false_returns_none() -> None:
    fake_registry: dict[str, Any] = {}
    tool_iface = SimpleNamespace(_registry=fake_registry)
    hb = SimpleNamespace(BrowserSession=object, tool_interface=tool_iface)
    with patch.dict(
        sys.modules,
        {"octop_browser": hb, "octop_browser.tool_interface": tool_iface},
    ):
        result = await resolve_harness_session("default", create=False)
    assert result is None


@pytest.mark.asyncio
async def test_resolve_harness_session_never_falls_back_to_another_profile() -> None:
    other_session = object()
    tool_iface = SimpleNamespace(_registry={"user-2": other_session})
    hb = SimpleNamespace(BrowserSession=object, tool_interface=tool_iface)
    with patch.dict(
        sys.modules,
        {"octop_browser": hb, "octop_browser.tool_interface": tool_iface},
    ):
        result = await resolve_harness_session("user-1", create=False)
    assert result is None


@pytest.mark.asyncio
async def test_resolve_harness_session_create_true_rejects_empty_hint() -> None:
    from octop.infra.errors import OctopError

    fake_registry: dict[str, Any] = {"user-2": object()}
    tool_iface = SimpleNamespace(_registry=fake_registry)
    hb = SimpleNamespace(BrowserSession=object, tool_interface=tool_iface)
    with (
        patch.dict(
            sys.modules,
            {"octop_browser": hb, "octop_browser.tool_interface": tool_iface},
        ),
        pytest.raises(OctopError, match="browser profile is required"),
    ):
        await resolve_harness_session("auto", create=True)
