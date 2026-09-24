"""Conversation-mode stamping on dashboard harness requests."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from harness_gateway.models import ChannelSubject, InboundMessage, TextContent
from langchain_core.messages import HumanMessage

from octop.infra.gateway.process.processor import GlobalProcessor, _overwrite_last_user_text
from octop.infra.gateway.slash.dispatcher import SlashDispatcher


def _processor(*, thread: SimpleNamespace | None) -> GlobalProcessor:
    agent_manager = MagicMock()
    agent_manager.merge_turn_mcp_servers = MagicMock(return_value=None)
    agent_manager.get_row = MagicMock(return_value=None)
    agent_manager.default_mcp_servers = MagicMock(return_value=[])
    agent_manager.default_knowledge_base_ids = MagicMock(return_value=[])
    agent_manager.providers = MagicMock()
    agent_manager.providers.is_model_ref_usable = MagicMock(return_value=False)
    agent_manager.providers.resolve_explicit_default_model = MagicMock(return_value=None)
    agent_manager.providers.resolve_model_for_multimodal_turn = MagicMock(
        side_effect=lambda ref, **_k: ref
    )
    agent_manager.get_thread_model = MagicMock(return_value=None)
    thread_registry = MagicMock()
    thread_registry.get_thread = MagicMock(return_value=thread)
    thread_registry.update_composer = MagicMock()
    return GlobalProcessor(
        agent_manager=agent_manager,
        thread_registry=thread_registry,
        audit_repo=MagicMock(),
        agent_repo=MagicMock(get=MagicMock(return_value=MagicMock(default_model=None))),
        user_repo=MagicMock(
            get=MagicMock(return_value=SimpleNamespace(locale="zh", preferences_json=None))
        ),
        connector_repo=MagicMock(),
        dispatcher=SlashDispatcher(),
        usage_repo=None,
        gateway=None,
    )


def test_overwrite_last_user_text_keeps_human_kwargs() -> None:
    request: dict[str, object] = {
        "messages": [HumanMessage(content="执行", additional_kwargs={"composer": True})],
    }
    _overwrite_last_user_text(request, "请按 plans/foo.md 执行")
    last = request["messages"][0]
    assert isinstance(last, HumanMessage)
    assert last.content == "请按 plans/foo.md 执行"
    assert last.additional_kwargs == {"composer": True}


@pytest.mark.asyncio
async def test_dashboard_execute_overwrites_user_text() -> None:
    processor = _processor(
        thread=SimpleNamespace(
            conversation_mode="plan",
            pending_plan_path="plans/foo.md",
            model_ref=None,
        )
    )
    msg = InboundMessage(
        channel_id="ws",
        channel_type="dashboard",
        tenant_id="agent-1",
        channel_subject=ChannelSubject(subject_id="1"),
        content=[TextContent(text="按计划执行")],
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
    assert request["messages"][0]["content"] == "请按 plans/foo.md 执行"
    assert request["conversation_mode"] == "craft"
    processor._thread_registry.update_composer.assert_called_once_with(
        "thr",
        conversation_mode="craft",
        pending_plan_path=None,
    )


@pytest.mark.asyncio
async def test_dashboard_mode_switch_keeps_pending_plan() -> None:
    processor = _processor(
        thread=SimpleNamespace(
            conversation_mode="plan",
            pending_plan_path="plans/foo.md",
            model_ref=None,
        )
    )
    msg = InboundMessage(
        channel_id="ws",
        channel_type="dashboard",
        tenant_id="agent-1",
        channel_subject=ChannelSubject(subject_id="1"),
        content=[TextContent(text="先问一句")],
        metadata={"conversation_mode": "ask"},
    )
    request = await processor._build_dashboard_request(
        msg,
        agent_id="agent-1",
        user_id=1,
        session_key="sk",
        thread_id="thr",
        meta={"conversation_mode": "ask"},
    )
    assert request["messages"][0]["content"] == "先问一句"
    assert request["conversation_mode"] == "ask"
    processor._thread_registry.update_composer.assert_called_once_with(
        "thr",
        conversation_mode="ask",
    )


@pytest.mark.asyncio
async def test_dashboard_turn_applies_hitl_policy() -> None:
    processor = _processor(
        thread=SimpleNamespace(
            conversation_mode="craft",
            pending_plan_path=None,
            model_ref=None,
        )
    )
    msg = InboundMessage(
        channel_id="ws",
        channel_type="dashboard",
        tenant_id="agent-1",
        channel_subject=ChannelSubject(subject_id="1"),
        content=[TextContent(text="hello")],
        metadata={"hitl_policy": {"mode": "allow_all"}},
    )
    await processor._build_dashboard_request(
        msg,
        agent_id="agent-1",
        user_id=1,
        session_key="sk",
        thread_id="thr",
        meta={"hitl_policy": {"mode": "allow_all"}},
    )
    assert processor.hitl_coordinator.session_policies.get("thr").mode == "allow_all"
