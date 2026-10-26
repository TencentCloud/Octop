"""Slash /delete refuses a non-bound thread while its turn is active."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from octop.i18n import error_message
from octop.infra.gateway.slash import BufferSink, SlashCommand
from octop.infra.gateway.slash.ctx import SlashCtx
from octop.infra.gateway.slash.handlers.session import cmd_delete
from octop.infra.gateway.ws import WebSocketHub


@pytest.mark.asyncio
async def test_cmd_delete_skips_checkpoint_when_non_bound_turn_is_active() -> None:
    target = SimpleNamespace(thread_id="thr_other_222222")
    registry = MagicMock()
    registry.get_bound_thread_id.return_value = "thr_bound_111111"
    registry.list_threads.return_value = [target]
    hub = WebSocketHub()
    hub.mark_turn_active(target.thread_id)
    manager = MagicMock()
    manager.delete_thread_checkpoint = AsyncMock()
    ctx = SlashCtx(
        agent_id="a1",
        user_id=1,
        channel_type="feishu",
        session_key="sk",
        thread_registry=registry,
        agent_manager=manager,
        locale="en",
        ws_hub=hub,
    )
    sink = BufferSink()

    await cmd_delete(MagicMock(), SlashCommand("delete", "222222"), ctx, sink)

    assert sink.lines == [error_message("THREAD_TURN_ACTIVE", "en")]
    manager.delete_thread_checkpoint.assert_not_awaited()
    registry.delete_thread.assert_not_called()
