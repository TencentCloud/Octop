"""GlobalProcessor injects default_open connectors on IM turns."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from harness_gateway.models import ChannelSubject, InboundMessage, MessageEvent, TextContent

from octop.infra.errors import ErrorCode, OctopError
from octop.infra.gateway.process.processor import GlobalProcessor
from octop.infra.gateway.slash.dispatcher import SlashDispatcher


@pytest.mark.asyncio
async def test_im_call_merges_default_open_mcp_servers() -> None:
    captured: dict[str, object] = {}

    async def fake_project_stream(_mgr, _aid, request, **_kwargs):
        captured["request"] = request
        yield MagicMock()

    agent_manager = MagicMock()
    agent_manager.merge_turn_mcp_servers = MagicMock(return_value=["docs__1"])
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

    with patch(
        "octop.infra.gateway.process.processor.project_stream",
        new=fake_project_stream,
    ):
        events = [ev async for ev in processor(msg)]

    assert events
    agent_manager.merge_turn_mcp_servers.assert_called_once_with(7, None, apply_defaults=True)
    agent_manager.prepare_chat_mcp.assert_awaited_once()
    assert captured["request"]["mcp_servers"] == ["docs__1"]


@pytest.mark.asyncio
async def test_dashboard_request_trusts_explicit_opt_out() -> None:
    """Dashboard mcp_servers=[] must not re-inject default_open connectors."""
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
        channel_type="dashboard",
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
    agent_manager.merge_turn_mcp_servers.assert_called_once_with(1, [], apply_defaults=False)


@pytest.mark.asyncio
async def test_dashboard_request_attaches_knowledge_base_ids_without_prepending() -> None:
    agent_manager = MagicMock()
    agent_manager.merge_turn_mcp_servers = MagicMock(return_value=None)
    agent_manager.get_row = MagicMock(return_value=None)
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


def _processor_with_gateway(gateway: object) -> tuple[GlobalProcessor, MagicMock]:
    thread_registry = MagicMock()
    thread_registry.touch_last_active = MagicMock()
    thread_registry.set_title_if_null = MagicMock()
    thread_registry.increment_unread = MagicMock()
    processor = GlobalProcessor(
        agent_manager=MagicMock(),
        thread_registry=thread_registry,
        audit_repo=MagicMock(),
        agent_repo=MagicMock(),
        user_repo=MagicMock(),
        connector_repo=MagicMock(),
        dispatcher=SlashDispatcher(),
        usage_repo=None,
        gateway=gateway,
    )
    return processor, thread_registry


@pytest.mark.asyncio
async def test_im_turn_notifies_dashboard_and_mirrors_tokens() -> None:
    hub = MagicMock()
    hub.push_to_thread = AsyncMock()
    hub.push_to_user = AsyncMock()
    processor, thread_registry = _processor_with_gateway(SimpleNamespace(ws_hub=hub))

    await processor._publish_im_turn_to_dashboard(
        channel_type="weixin",
        session_key="a1:weixin:ou:dm",
        thread_id="thr-wx",
        agent_id="a1",
        user_id=7,
        text="hi",
    )
    thread_registry.increment_unread.assert_called_once_with("a1:weixin:ou:dm")
    hub.mark_turn_active.assert_called_once_with("thr-wx")
    hub.push_to_thread.assert_awaited_once_with(
        "thr-wx",
        {"type": "inbound_user", "content": "hi", "thread_id": "thr-wx"},
    )
    hub.push_to_user.assert_awaited_once_with(
        7,
        {
            "type": "thread_activity",
            "agent_id": "a1",
            "thread_id": "thr-wx",
            "channel_type": "weixin",
        },
    )

    thread_registry.increment_unread.reset_mock()
    await processor._publish_im_turn_to_dashboard(
        channel_type="feishu",
        session_key="a1:feishu:ou:dm",
        thread_id="thr-fs",
        agent_id="a1",
        user_id=7,
        text="hi",
    )
    thread_registry.increment_unread.assert_not_called()

    await processor._mirror_im_event_to_dashboard("thr-wx", MessageEvent.delta("你"))
    await processor._mirror_im_event_to_dashboard("thr-wx", MessageEvent.completed())
    frames = [call.args[1] for call in hub.push_to_thread.await_args_list]
    assert {"type": "token", "content": "你", "thread_id": "thr-wx"} in frames
    assert {"type": "done", "thread_id": "thr-wx"} in frames
    hub.mark_turn_idle.assert_called_once_with("thr-wx")


@pytest.mark.asyncio
async def test_dashboard_turn_does_not_publish_im_activity() -> None:
    hub = MagicMock()
    hub.push_to_thread = AsyncMock()
    processor, thread_registry = _processor_with_gateway(SimpleNamespace(ws_hub=hub))

    await processor._publish_im_turn_to_dashboard(
        channel_type="dashboard",
        session_key="a1:dashboard:7:dm",
        thread_id="thr-dash",
        agent_id="a1",
        user_id=7,
        text="from panel",
    )
    thread_registry.increment_unread.assert_not_called()
    hub.push_to_thread.assert_not_awaited()


@pytest.mark.asyncio
async def test_im_publish_failure_does_not_raise() -> None:
    hub = MagicMock()
    hub.push_to_thread = AsyncMock(side_effect=RuntimeError("hub down"))
    hub.push_to_user = AsyncMock()
    processor, thread_registry = _processor_with_gateway(SimpleNamespace(ws_hub=hub))
    thread_registry.increment_unread.side_effect = RuntimeError("db down")

    await processor._publish_im_turn_to_dashboard(
        channel_type="weixin",
        session_key="a1:weixin:ou:dm",
        thread_id="thr-wx",
        agent_id="a1",
        user_id=7,
        text="hi",
    )
    hub.push_to_thread.assert_awaited()
