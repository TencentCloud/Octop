"""IM turns resolve reasoning overrides like the Dashboard path (#2785)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from octop_gateway.models import ChannelSubject, InboundMessage, TextContent

from octop.infra.gateway.process.processor import GlobalProcessor
from octop.infra.gateway.slash.dispatcher import SlashDispatcher


def _processor(reasoning_parameters: dict | None) -> GlobalProcessor:
    """A processor whose providers report an OpenAI-effort reasoning capability."""
    agent_manager = MagicMock()
    agent_manager.merge_turn_mcp_servers = MagicMock(return_value=None)
    agent_manager.default_mcp_servers = MagicMock(return_value=[])
    agent_manager.default_knowledge_base_ids = MagicMock(return_value=[])
    agent_manager.prepare_chat_mcp = AsyncMock(return_value=[])
    agent_manager.get_row = MagicMock(return_value=MagicMock(default_model=None))
    agent_manager.providers = MagicMock()
    agent_manager.providers.is_model_ref_usable = MagicMock(return_value=False)
    agent_manager.providers.resolve_explicit_default_model = MagicMock(return_value=None)
    agent_manager.providers.resolve_model_for_multimodal_turn = MagicMock(
        side_effect=lambda ref, **_k: ref
    )
    agent_manager.providers.get_model_reasoning_capability = MagicMock(
        return_value={"adapter": "openai_reasoning_effort"}
        if reasoning_parameters is not None
        else None
    )
    agent_manager.get_thread_model = MagicMock(return_value=None)
    agent_manager.resolve_fallback_model_ref = MagicMock(return_value="prov/m-1")

    agent_repo = MagicMock()
    agent_repo.get = MagicMock(return_value=MagicMock(user_id=7, default_model=None))

    thread_registry = MagicMock()
    thread_registry.get_or_create_by_key = AsyncMock(return_value="thr-im")
    thread_registry.touch_last_active = MagicMock()
    thread_registry.set_title_if_null = MagicMock()
    thread_registry.get_thread = MagicMock(return_value=None)

    return GlobalProcessor(
        agent_manager=agent_manager,
        thread_registry=thread_registry,
        audit_repo=MagicMock(),
        agent_repo=agent_repo,
        user_repo=MagicMock(),
        connector_repo=MagicMock(),
        dispatcher=SlashDispatcher(),
        usage_repo=None,
        gateway=None,
    )


def _im_message() -> InboundMessage:
    return InboundMessage(
        channel_id="feishu",
        channel_type="feishu",
        tenant_id="agent-1",
        channel_subject=ChannelSubject(subject_id="u1"),
        content=[TextContent(text="hello")],
    )


@pytest.mark.asyncio
async def test_im_request_carries_reasoning_overrides() -> None:
    captured: dict[str, object] = {}
    overrides = {"model_fields": {"reasoning_effort": "high"}}

    async def fake_project_stream(_mgr, _aid, request, **_kwargs):
        captured["request"] = request
        yield MagicMock()

    processor = _processor(overrides)

    with (
        patch(
            "octop.infra.gateway.process.processor.project_stream",
            new=fake_project_stream,
        ),
        patch(
            "octop.infra.gateway.process.processor.reasoning_request_parameters",
            return_value=overrides,
        ),
    ):
        events = [ev async for ev in processor(_im_message())]

    assert events
    assert captured["request"]["configurable"]["octop_reasoning_overrides"] == overrides


@pytest.mark.asyncio
async def test_im_request_without_reasoning_capability_has_no_overrides() -> None:
    captured: dict[str, object] = {}

    async def fake_project_stream(_mgr, _aid, request, **_kwargs):
        captured["request"] = request
        yield MagicMock()

    processor = _processor(None)

    with patch(
        "octop.infra.gateway.process.processor.project_stream",
        new=fake_project_stream,
    ):
        events = [ev async for ev in processor(_im_message())]

    assert events
    assert not captured["request"].get("reasoning_overrides")
