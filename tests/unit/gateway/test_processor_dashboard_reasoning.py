"""Dashboard turns apply the same reasoning roundtrip contract as IM turns."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from octop_gateway.models import ChannelSubject, InboundMessage, TextContent

from octop.infra.gateway.process.processor import GlobalProcessor
from octop.infra.gateway.slash.dispatcher import SlashDispatcher


def _processor(reasoning_parameters: dict | None) -> GlobalProcessor:
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

    thread_registry = MagicMock()
    thread_registry.get_thread = MagicMock(return_value=None)
    thread_registry.update_composer = MagicMock()

    return GlobalProcessor(
        agent_manager=agent_manager,
        thread_registry=thread_registry,
        audit_repo=MagicMock(),
        agent_repo=MagicMock(get=MagicMock(return_value=MagicMock(default_model=None))),
        user_repo=MagicMock(),
        connector_repo=MagicMock(),
        dispatcher=SlashDispatcher(),
        usage_repo=None,
        gateway=None,
    )


def _dashboard_message() -> InboundMessage:
    return InboundMessage(
        channel_id="ws",
        channel_type="dashboard",
        tenant_id="agent-1",
        channel_subject=ChannelSubject(subject_id="1"),
        content=[TextContent(text="hello")],
        metadata={},
    )


async def _built_request(processor: GlobalProcessor) -> dict:
    return await processor._build_dashboard_request(
        _dashboard_message(),
        agent_id="agent-1",
        user_id=1,
        session_key="sk",
        thread_id="thr",
        meta={},
    )


@pytest.mark.asyncio
async def test_dashboard_request_carries_reasoning_overrides() -> None:
    overrides = {"model_fields": {"reasoning_effort": "high"}}
    processor = _processor(overrides)

    with patch(
        "octop.infra.gateway.process.processor.reasoning_request_parameters",
        return_value=overrides,
    ):
        request = await _built_request(processor)

    configurable = request["configurable"]
    assert configurable["octop_reasoning_overrides"] == overrides
    assert configurable["octop_reasoning_roundtrip"] is True
    # 内部传递字段不能跟着 resolver 输出进入请求配置。
    assert "_roundtrip" not in configurable["octop_reasoning_overrides"]


@pytest.mark.asyncio
async def test_dashboard_request_without_capability_gates_roundtrip_off() -> None:
    processor = _processor(None)

    request = await _built_request(processor)

    configurable = request["configurable"]
    assert configurable["octop_reasoning_roundtrip"] is False
    assert "octop_reasoning_overrides" not in configurable


@pytest.mark.asyncio
async def test_dashboard_request_without_model_ref_omits_gate() -> None:
    processor = _processor({"model_fields": {"reasoning_effort": "high"}})
    processor._agent_manager.resolve_fallback_model_ref = MagicMock(return_value="")

    request = await _built_request(processor)

    configurable = request.get("configurable", {})
    assert "octop_reasoning_roundtrip" not in configurable
    assert "octop_reasoning_overrides" not in configurable
