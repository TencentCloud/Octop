"""tests/unit/gateway/test_stream_project_tools.py"""

from __future__ import annotations

from octop.infra.gateway.process.stream_project import enrich_tool_stream_chunk


def test_enrich_tool_stream_chunk_adds_display_name():
    chunk = {"type": "tool_call_chunk", "name": "read_file", "args": "{"}
    out = enrich_tool_stream_chunk(chunk, "zh")
    assert out["display_name"] == "读取文件"
    assert out["name"] == "read_file"


def test_enrich_tool_stream_chunk_ignores_non_tool():
    chunk = {"type": "token", "content": "hi"}
    assert enrich_tool_stream_chunk(chunk, "zh") is chunk


def test_tool_start_event_carries_localized_hint():
    from octop_gateway.models import MessageEvent

    from octop.i18n import channel_tool_hint_start

    label = "读取文件"
    event = MessageEvent.tool_start(
        label,
        tool_hint_text=channel_tool_hint_start(label, "zh"),
    )
    assert event.metadata["tool_hint_text"] == channel_tool_hint_start(label, "zh")
    assert "正在调用工具" in event.metadata["tool_hint_text"]


async def test_project_stream_does_not_pop_file_changes_and_processor_drains_on_success(
    tmp_path, monkeypatch
) -> None:
    from unittest.mock import AsyncMock, MagicMock

    from octop_gateway.models import ChannelSubject, InboundMessage, TextContent

    from octop.infra.agents.file_checkpoints import load_checkpoints
    from octop.infra.gateway.process.processor import GlobalProcessor
    from octop.infra.gateway.process.stream_project import project_stream
    from octop.infra.gateway.slash.dispatcher import SlashDispatcher
    from octop.infra.history.projection import TurnHistoryTracker

    popped: list[str] = []
    discarded: list[str] = []

    class _FakeAgent:
        def pop_file_changes(self, thread_id: str) -> list[dict[str, object]]:
            popped.append(thread_id)
            return [{"path": "note.md", "before": None, "after": "hello"}]

        def discard_file_changes(self, thread_id: str) -> None:
            discarded.append(thread_id)

    async def _ok_stream(_agent_id: str, _request: dict[str, object]):
        yield {"type": "token", "content": "done"}
        yield {
            "type": "state_update",
            "data": {"messages": [{"role": "assistant", "content": "done", "id": "ai-msg-1"}]},
        }

    agent_manager = MagicMock()
    agent_manager.get_agent.return_value = _FakeAgent()
    agent_manager.get_config.return_value = {}
    agent_manager.get_row.return_value = None
    agent_manager.stream.side_effect = _ok_stream
    agent_manager.merge_turn_mcp_servers.return_value = []
    agent_manager.default_mcp_servers.return_value = []
    agent_manager.default_knowledge_base_ids.return_value = []
    agent_manager.prepare_chat_mcp = AsyncMock(return_value=[])
    agent_manager.providers = MagicMock()
    agent_manager.providers.is_model_ref_usable.return_value = False
    agent_manager.providers.resolve_explicit_default_model.return_value = None
    agent_manager.providers.resolve_model_for_multimodal_turn.side_effect = lambda ref, **_k: ref
    agent_manager.get_thread_model.return_value = None
    agent_manager.resolve_fallback_model_ref.return_value = None

    # 1. project_stream itself must never touch pop_file_changes() directly.
    tracker = TurnHistoryTracker.from_request({"messages": [{"role": "user", "content": "hi"}]})
    events = [
        ev
        async for ev in project_stream(
            agent_manager,
            "agent-1",
            {},
            history_tracker=tracker,
        )
    ]
    assert events
    assert popped == []
    assert discarded == []

    # 2. Full GlobalProcessor IM turn persists checkpoints cleanly via pop_file_changes(thread_id).
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))
    thread_registry = MagicMock()
    thread_registry.get_or_create_by_key = AsyncMock(return_value="thr-ok")
    thread_registry.get_thread.return_value = None
    thread_registry.touch_last_active = MagicMock()
    thread_registry.set_title_if_null = MagicMock()
    agent_repo = MagicMock()
    agent_repo.get.return_value = MagicMock(user_id=1, default_model=None, config_json=None)

    processor = GlobalProcessor(
        agent_manager=agent_manager,
        thread_registry=thread_registry,
        audit_repo=MagicMock(),
        agent_repo=agent_repo,
        user_repo=MagicMock(),
        connector_repo=MagicMock(),
        dispatcher=SlashDispatcher(),
        thread_message_repo=MagicMock(),
    )
    processor.teams.stamp_host_runtime = MagicMock()
    msg = InboundMessage(
        channel_id="qq",
        channel_type="qq",
        tenant_id="agent-1",
        channel_subject=ChannelSubject(subject_id="u1"),
        content=[TextContent(text="write note")],
    )
    out = [ev async for ev in processor(msg)]
    assert out
    assert popped == ["thr-ok"]
    assert discarded == []
    assert load_checkpoints(tmp_path, "agent-1", "thr-ok", "ai-msg-1") == [
        {"path": "note.md", "before": None, "after": "hello"}
    ]


