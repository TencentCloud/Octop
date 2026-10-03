"""Browser stream viewport values stay within Chromium-safe bounds."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from octop.api.routers.browser import stream as stream_mod


def _fake_session() -> SimpleNamespace:
    return SimpleNamespace(
        navigate=AsyncMock(),
        _internal=SimpleNamespace(client=SimpleNamespace(send=AsyncMock(return_value={}))),
    )


def test_normalize_viewport_clamps_each_dimension() -> None:
    assert stream_mod.normalize_viewport(1, 100_000) == (
        stream_mod.MIN_VIEWPORT_DIMENSION,
        stream_mod.MAX_VIEWPORT_DIMENSION,
    )


def test_normalize_viewport_uses_default_for_nonpositive_or_malformed_values() -> None:
    assert stream_mod.normalize_viewport(0, 800, default=(1280, 800)) == (1280, 800)
    assert stream_mod.normalize_viewport("wide", 800, default=(1280, 800)) == (1280, 800)
    assert stream_mod.normalize_viewport(-1, 800) is None


@pytest.mark.asyncio
async def test_resize_clamps_dimensions_before_sending_to_cdp() -> None:
    sess = _fake_session()

    await stream_mod._handle_client_event(
        sess,
        {"type": "resize", "width": 100_000, "height": 1},
    )

    method, params = sess._internal.client.send.await_args.args
    assert method == "Emulation.setDeviceMetricsOverride"
    assert params["width"] == stream_mod.MAX_VIEWPORT_DIMENSION
    assert params["height"] == stream_mod.MIN_VIEWPORT_DIMENSION


@pytest.mark.asyncio
async def test_start_clamps_dimensions_before_sending_to_cdp() -> None:
    sess = _fake_session()
    send_json = AsyncMock()

    with (
        patch.object(stream_mod, "resolve_harness_session", new=AsyncMock(return_value=sess)),
        patch.object(stream_mod, "_stream_loop", new=AsyncMock()),
    ):
        await stream_mod.run_browser_stream_session(
            send_json=send_json,
            is_connected=lambda: True,
            receive_text=AsyncMock(return_value={"type": "stop"}),
            user_id=1,
            start_msg={"type": "start", "width": 100_000, "height": 1},
        )

    method, params = sess._internal.client.send.await_args.args
    assert method == "Emulation.setDeviceMetricsOverride"
    assert params["width"] == stream_mod.MAX_VIEWPORT_DIMENSION
    assert params["height"] == stream_mod.MIN_VIEWPORT_DIMENSION
