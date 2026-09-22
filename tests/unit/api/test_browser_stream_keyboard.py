"""The browser viewer forwards committed text and native editing keys through CDP."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from octop.api.routers.browser.stream import _handle_client_event


def _session() -> SimpleNamespace:
    return SimpleNamespace(_internal=SimpleNamespace(client=SimpleNamespace(send=AsyncMock())))


@pytest.mark.asyncio
async def test_committed_unicode_is_inserted_in_one_command() -> None:
    sess = _session()
    text = "你好，browser\n🙂"
    await _handle_client_event(sess, {"type": "type", "text": text})
    sess._internal.client.send.assert_awaited_once_with("Input.insertText", {"text": text})


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("key", "key_code"),
    [("Backspace", 8), ("Delete", 46), ("ArrowLeft", 37), ("ArrowRight", 39), ("Tab", 9)],
)
async def test_editing_keys_dispatch_down_and_up(key: str, key_code: int) -> None:
    sess = _session()
    await _handle_client_event(sess, {"type": "keydown", "key": key, "shiftKey": True})
    calls = sess._internal.client.send.await_args_list
    assert [c.args[1]["type"] for c in calls] == ["rawKeyDown", "keyUp"]
    for call in calls:
        assert call.args[0] == "Input.dispatchKeyEvent"
        assert call.args[1]["key"] == key
        assert call.args[1]["windowsVirtualKeyCode"] == key_code
        assert call.args[1]["modifiers"] == 8


@pytest.mark.asyncio
async def test_enter_is_a_real_keypress_not_inserted_newline() -> None:
    sess = _session()
    await _handle_client_event(sess, {"type": "keydown", "key": "Enter"})
    down, up = sess._internal.client.send.await_args_list
    assert down.args[1]["type"] == "keyDown"
    assert down.args[1]["key"] == "Enter"
    assert down.args[1]["text"] == "\r"
    assert up.args[1]["type"] == "keyUp"


@pytest.mark.asyncio
@pytest.mark.parametrize(("modifier", "mask"), [("metaKey", 4), ("ctrlKey", 2)])
async def test_select_all_works_across_client_and_server_platforms(
    modifier: str, mask: int
) -> None:
    sess = _session()
    await _handle_client_event(
        sess, {"type": "keydown", "key": "a", "code": "KeyA", "keyCode": 65, modifier: True}
    )
    down, up = sess._internal.client.send.await_args_list
    assert down.args[1]["commands"] == ["selectAll"]
    assert down.args[1]["modifiers"] == mask
    assert up.args[1]["code"] == "KeyA"
    assert up.args[1]["windowsVirtualKeyCode"] == 65


@pytest.mark.asyncio
async def test_empty_text_and_uncommitted_keys_are_ignored() -> None:
    sess = _session()
    for msg in [{"type": "type", "text": ""}, {"type": "keydown", "key": "Process"}]:
        await _handle_client_event(sess, msg)
    sess._internal.client.send.assert_not_awaited()