async def test_processor_discards_file_changes_when_project_stream_fails() -> None:
    from unittest.mock import AsyncMock, MagicMock

    from octop_gateway.models import ChannelSubject, InboundMessage, MessageEventType, TextContent

    from octop.infra.gateway.process.processor import GlobalProcessor
    from octop.infra.gateway.slash.dispatcher import SlashDispatcher

    popped: list[str] = []
    discarded: list[str] = []

    class _FakeAgent:
        def pop_file_changes(self, thread_id: str) -> list[dict[str, object]]:
            popped.append(thread_id)
            return []

        def discard_file_changes(self, thread_id: str) -> None:
            discarded.append(thread_id)

    async def _failing_stream(_agent_id: str, _request: dict[str, object]):
        raise RuntimeError("Error code: 400 - image_invalid")
        yield {}

    agent_manager = MagicMock()
    agent_manager.get_agent.return_value = _FakeAgent()
    agent_manager.get_config.return_value = {}
    agent_manager.get_row.return_value = None
    agent_manager.stream.side_effect = _failing_stream
    agent_manager.merge_turn_mcp_servers.return_value = []
    agent_manager.default_mcp_servers.return_value = []
    agent_manager.default_knowledge_base_ids.return_value = []
    agent_manager.prepare_chat_mcp = AsyncMock(return_value=[])
    agent_manager.providers = MagicMock()
    agent_manager.providers.is_model_ref_usable.return_value = False
    agent_manager.providers.resolve_explicit_default_model.return_value = None
    agent_manager.providers.resolve_model_for_multimodal_turn.side_effect = lambda ref, **_k: ref
    agent_manager.get_thread_model.return_value = None
    agent_manager.resolve_fallback_model_ref.return_value = None

    thread_registry = MagicMock()
    thread_registry.get_or_create_by_key = AsyncMock(return_value="thr-fail")
    thread_registry.get_thread.return_value = None
    thread_registry.touch_last_active = MagicMock()
    thread_registry.set_title_if_null = MagicMock()
    agent_repo = MagicMock()
    agent_repo.get.return_value = MagicMock(user_id=1, default_model=None, config_json=None)

    processor = GlobalProcessor(
        agent_manager=agent_manager,
        thread_registry=thread_registry,
        audit_repo=MagicMock(),
        agent_repo=agent_repo,
        user_repo=MagicMock(),
        connector_repo=MagicMock(),
        dispatcher=SlashDispatcher(),
    )
    processor.teams.stamp_host_runtime = MagicMock()
    msg = InboundMessage(
        channel_id="qq",
        channel_type="qq",
        tenant_id="agent-1",
        channel_subject=ChannelSubject(subject_id="u1"),
        content=[TextContent(text="boom")],
    )
    events = [ev async for ev in processor(msg)]
    assert any(ev.type == MessageEventType.ERROR for ev in events)
    assert popped == []
    assert discarded == ["thr-fail"]
