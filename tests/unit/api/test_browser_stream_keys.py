"""Browser WebSocket stream must forward non-printable keys as CDP key events.

Regression for dashboard issue #1374: the embedded browser dropped every
``keydown`` event except Enter, so Backspace/Delete/arrows did nothing.
"""

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
async def test_backspace_dispatches_cdp_key_down_and_up() -> None:
    sess = _fake_sess()
    await stream_mod._handle_client_event(sess, {"type": "keydown", "key": "Backspace"})
    calls = sess._internal.client.send.await_args_list
    assert [call.args[0] for call in calls] == [
        "Input.dispatchKeyEvent",
        "Input.dispatchKeyEvent",
    ]
    down = calls[0].args[1]
    up = calls[1].args[1]
    assert down["type"] == "rawKeyDown"
    assert down["key"] == "Backspace"
    assert down["code"] == "Backspace"
    assert down["windowsVirtualKeyCode"] == 8
    assert up["type"] == "keyUp"
    assert up["key"] == "Backspace"
    sess.type.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("key", "vk"),
    [
        ("Delete", 46),
        ("Tab", 9),
        ("Escape", 27),
        ("ArrowLeft", 37),
        ("ArrowUp", 38),
        ("ArrowRight", 39),
        ("ArrowDown", 40),
        ("Home", 36),
        ("End", 35),
        ("PageUp", 33),
        ("PageDown", 34),
    ],
)
async def test_navigation_keys_dispatch_cdp_key_events(key: str, vk: int) -> None:
    sess = _fake_sess()
    await stream_mod._handle_client_event(sess, {"type": "keydown", "key": key})
    calls = sess._internal.client.send.await_args_list
    assert len(calls) == 2
    down = calls[0].args[1]
    assert down["type"] == "rawKeyDown"
    assert down["key"] == key
    assert down["windowsVirtualKeyCode"] == vk
    assert calls[1].args[1]["type"] == "keyUp"


@pytest.mark.asyncio
async def test_unknown_key_is_ignored() -> None:
    sess = _fake_sess()
    await stream_mod._handle_client_event(sess, {"type": "keydown", "key": "F5"})
    sess._internal.client.send.assert_not_awaited()
    sess.type.assert_not_awaited()


@pytest.mark.asyncio
async def test_enter_keeps_newline_tab_path() -> None:
    sess = _fake_sess()
    await stream_mod._handle_client_event(sess, {"type": "keydown", "key": "Enter"})
    sess.type.assert_awaited_once_with("\n")
    sess._internal.client.send.assert_not_awaited()
