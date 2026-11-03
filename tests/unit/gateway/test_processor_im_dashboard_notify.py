"""IM turns tell the Dashboard their thread changed (#2752).

IM channels never stream through the chat WebSocket, so an open Dashboard
session used to show nothing — not even the finished turn — until a manual
refresh. The processor now emits the same ``dashboard_push`` frame cron /
proactive turns already send, via ``Gateway.notify_thread_activity``.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from octop_gateway.models import ChannelSubject, InboundMessage, MessageEvent, TextContent

from octop.infra.gateway.process.processor import GlobalProcessor
from octop.infra.gateway.slash.dispatcher import SlashDispatcher


def _processor(gateway: MagicMock | None) -> GlobalProcessor:
    agent_manager = MagicMock()
    agent_manager.merge_turn_mcp_servers = MagicMock(return_value=None)
    agent_manager.default_mcp_servers = MagicMock(return_value=[])
    agent_manager.default_knowledge_base_ids = MagicMock(return_value=[])
    agent_manager.prepare_chat_mcp = AsyncMock(return_value=[])
    agent_manager.get_row = MagicMock(return_value=MagicMock(name="飞书专家"))
    agent_manager.providers = MagicMock()
    agent_manager.providers.is_model_ref_usable = MagicMock(return_value=False)
    agent_manager.providers.resolve_explicit_default_model = MagicMock(return_value=None)
    agent_manager.providers.resolve_model_for_multimodal_turn = MagicMock(
        side_effect=lambda ref, **_k: ref
    )
    agent_manager.get_thread_model = MagicMock(return_value=None)

    thread_registry = MagicMock()
    thread_registry.get_or_create_by_key = AsyncMock(return_value="thr-im")
    thread_registry.touch_last_active = MagicMock()
    thread_registry.set_title_if_null = MagicMock()

    return GlobalProcessor(
        agent_manager=agent_manager,
        thread_registry=thread_registry,
        audit_repo=MagicMock(),
        agent_repo=MagicMock(get=MagicMock(return_value=MagicMock(user_id=7, default_model=None))),
        user_repo=MagicMock(),
        connector_repo=MagicMock(),
        dispatcher=SlashDispatcher(),
        usage_repo=None,
        gateway=gateway,
    )


def _im_message(channel_type: str = "feishu") -> InboundMessage:
    return InboundMessage(
        channel_id="feishu",
        channel_type=channel_type,
        tenant_id="agent-1",
        channel_subject=ChannelSubject(subject_id="u1"),
        content=[TextContent(text="hello")],
    )


@pytest.mark.asyncio
async def test_im_turn_notifies_dashboard_thread_activity() -> None:
    gateway = MagicMock()
    gateway.notify_thread_activity = AsyncMock(return_value=None)

    async def fake_project_stream(_mgr, _aid, _request, **_kwargs):
        yield MessageEvent.delta("你好")
        yield MessageEvent.delta("，世界")

    with patch(
        "octop.infra.gateway.process.processor.project_stream",
        new=fake_project_stream,
    ):
        events = [ev async for ev in _processor(gateway)(_im_message())]

    assert events
    gateway.notify_thread_activity.assert_awaited_once_with(
        user_id=7,
        agent_id="agent-1",
        thread_id="thr-im",
        text="你好\n，世界",
    )


@pytest.mark.asyncio
async def test_dashboard_turn_does_not_notify_thread_activity() -> None:
    """The chat WebSocket already streams these turns — no push, no toast."""
    gateway = MagicMock()
    gateway.notify_thread_activity = AsyncMock(return_value=None)

    async def fake_project_stream(_mgr, _aid, _request, **_kwargs):
        yield MessageEvent.delta("hello")

    with patch(
        "octop.infra.gateway.process.processor.project_stream",
        new=fake_project_stream,
    ):
        events = [ev async for ev in _processor(gateway)(_im_message("dashboard"))]

    assert events
    gateway.notify_thread_activity.assert_not_awaited()


@pytest.mark.asyncio
async def test_im_turn_without_gateway_still_completes() -> None:
    async def fake_project_stream(_mgr, _aid, _request, **_kwargs):
        yield MessageEvent.delta("ok")

    with patch(
        "octop.infra.gateway.process.processor.project_stream",
        new=fake_project_stream,
    ):
        events = [ev async for ev in _processor(None)(_im_message())]

    assert events
    assert events[-1].type.value == "completed"
