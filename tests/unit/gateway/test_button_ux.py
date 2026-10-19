"""Telegram 按钮选择收尾交互的单元测试。"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from octop_gateway.channels.telegram.channel import TelegramChannel

import octop.infra.gateway.channels.telegram_button_ux as ux


def _make_channel(invoke_return: bool) -> TelegramChannel:
    ch = TelegramChannel.__new__(TelegramChannel)
    ch.interactions = SimpleNamespace(invoke=AsyncMock(return_value=invoke_return))

    async def fake_request(method, **kwargs):
        await method(**kwargs)

    ch._request = fake_request
    ch._app = SimpleNamespace(
        bot=SimpleNamespace(
            edit_message_text=AsyncMock(),
            edit_message_reply_markup=AsyncMock(),
        )
    )
    return ch


def _make_query(label: str, text: str = "Pick one"):
    button = SimpleNamespace(text=label, callback_data="tok1")
    return SimpleNamespace(
        data="tok1",
        from_user=SimpleNamespace(id=42),
        message=SimpleNamespace(
            chat=SimpleNamespace(id=555),
            message_id=9,
            text=text,
            message_thread_id=None,
            reply_markup=SimpleNamespace(inline_keyboard=[[button]]),
        ),
        answer=AsyncMock(),
    )


@pytest.fixture(autouse=True)
def _install():
    ux.install()
    yield


async def _run(ch, query):
    await TelegramChannel.__dict__["_handle_callback"](
        ch, SimpleNamespace(callback_query=query), None
    )
    await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_valid_choice_toasts_and_appends():
    ch = _make_channel(True)
    query = _make_query("Alpha")
    await _run(ch, query)
    query.answer.assert_awaited_once()
    assert query.answer.await_args.kwargs.get("text") == "✓ Alpha"
    ch._app.bot.edit_message_text.assert_awaited_once()
    assert ch._app.bot.edit_message_text.await_args.kwargs["text"] == "Pick one\n✓ Alpha"


@pytest.mark.asyncio
async def test_expired_choice_removes_keyboard():
    ch = _make_channel(False)
    query = _make_query("Alpha")
    await _run(ch, query)
    assert query.answer.await_args.kwargs.get("text") == ux._EXPIRED_NOTE
    ch._app.bot.edit_message_text.assert_awaited_once()
    assert "失效" in ch._app.bot.edit_message_text.await_args.kwargs["text"]


@pytest.mark.asyncio
async def test_page_arrow_only_strips_markup():
    ch = _make_channel(True)
    query = _make_query("→")
    await _run(ch, query)
    ch._app.bot.edit_message_reply_markup.assert_awaited_once()
    ch._app.bot.edit_message_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_stop_button_skips_settle():
    ch = _make_channel(True)
    query = _make_query("Stop")
    await _run(ch, query)
    ch._app.bot.edit_message_text.assert_not_awaited()
    ch._app.bot.edit_message_reply_markup.assert_not_awaited()
