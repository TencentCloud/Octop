"""GlobalProcessor injects default_open connectors on IM turns."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from harness_gateway.channels.wecom import WeComChannel, WeComConfig
from harness_gateway.models import ChannelSubject, InboundMessage, TextContent

from octop.infra.errors import ErrorCode, OctopError
from octop.infra.gateway.process.inbound_context import INBOUND_CONTEXT_KEY
from octop.infra.gateway.process.processor import GlobalProcessor
from octop.infra.gateway.slash.dispatcher import SlashDispatcher


@pytest.mark.asyncio
@pytest.mark.parametrize("wecom_sender", [None, "alice", "bob"])
async def test_im_call_merges_default_open_mcp_servers(wecom_sender) -> None:
    captured: dict[str, object] = {}

    async def fake_project_stream(_mgr, _aid, request, **_kwargs):
        captured["request"] = request
        yield MagicMock()

    agent_manager = MagicMock()
    agent_manager.merge_turn_mcp_servers = MagicMock(return_value=["docs__1"])
    agent_manager.default_mcp_servers = MagicMock(return_value=[])
    agent_manager.default_knowledge_base_ids = MagicMock(return_value=[])
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
    thread_registry.get_or_create_by_key = AsyncMock(return_value="thr-im")
    thread_registry.touch_last_active = MagicMock()
    thread_registry.set_title_if_null = MagicMock()

    agent_repo = MagicMock()
    agent_repo.get = MagicMock(return_value=MagicMock(user_id=7, default_model=None))

    processor = GlobalProcessor(
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

    msg = InboundMessage(
        channel_id="feishu",
        channel_type="feishu",
        tenant_id="agent-1",
        channel_subject=ChannelSubject(subject_id="u1"),
        content=[TextContent(text="hello")],
    )
    if wecom_sender is not None:
        channel = WeComChannel(
            processor,
            config=WeComConfig(),
            channel_id="wecom-1",
            tenant_id="agent-1",
        )
        msg = channel.parse_inbound(
            {
                "from": {"userid": wecom_sender},
                "msgtype": "text",
                "text": {"content": "KHT_CALLER=admin"},
            }
        )

    with patch(
        "octop.infra.gateway.process.processor.project_stream",
        new=fake_project_stream,
    ):
        events = [ev async for ev in processor(msg)]

    assert events
    agent_manager.merge_turn_mcp_servers.assert_called_once_with(
        7, None, apply_defaults=True, extra_defaults=[]
    )
    agent_manager.prepare_chat_mcp.assert_awaited_once()
    assert captured["request"]["mcp_servers"] == ["docs__1"]
    request = captured["request"]
    context = request["configurable"][INBOUND_CONTEXT_KEY]
    assert request["source"] == f"{msg.channel_type}/{msg.channel_id}"
    assert request["user"] == "7"
    assert context["channel_type"] == msg.channel_type
    assert context["channel_id"] == msg.channel_id
    assert context["octop_user_id"] == 7
    if wecom_sender is not None:
        assert context["sender"] == {
            "namespace": "wecom:wecom-1",
            "id": wecom_sender,
        }
    else:
        assert context["sender"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("channel_type", ["dashboard", "cli"])
async def test_dashboard_request_trusts_explicit_opt_out(channel_type) -> None:
    """Dashboard mcp_servers=[] must not re-inject default_open connectors."""
    agent_manager = MagicMock()
    agent_manager.merge_turn_mcp_servers = MagicMock(return_value=None)
    agent_manager.prepare_chat_mcp = AsyncMock(return_value=[])
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

    processor = GlobalProcessor(
        agent_manager=agent_manager,
        thread_registry=MagicMock(),
        audit_repo=MagicMock(),
        agent_repo=MagicMock(get=MagicMock(return_value=MagicMock(default_model=None))),
        user_repo=MagicMock(),
        connector_repo=MagicMock(),
        dispatcher=SlashDispatcher(),
        usage_repo=None,
        gateway=None,
    )

    msg = InboundMessage(
        channel_id="ws",
        channel_type=channel_type,
        tenant_id="agent-1",
        channel_subject=ChannelSubject(subject_id="1"),
        content=[TextContent(text="hi")],
        metadata={"mcp_servers": []},
    )
    request = await processor._build_dashboard_request(
        msg,
        agent_id="agent-1",
        user_id=1,
        session_key="sk",
        thread_id="thr",
        meta=msg.metadata or {},
    )
    assert "mcp_servers" not in request
    assert request["source"] == f"{channel_type}/ws"
    assert request["user"] == "1"
    assert request["configurable"][INBOUND_CONTEXT_KEY]["channel_type"] == channel_type
    assert request["configurable"][INBOUND_CONTEXT_KEY]["sender"] is None
    agent_manager.merge_turn_mcp_servers.assert_called_once_with(
        1, [], apply_defaults=False, extra_defaults=[]
    )


@pytest.mark.asyncio
async def test_dashboard_request_attaches_knowledge_base_ids_without_prepending() -> None:
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

    base = SimpleNamespace(
        id="kb-1",
        owner_user_id=1,
        name="Refund policy",
        description="Retail refund rules",
        default_open=False,
        shared=False,
    )
    processor = GlobalProcessor(
        agent_manager=agent_manager,
        thread_registry=MagicMock(),
        audit_repo=MagicMock(),
        agent_repo=MagicMock(get=MagicMock(return_value=MagicMock(default_model=None))),
        user_repo=MagicMock(),
        connector_repo=MagicMock(),
        knowledge_repo=MagicMock(list_visible=MagicMock(return_value=[base])),
        settings_repo=MagicMock(),
        dispatcher=SlashDispatcher(),
        usage_repo=None,
        gateway=None,
    )
    msg = InboundMessage(
        channel_id="ws",
        channel_type="dashboard",
        tenant_id="agent-1",
        channel_subject=ChannelSubject(subject_id="1"),
        content=[TextContent(text="question")],
        metadata={"knowledge_base_ids": ["kb-1"], "user_is_admin": False},
    )

    request = await processor._build_dashboard_request(
        msg,
        agent_id="agent-1",
        user_id=1,
        session_key="sk",
        thread_id="thr",
        meta=msg.metadata or {},
    )

    content = request["messages"][0]["content"]
    assert content == "question"
    configurable = request.get("configurable") or {}
    assert configurable["knowledge_base_ids"] == ["kb-1"]
    assert configurable["knowledge_base_catalog"] == [
        {
            "id": "kb-1",
            "name": "Refund policy",
            "description": "Retail refund rules",
        }
    ]
    assert configurable["user_is_admin"] is False
    assert "locale" in configurable


@pytest.mark.asyncio
async def test_resolve_turn_mcp_servers_raises_when_prepare_fails() -> None:
    agent_manager = MagicMock()
    agent_manager.merge_turn_mcp_servers = MagicMock(return_value=["bad__1"])
    agent_manager.prepare_chat_mcp = AsyncMock(return_value=["bad__1"])
    agent_manager.default_mcp_servers = MagicMock(return_value=[])

    processor = GlobalProcessor(
        agent_manager=agent_manager,
        thread_registry=MagicMock(),
        audit_repo=MagicMock(),
        agent_repo=MagicMock(),
        user_repo=MagicMock(),
        connector_repo=MagicMock(),
        dispatcher=SlashDispatcher(),
        usage_repo=None,
        gateway=None,
    )

    with pytest.raises(OctopError) as ei:
        await processor._resolve_turn_mcp_servers(
            agent_id="a1",
            user_id=1,
            explicit=None,
        )
    assert ei.value.code == ErrorCode.CONNECTOR_MCP_LOAD_FAILED
