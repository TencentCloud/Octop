"""IM turns tell the owner's dashboard that the thread gained a turn."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from octop_gateway.models import ChannelSubject, InboundMessage, TextContent

from octop.infra.gateway.process.processor import GlobalProcessor
from octop.infra.gateway.slash.dispatcher import SlashDispatcher


def _build_processor(gateway: object) -> GlobalProcessor:
    agent_manager = MagicMock()
    agent_manager.merge_turn_mcp_servers = MagicMock(return_value=None)
    agent_manager.default_mcp_servers = MagicMock(return_value=[])
    agent_manager.default_knowledge_base_ids = MagicMock(return_value=[])
    agent_manager.prepare_chat_mcp = AsyncMock(return_value=[])
    agent_manager.get_row = MagicMock(return_value=None)
    agent_manager.providers = MagicMock()
    agent_manager.providers.is_model_ref_usable = MagicMock(return_value=False)
    agent_manager.providers.resolve_explicit_default_model = MagicMock(return_value=None)
    agent_manager.providers.resolve_model_for_multimodal_turn = MagicMock(
        side_effect=lambda ref, **_kwargs: ref
    )
    agent_manager.get_thread_model = MagicMock(return_value=None)

    thread_registry = MagicMock()
    thread_registry.get_or_create_by_key = AsyncMock(return_value="thr-im")

    agent_repo = MagicMock()
    agent_repo.get = MagicMock(return_value=MagicMock(user_id=7, default_model=None))

    return GlobalProcessor(
        agent_manager=agent_manager,
        thread_registry=thread_registry,
        audit_repo=MagicMock(),
        agent_repo=agent_repo,
        user_repo=MagicMock(),
        connector_repo=MagicMock(),
        dispatcher=SlashDispatcher(),
        usage_repo=None,
        gateway=gateway,
    )


def _qq_message() -> InboundMessage:
    return InboundMessage(
        channel_id="ch-qq",
        channel_type="qq",
        tenant_id="agent-1",
        channel_subject=ChannelSubject(subject_id="openid_1"),
        content=[TextContent(text="hello")],
    )


@pytest.mark.asyncio
async def test_im_turn_notifies_dashboard_after_history_is_written() -> None:
    order: list[str] = []

    async def fake_project_stream(_mgr, _aid, _request, **_kwargs):
        yield MagicMock()

    gateway = MagicMock()
    gateway.notify_thread_updated = AsyncMock(side_effect=lambda **_kwargs: order.append("notify"))
    processor = _build_processor(gateway)
    processor._record_turn_history = AsyncMock(  # type: ignore[method-assign]
        side_effect=lambda *_args, **_kwargs: order.append("history")
    )

    with patch(
        "octop.infra.gateway.process.processor.project_stream",
        new=fake_project_stream,
    ):
        events = [ev async for ev in processor(_qq_message())]

    assert events
    gateway.notify_thread_updated.assert_awaited_once_with(
        agent_id="agent-1", thread_id="thr-im", user_id=7
    )
    # The dashboard must not refetch before the projection is visible to it.
    assert order == ["history", "notify"]


@pytest.mark.asyncio
async def test_im_turn_notify_failure_does_not_break_the_turn() -> None:
    async def fake_project_stream(_mgr, _aid, _request, **_kwargs):
        yield MagicMock()

    gateway = MagicMock()
    gateway.notify_thread_updated = AsyncMock(side_effect=RuntimeError("socket down"))
    processor = _build_processor(gateway)

    with patch(
        "octop.infra.gateway.process.processor.project_stream",
        new=fake_project_stream,
    ):
        events = [ev async for ev in processor(_qq_message())]

    assert events
    assert events[-1].type.value == "completed"


@pytest.mark.asyncio
async def test_im_turn_without_gateway_still_completes() -> None:
    async def fake_project_stream(_mgr, _aid, _request, **_kwargs):
        yield MagicMock()

    processor = _build_processor(None)

    with patch(
        "octop.infra.gateway.process.processor.project_stream",
        new=fake_project_stream,
    ):
        events = [ev async for ev in processor(_qq_message())]

    assert events
