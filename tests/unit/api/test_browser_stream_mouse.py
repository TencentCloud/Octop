"""Browser WebSocket stream must forward press / move / release for drag."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from octop.api.routers.browser import stream as stream_mod


def _fake_sess() -> SimpleNamespace:
    client = SimpleNamespace(send=AsyncMock(return_value={}))
    return SimpleNamespace(
        click=AsyncMock(),
        scroll=AsyncMock(),
        type=AsyncMock(),
        _internal=SimpleNamespace(client=client),
    )


@pytest.mark.asyncio
async def test_mousedown_dispatches_cdp_mouse_pressed() -> None:
    sess = _fake_sess()
    await stream_mod._handle_client_event(
        sess, {"type": "mousedown", "x": 40, "y": 80, "button": "left"}
    )
    sess._internal.client.send.assert_awaited()
    method, params = sess._internal.client.send.await_args.args
    assert method == "Input.dispatchMouseEvent"
    assert params["type"] == "mousePressed"
    assert params["x"] == 40
    assert params["y"] == 80
    assert params["button"] == "left"
    assert params.get("clickCount") == 1


@pytest.mark.asyncio
async def test_mousemove_dispatches_cdp_mouse_moved() -> None:
    sess = _fake_sess()
    await stream_mod._handle_client_event(
        sess, {"type": "mousemove", "x": 55, "y": 90, "button": "left"}
    )
    method, params = sess._internal.client.send.await_args.args
    assert method == "Input.dispatchMouseEvent"
    assert params["type"] == "mouseMoved"
    assert params["x"] == 55
    assert params["y"] == 90


@pytest.mark.asyncio
async def test_mouseup_dispatches_cdp_mouse_released() -> None:
    sess = _fake_sess()
    await stream_mod._handle_client_event(
        sess, {"type": "mouseup", "x": 70, "y": 100, "button": "left"}
    )
    method, params = sess._internal.client.send.await_args.args
    assert method == "Input.dispatchMouseEvent"
    assert params["type"] == "mouseReleased"
    assert params["x"] == 70
    assert params["y"] == 100
    assert params["button"] == "left"


@pytest.mark.asyncio
async def test_drag_sequence_preserves_pressed_buttons_on_move() -> None:
    sess = _fake_sess()
    await stream_mod._handle_client_event(
        sess, {"type": "mousedown", "x": 10, "y": 20, "button": "left", "buttons": 1}
    )
    await stream_mod._handle_client_event(
        sess, {"type": "mousemove", "x": 30, "y": 40, "button": "left", "buttons": 1}
    )
    await stream_mod._handle_client_event(
        sess, {"type": "mouseup", "x": 30, "y": 40, "button": "left", "buttons": 0}
    )
    calls = sess._internal.client.send.await_args_list
    assert len(calls) >= 3
    pressed = calls[0].args[1]
    moved = calls[1].args[1]
    released = calls[2].args[1]
    assert pressed["type"] == "mousePressed"
    assert pressed["buttons"] == 1
    assert moved["type"] == "mouseMoved"
    assert moved["buttons"] == 1
    assert released["type"] == "mouseReleased"
    assert released["buttons"] == 0


@pytest.mark.asyncio
async def test_mousemove_hover_uses_buttons_zero() -> None:
    sess = _fake_sess()
    await stream_mod._handle_client_event(
        sess,
        {
            "type": "mousemove",
            "x": 12,
            "y": 34,
            "button": "none",
            "buttons": 0,
        },
    )
    method, params = sess._internal.client.send.await_args.args
    assert method == "Input.dispatchMouseEvent"
    assert params["type"] == "mouseMoved"
    assert params["button"] == "none"
    assert params["buttons"] == 0


@pytest.mark.asyncio
async def test_mousedown_forwards_click_count() -> None:
    sess = _fake_sess()
    await stream_mod._handle_client_event(
        sess,
        {
            "type": "mousedown",
            "x": 1,
            "y": 2,
            "button": "left",
            "buttons": 1,
            "clickCount": 2,
        },
    )
    _method, params = sess._internal.client.send.await_args.args
    assert params["type"] == "mousePressed"
    assert params["clickCount"] == 2


@pytest.mark.asyncio
async def test_right_mousedown_uses_right_button_mask() -> None:
    sess = _fake_sess()
    await stream_mod._handle_client_event(
        sess, {"type": "mousedown", "x": 5, "y": 6, "button": "right", "buttons": 2}
    )
    _method, params = sess._internal.client.send.await_args.args
    assert params["type"] == "mousePressed"
    assert params["button"] == "right"
    assert params["buttons"] == 2
