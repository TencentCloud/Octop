"""GlobalProcessor turn-scoped conversation_mode configurable stamp (#616)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from harness_gateway.models import ChannelSubject, InboundMessage, TextContent

from octop.infra.gateway.process.processor import GlobalProcessor
from octop.infra.gateway.slash.dispatcher import SlashDispatcher


def _processor(agent_manager: MagicMock) -> GlobalProcessor:
    thread_registry = MagicMock()
    thread_registry.get_or_create_by_key = AsyncMock(return_value="thr-1")
    thread_registry.touch_last_active = MagicMock()
    thread_registry.set_title_if_null = MagicMock()
    return GlobalProcessor(
        agent_manager=agent_manager,
        thread_registry=thread_registry,
        audit_repo=MagicMock(),
        agent_repo=MagicMock(get=MagicMock(return_value=MagicMock(user_id=1, default_model=None))),
        user_repo=MagicMock(get=MagicMock(return_value=None)),
        connector_repo=MagicMock(),
        dispatcher=SlashDispatcher(),
        usage_repo=None,
        gateway=None,
    )


def _agent_manager() -> MagicMock:
    mgr = MagicMock()
    mgr.merge_turn_mcp_servers = MagicMock(return_value=None)
    mgr.prepare_chat_mcp = AsyncMock(return_value=[])
    mgr.get_row = MagicMock(return_value=None)
    mgr.get_config = MagicMock(return_value={"tools_disabled": ["web_fetch"]})
    mgr.sync_effective_tools_disabled = MagicMock()
    mgr.sync_tools_disabled = MagicMock()
    mgr.providers = MagicMock()
    mgr.providers.is_model_ref_usable = MagicMock(return_value=False)
    mgr.providers.resolve_explicit_default_model = MagicMock(return_value=None)
    mgr.providers.resolve_model_for_multimodal_turn = MagicMock(side_effect=lambda ref, **_k: ref)
    mgr.providers.get_model_reasoning_capability = MagicMock(return_value=None)
    mgr.get_thread_model = MagicMock(return_value=None)

    async def fake_stream(_aid: str, _req: dict):
        yield {"type": "token", "content": "ok"}

    mgr.stream = fake_stream
    return mgr


@pytest.mark.asyncio
async def test_dashboard_request_stamps_conversation_mode_ask() -> None:
    processor = _processor(_agent_manager())
    msg = InboundMessage(
        channel_id="ws",
        channel_type="dashboard",
        tenant_id="agent-1",
        channel_subject=ChannelSubject(subject_id="1"),
        content=[TextContent(text="hi")],
        metadata={"conversation_mode": "ask"},
    )
    request = await processor._build_dashboard_request(
        msg,
        agent_id="agent-1",
        user_id=1,
        session_key="sk",
        thread_id="thr",
        meta=msg.metadata or {},
    )
    assert (request.get("configurable") or {})["conversation_mode"] == "ask"
    hint = (request.get("configurable") or {}).get("conversation_mode_hint")
    assert isinstance(hint, str) and hint


@pytest.mark.asyncio
async def test_dashboard_request_stamps_plan_system_hint() -> None:
    """Plan turn attaches plan-mode system hint for ConversationModeMiddleware."""
    processor = _processor(_agent_manager())
    msg = InboundMessage(
        channel_id="ws",
        channel_type="dashboard",
        tenant_id="agent-1",
        channel_subject=ChannelSubject(subject_id="1"),
        content=[TextContent(text="plan it")],
        metadata={"conversation_mode": "plan"},
    )
    request = await processor._build_dashboard_request(
        msg,
        agent_id="agent-1",
        user_id=1,
        session_key="sk",
        thread_id="thr",
        meta=msg.metadata or {},
    )
    cfg = request.get("configurable") or {}
    assert cfg["conversation_mode"] == "plan"
    hint = str(cfg.get("conversation_mode_hint") or "")
    assert "plan" in hint.lower() or "想一想" in hint
    assert "write_todos" in hint.lower() or "plan" in hint.lower()


@pytest.mark.asyncio
async def test_dashboard_request_defaults_conversation_mode_to_craft() -> None:
    processor = _processor(_agent_manager())
    msg = InboundMessage(
        channel_id="ws",
        channel_type="dashboard",
        tenant_id="agent-1",
        channel_subject=ChannelSubject(subject_id="1"),
        content=[TextContent(text="hi")],
        metadata={},
    )
    request = await processor._build_dashboard_request(
        msg,
        agent_id="agent-1",
        user_id=1,
        session_key="sk",
        thread_id="thr",
        meta={},
    )
    assert (request.get("configurable") or {})["conversation_mode"] == "craft"


@pytest.mark.asyncio
async def test_dashboard_request_stamps_plan_brief_into_system_hint() -> None:
    processor = _processor(_agent_manager())
    brief = "## Approved plan\n\nWrite load.sh\n\nExecute this plan now."
    msg = InboundMessage(
        channel_id="ws",
        channel_type="dashboard",
        tenant_id="agent-1",
        channel_subject=ChannelSubject(subject_id="1"),
        content=[TextContent(text="按计划执行")],
        metadata={"conversation_mode": "craft", "plan_brief": brief},
    )
    request = await processor._build_dashboard_request(
        msg,
        agent_id="agent-1",
        user_id=1,
        session_key="sk",
        thread_id="thr",
        meta=msg.metadata or {},
    )
    cfg = request.get("configurable") or {}
    assert cfg["conversation_mode"] == "craft"
    assert cfg.get("plan_brief") == brief
    hint = str(cfg.get("conversation_mode_hint") or "")
    assert "Write load.sh" in hint
    assert "Approved plan" in hint
    from octop.infra.gateway.process.message_keys import UI_HIDDEN_KEY

    human = (request.get("messages") or [None])[0]
    assert human is not None
    assert human.additional_kwargs.get(UI_HIDDEN_KEY) is True


@pytest.mark.asyncio
async def test_iter_turn_chunks_does_not_mutate_agent_tools_disabled() -> None:
    """Ask/Plan enforcement is middleware-scoped; processor must not hot-patch tools."""
    mgr = _agent_manager()
    processor = _processor(mgr)

    msg = InboundMessage(
        channel_id="ws",
        channel_type="dashboard",
        tenant_id="agent-1",
        channel_subject=ChannelSubject(subject_id="1"),
        content=[TextContent(text="hi")],
        metadata={"conversation_mode": "ask", "thread_id": "thr-1"},
    )
    chunks = [c async for c in processor.iter_turn_chunks(msg)]
    assert any(c.get("type") == "token" for c in chunks)
    mgr.sync_tools_disabled.assert_not_called()
    mgr.sync_effective_tools_disabled.assert_not_called()
