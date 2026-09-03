"""WeChat/QQ turns notify an open dashboard view after history is written."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from harness_gateway.models import ChannelSubject, InboundMessage, TextContent

from octop.infra.gateway.process.processor import GlobalProcessor
from octop.infra.gateway.slash.dispatcher import SlashDispatcher


def _im_processor(*, channel_type: str, hub: MagicMock | None) -> GlobalProcessor:
    agent_manager = MagicMock()
    agent_manager.merge_turn_mcp_servers = MagicMock(return_value=None)
    agent_manager.prepare_chat_mcp = AsyncMock(return_value=[])
    agent_manager.get_row = MagicMock(return_value=None)
    agent_manager.providers = MagicMock()
    agent_manager.providers.is_model_ref_usable = MagicMock(return_value=False)
    agent_manager.providers.resolve_explicit_default_model = MagicMock(return_value=None)
    agent_manager.providers.resolve_model_for_multimodal_turn = MagicMock(
        side_effect=lambda ref, **_k: ref
    )
    agent_manager.get_thread_model = MagicMock(return_value=None)

    thread_registry = MagicMock()
    thread_registry.get_or_create_by_key = AsyncMock(return_value="thr-wx")
    thread_registry.touch_last_active = MagicMock()
    thread_registry.set_title_if_null = MagicMock()

    gateway = None
    if hub is not None:
        gateway = MagicMock()
        gateway.ws_hub = hub

    return GlobalProcessor(
        agent_manager=agent_manager,
        thread_registry=thread_registry,
        audit_repo=MagicMock(),
        agent_repo=MagicMock(get=MagicMock(return_value=MagicMock(user_id=7, default_model=None))),
        user_repo=MagicMock(),
        connector_repo=MagicMock(),
        dispatcher=SlashDispatcher(),
        usage_repo=None,
        thread_message_repo=MagicMock(),
        gateway=gateway,
    )


def _inbound(channel_type: str) -> InboundMessage:
    return InboundMessage(
        channel_id=channel_type,
        channel_type=channel_type,
        tenant_id="agent-1",
        channel_subject=ChannelSubject(subject_id="wx-user"),
        content=[TextContent(text="你好")],
    )


async def _empty_stream(_mgr, _aid, _request, **_kwargs):
    if False:
        yield None


@pytest.mark.asyncio
@pytest.mark.parametrize("channel_type", ["weixin", "qq"])
async def test_im_turn_notifies_history_ready(channel_type: str) -> None:
    hub = MagicMock()
    hub.push_to_user = AsyncMock()
    processor = _im_processor(channel_type=channel_type, hub=hub)

    with patch(
        "octop.infra.gateway.process.processor.project_stream",
        new=_empty_stream,
    ):
        events = [ev async for ev in processor(_inbound(channel_type))]

    assert events
    hub.push_to_user.assert_awaited_once_with(
        7,
        {
            "type": "history_ready",
            "agent_id": "agent-1",
            "thread_id": "thr-wx",
            "channel_type": channel_type,
        },
    )


@pytest.mark.asyncio
async def test_feishu_turn_does_not_notify_history_ready() -> None:
    hub = MagicMock()
    hub.push_to_user = AsyncMock()
    processor = _im_processor(channel_type="feishu", hub=hub)

    with patch(
        "octop.infra.gateway.process.processor.project_stream",
        new=_empty_stream,
    ):
        [ev async for ev in processor(_inbound("feishu"))]

    hub.push_to_user.assert_not_called()


@pytest.mark.asyncio
async def test_weixin_history_ready_failure_does_not_fail_turn() -> None:
    hub = MagicMock()
    hub.push_to_user = AsyncMock(side_effect=RuntimeError("hub down"))
    processor = _im_processor(channel_type="weixin", hub=hub)

    with patch(
        "octop.infra.gateway.process.processor.project_stream",
        new=_empty_stream,
    ):
        events = [ev async for ev in processor(_inbound("weixin"))]

    assert events
    hub.push_to_user.assert_awaited_once()
