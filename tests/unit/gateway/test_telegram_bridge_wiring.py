"""Telegram channels must be registered behind the host bridge."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from tests.unit.gateway.test_gateway_probe import _fake_row, _make_gateway

from octop.infra.gateway.channels.telegram_bridge import TelegramBridge
from octop.infra.gateway.gateway import Gateway


async def _registered_processor(gw: Gateway, kind: str, config_json: str):
    gw._processor = MagicMock()
    gw._channel_manager = MagicMock()
    gw._channel_manager.add_channel = AsyncMock()
    gw._channel_manager.get_channel = MagicMock(return_value=None)
    row = _fake_row()
    row.kind = kind
    row.config_json = config_json
    await gw._register_channel(row)
    return gw._channel_manager.add_channel.call_args.kwargs["processor"]


@pytest.mark.asyncio
async def test_telegram_channel_is_wrapped_by_bridge(tmp_path) -> None:
    gw = _make_gateway(tmp_path)
    processor = await _registered_processor(gw, "telegram", '{"bot_token":"123:abc"}')
    assert isinstance(processor, TelegramBridge)
    assert not isinstance(processor.processor, TelegramBridge)


@pytest.mark.asyncio
async def test_other_channels_are_not_wrapped(tmp_path) -> None:
    gw = _make_gateway(tmp_path)
    processor = await _registered_processor(gw, "feishu", '{"app_id":"x","app_secret":"y"}')
    assert not isinstance(processor, TelegramBridge)
