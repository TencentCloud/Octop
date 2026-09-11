from __future__ import annotations

import json

import pytest
from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    ToolMessage,
    message_to_dict,
    messages_from_dict,
)

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.agents import AgentRepo
from octop.infra.db.repos.thread_messages import ThreadMessageRepo
from octop.infra.db.repos.threads import ThreadRepo
from octop.infra.db.repos.trajectory_events import TrajectoryEventRepo
from octop.infra.db.repos.users import UserRepo
from octop.infra.gateway.process.history_projection import message_inputs
from octop.infra.history.recorder import RecordingTracker
from octop.infra.history.service import HistoryArchive
from octop.infra.history.store import HistoryStore
from octop.infra.history.trajectory import ArchiveTrajectoryStore
from octop.infra.trajectory.live import TrajectoryLiveBus
from octop.infra.trajectory.service import TrajectoryService


@pytest.fixture
def archive(tmp_path):
    db = SqlitePool(tmp_path / "legacy.sqlite")
    run_migrations(db)
    uid = UserRepo(db).create(username="test", password_hash="x", role="user")
    AgentRepo(db).create(agent_id="a", user_id=uid, name="A")
    ThreadRepo(db).insert(
        thread_id="t",
        agent_id="a",
        user_id=uid,
        channel_type="dashboard",
        session_key="s",
        last_active=0,
    )
    store = HistoryStore(tmp_path / "history.sqlite", identity="test")
    value = HistoryArchive(store, ThreadMessageRepo(db), TrajectoryEventRepo(db), enabled=True)
    yield value
    store.close()
    db.close()


async def no_anchor(_anchor):
    raise AssertionError("Unexpected legacy checkpoint read")


@pytest.mark.asyncio
async def test_no_migration_single_write_and_cross_boundary_cursor(archive):
    old = [HumanMessage(content="old question", id="u0"), AIMessage(content="old answer", id="a0")]
    archive.messages.append_if_ready("t", message_inputs(old))
    before = archive.messages.range_rows("t", 0, 100)
    turn = archive.begin("a", "t")
    recorder = RecordingTracker(
        archive, turn, [{"role": "user", "content": "new question", "id": "u1"}]
    )
    recorder.observe({"type": "reasoning", "content": "visible thought"})
    recorder.observe({"type": "token", "content": "new answer"})
    await recorder.finish(completed=True)
    assert archive.messages.range_rows("t", 0, 100) == before
    page = await archive.page("t", limit=3, cursor=None, legacy_reader=no_anchor)
    assert [m.content for m in messages_from_dict(page["messages"])] == [
        "old answer",
        "new question",
        "new answer",
    ]
    first_cursor = page["next_cursor"]
    turn2 = archive.begin("a", "t")
    r2 = RecordingTracker(archive, turn2, [{"role": "user", "content": "more", "id": "u2"}])
    r2.observe({"type": "token", "content": "more answer"})
    await r2.finish(completed=True)
    older = await archive.page("t", limit=3, cursor=first_cursor, legacy_reader=no_anchor)
    assert [m.content for m in messages_from_dict(older["messages"])] == ["old question"]
    assert not older["has_more"]


@pytest.mark.asyncio
async def test_state_metadata_thinking_tools_and_shared_trajectory_bodies(archive):
    text = "A final answer with sufficient distinct content"
    turn = archive.begin("a", "t")
    tracker = RecordingTracker(archive, turn, [{"role": "user", "content": "question", "id": "u"}])
    tracker.observe({"type": "reasoning", "content": "visible thought"})
    tracker.observe(
        {"type": "tool_call_chunk", "id": "call", "name": "lookup", "args": '{"q":"weather"}'}
    )
    tracker.observe({"type": "tool_result", "id": "call", "name": "lookup", "content": "rain"})
    tracker.observe({"type": "token", "content": text})
    final = [
        HumanMessage(content="question", id="u"),
        AIMessage(
            content="",
            id="a1",
            tool_calls=[{"id": "call", "name": "lookup", "args": {"q": "weather"}}],
        ),
        ToolMessage(content="rain", tool_call_id="call", id="tool"),
        AIMessage(content=text, id="a2", response_metadata={"model_name": "test"}),
    ]
    tracker.observe({"type": "state_snapshot", "data": {"messages": final}})
    await tracker.finish(completed=True)
    service = TrajectoryService(ArchiveTrajectoryStore(archive), TrajectoryLiveBus())
    service.observe_chunk("a", "t", {"type": "user", "content": "question"})
    service.observe_chunk("a", "t", {"type": "token", "content": text})
    service.finish_turn("t")
    wires = [d["value"] for d in archive.store.documents("t", "message")]
    recovered = messages_from_dict(wires)
    assert recovered[1].additional_kwargs["reasoning_content"] == "visible thought"
    assert recovered[1].tool_calls[0]["args"] == {"q": "weather"}
    assert recovered[2].content == "rain"
    assert recovered[3].response_metadata == {"model_name": "test"}
    assert not archive.events.list_before("t", before_seq=None, limit=10, kinds=None)
    with archive.store.db.connect() as conn:
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM bodies WHERE value=?", (json.dumps(text),)
            ).fetchone()[0]
            == 1
        )
    exported = list(service.export_jsonl("t"))
    assert text in exported[-1]


@pytest.mark.asyncio
async def test_rollback_adds_legacy_interval_without_losing_v2(archive):
    turn = archive.begin("a", "t")
    tracker = RecordingTracker(archive, turn, [{"role": "user", "content": "v2"}])
    tracker.observe({"type": "token", "content": "answer v2"})
    await tracker.finish(completed=True)
    archive.enabled = False
    legacy = archive.begin("a", "t")
    assert legacy["format"] == "legacy"
    archive.messages.append_legacy_interval(
        "t", message_inputs([HumanMessage(content="rollback", id="r")])
    )
    archive.finish(legacy["id"], "complete")
    archive.enabled = True
    next_turn = archive.begin("a", "t")
    recorder = RecordingTracker(archive, next_turn, [{"role": "user", "content": "v2 again"}])
    await recorder.finish(completed=False)
    result = await archive.page("t", limit=20, cursor=None, legacy_reader=no_anchor)
    assert [m.content for m in messages_from_dict(result["messages"])] == [
        "v2",
        "answer v2",
        "rollback",
        "v2 again",
    ]


@pytest.mark.asyncio
async def test_paused_turn_resumes_original_format_after_switch_disabled(archive):
    turn = archive.begin("a", "t")
    tracker = RecordingTracker(archive, turn, [{"role": "user", "content": "question"}])
    tracker.observe({"type": "reasoning", "content": "partial thought"})
    tracker.observe({"type": "hitl_required", "request": {}})
    await tracker.finish(completed=False)
    archive.enabled = False
    with pytest.raises(ValueError, match="paused"):
        archive.begin("a", "t")
    resumed = archive.begin("a", "t", resume=True)
    assert resumed["id"] == turn["id"] and resumed["format"] == "v2"
    reader = RecordingTracker(archive, resumed, [])
    reader.observe({"type": "token", "content": "resumed"})
    await reader.finish(completed=True)
    docs = archive.store.documents("t", "message")
    assert any("partial thought" in json.dumps(d["value"]) for d in docs)


def test_archive_identity_mismatch_is_rejected(archive):
    with pytest.raises(ValueError, match="identity"):
        HistoryStore(archive.store.path, identity="different")


def test_missing_archive_is_not_empty_history(tmp_path):
    path = tmp_path / "history.sqlite"
    store = HistoryStore(path, identity="test")
    store.close()
    path.rename(tmp_path / "moved.sqlite")

    with pytest.raises(FileNotFoundError):
        store.segments("t")
    with pytest.raises(FileNotFoundError, match="required history archive"):
        HistoryStore(path, identity="test")


def test_failed_document_write_rolls_back_bodies(archive):
    turn = archive.begin("a", "t")
    with pytest.raises(RuntimeError), archive.store.transaction() as conn:
        archive.store.put_document(
            conn,
            doc_id="x",
            thread_id="t",
            turn_id=turn["id"],
            kind="message",
            seq=1,
            value=message_to_dict(HumanMessage(content="atomic")),
        )
        raise RuntimeError("simulated crash before commit")
    assert not archive.store.documents("t", "message")
    with archive.store.db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM bodies").fetchone()[0] == 0


def test_two_writers_cannot_start_the_same_thread(archive):
    from concurrent.futures import ThreadPoolExecutor

    def start():
        try:
            return archive.begin("a", "t")
        except ValueError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: start(), range(2)))
    assert sum(result is not None for result in results) == 1


@pytest.mark.asyncio
async def test_restart_keeps_committed_partial_content(archive):
    turn = archive.begin("a", "t")
    recorder = RecordingTracker(archive, turn, [{"role": "user", "content": "question"}])
    recorder.observe({"type": "reasoning", "content": "saved before crash"})
    await recorder.flush()
    restarted = HistoryArchive(archive.store, archive.messages, archive.events, enabled=True)
    next_turn = restarted.begin("a", "t")
    assert next_turn["id"] != turn["id"]
    docs = archive.store.documents("t", "message", turn_id=turn["id"])
    assert docs[-1]["status"] == "interrupted"
    assert (
        docs[-1]["value"]["data"]["additional_kwargs"]["reasoning_content"] == "saved before crash"
    )


@pytest.mark.asyncio
async def test_unanswered_tool_is_not_marked_complete(archive):
    turn = archive.begin("a", "t")
    tracker = RecordingTracker(archive, turn, [{"role": "user", "content": "question"}])
    tracker.observe({"type": "tool_call_chunk", "id": "missing", "name": "lookup", "args": {}})
    await tracker.finish(completed=True)
    assert archive.store.turn("t")["status"] == "partial"


@pytest.mark.asyncio
async def test_pinned_legacy_anchor_and_new_rows_are_not_copied(archive):
    archive.messages.mark_projection("t", "pending")
    anchor = {
        "checkpoint_config": {"configurable": {"thread_id": "t", "checkpoint_id": "old-head"}}
    }
    turn = archive.begin("a", "t", anchor=anchor)
    tracker = RecordingTracker(archive, turn, [{"role": "user", "content": "new"}])
    await tracker.finish(completed=False)

    async def load(received):
        assert received == anchor
        return [message_to_dict(HumanMessage(content="old pinned message", id="old"))]

    page = await archive.page("t", limit=10, cursor=None, legacy_reader=load)
    assert [m.content for m in messages_from_dict(page["messages"])] == [
        "old pinned message",
        "new",
    ]
    assert archive.messages.projection_status("t") == "pending"
    assert archive.messages.head("t") == 0
    assert len(archive.store.documents("t", "message")) == 1


def test_backup_includes_archive_and_restore_refuses_partial_overwrite(archive, tmp_path):
    import tarfile

    from octop.config import DatabaseConfig
    from octop.infra.backup.system_archive import create_system_backup, restore_system_backup
    from octop.infra.errors import OctopError
    from octop.infra.utils.paths import PathLayout

    archive.begin("a", "t")
    paths = PathLayout(tmp_path)
    # The fixture uses a different basename; snapshot it into the configured archive location.
    from octop.infra.backup.snapshot import snapshot_sqlite_file

    snapshot_sqlite_file(archive.store.path, tmp_path / "history_v2.sqlite")
    (tmp_path / "history_v2.required").write_text("required", encoding="utf-8")
    dest = tmp_path / "backup.tar.gz"
    db = archive.messages._db
    create_system_backup(
        paths=paths,
        agent_rows=[],
        pool=db,
        db_config=DatabaseConfig(),
        dest=dest,
        include_workspaces=False,
        include_chats=True,
    )
    with tarfile.open(dest) as tf:
        assert "history/history_v2.sqlite" in tf.getnames()
        assert "history/history_v2.required" in tf.getnames()
    old_rows = archive.messages.range_rows("t", 0, 100)
    with pytest.raises(OctopError, match="offline restore"):
        restore_system_backup(dest, paths=paths, pool=db, db_config=DatabaseConfig())
    assert archive.messages.range_rows("t", 0, 100) == old_rows


@pytest.mark.asyncio
async def test_interleaved_identified_reasoning_survives_state_replay(archive):
    tracker = RecordingTracker(
        archive, archive.begin("a", "t"), [HumanMessage(content="go", id="u")]
    )
    tracker.observe(
        {
            "type": "reasoning",
            "message_id": "one",
            "checkpoint_ns": "root",
            "content": "root thought",
        }
    )
    tracker.observe(
        {
            "type": "reasoning",
            "message_id": "two",
            "checkpoint_ns": "child",
            "content": "child thought",
        }
    )
    tracker.observe(
        {"type": "token", "message_id": "one", "checkpoint_ns": "root", "content": "root answer"}
    )
    tracker.observe(
        {"type": "token", "message_id": "two", "checkpoint_ns": "child", "content": "child answer"}
    )
    tracker.observe(
        {"type": "state_update", "data": {"messages": [AIMessage(content="root answer", id="one")]}}
    )
    await tracker.flush()
    tracker.observe(
        {"type": "state_update", "data": {"messages": [AIMessage(content="root answer", id="one")]}}
    )
    await tracker.finish(completed=True)
    result = await archive.page("t", limit=20, cursor=None, legacy_reader=no_anchor)
    messages = {w["data"]["id"]: w["data"] for w in result["messages"]}
    assert len(messages) == 3
    assert messages["one"]["content"] == "root answer"
    assert messages["two"]["content"] == "child answer"
    assert messages["one"]["additional_kwargs"]["reasoning_content"] == "root thought"
    assert messages["two"]["additional_kwargs"]["reasoning_content"] == "child thought"


@pytest.mark.asyncio
async def test_trajectory_write_failure_prevents_complete_archive_status(archive, monkeypatch):
    tracker = RecordingTracker(
        archive, archive.begin("a", "t"), [HumanMessage(content="go", id="u")]
    )
    store = ArchiveTrajectoryStore(archive)
    service = TrajectoryService(store, TrajectoryLiveBus())

    def fail(_event):
        raise OSError("disk full")

    monkeypatch.setattr(store, "append", fail)
    service.observe_chunk("a", "t", {"type": "user", "content": "go"})
    tracker.observe({"type": "token", "content": "answer"})
    await tracker.finish(completed=True)
    assert archive.store.turn("t")["status"] == "partial"


@pytest.mark.asyncio
async def test_unsegmented_legacy_export_does_not_backfill(archive):
    from unittest.mock import MagicMock

    from octop.infra.history.reader import export_messages

    archive.messages.append_if_ready("t", message_inputs([HumanMessage(content="old", id="old")]))
    messages = await export_messages(archive, MagicMock(), "a", "t")
    assert messages_from_dict(messages)[0].content == "old"
    assert not archive.store.segments("t")
    assert not archive.store.documents("t", "message")


@pytest.mark.asyncio
async def test_revised_state_message_keeps_latest_tool_metadata(archive):
    tracker = RecordingTracker(
        archive, archive.begin("a", "t"), [HumanMessage(content="go", id="u")]
    )
    tracker.observe({"type": "reasoning", "message_id": "a", "content": "thought"})
    for message in [
        AIMessage(content="draft", id="a"),
        AIMessage(content="final", id="a", response_metadata={"model_name": "test"}),
    ]:
        tracker.observe({"type": "state_update", "data": {"messages": [message]}})
    await tracker.finish(completed=True)
    wires = (await archive.page("t", limit=20, cursor=None, legacy_reader=no_anchor))["messages"]
    answer = messages_from_dict(wires)[-1]
    assert answer.content == "final"
    assert answer.response_metadata["model_name"] == "test"
    assert answer.additional_kwargs["reasoning_content"] == "thought"


@pytest.mark.asyncio
async def test_dashboard_processor_writes_only_new_archive(archive):
    from unittest.mock import AsyncMock, MagicMock

    from harness_gateway.models import ChannelSubject, InboundMessage, TextContent

    from octop.infra.gateway.process.processor import GlobalProcessor
    from octop.infra.gateway.slash.dispatcher import SlashDispatcher
    from octop.infra.gateway.ws import WS_CHANNEL_ID

    async def stream(*_args, **_kwargs):
        yield {"type": "reasoning", "message_id": "answer", "content": "thought"}
        yield {"type": "token", "message_id": "answer", "content": "answer"}

    manager = MagicMock()
    manager.stream = stream
    manager.merge_turn_mcp_servers.return_value = None
    manager.prepare_chat_mcp = AsyncMock(return_value=[])
    service = TrajectoryService(ArchiveTrajectoryStore(archive), TrajectoryLiveBus())
    processor = GlobalProcessor(
        agent_manager=manager,
        thread_registry=MagicMock(),
        audit_repo=MagicMock(),
        agent_repo=MagicMock(),
        user_repo=MagicMock(),
        connector_repo=MagicMock(),
        dispatcher=SlashDispatcher(),
        trajectory_service=service,
        thread_message_repo=archive.messages,
        history_archive=archive,
    )
    msg = InboundMessage(
        channel_id=WS_CHANNEL_ID,
        channel_type="dashboard",
        tenant_id="a",
        channel_subject=ChannelSubject(subject_id="1"),
        content=[TextContent(text="question")],
        metadata={"session_key": "s", "thread_id": "t"},
    )
    output = [event async for event in processor.iter_turn_chunks(msg)]
    assert output[-1]["type"] == "done"
    assert not archive.messages.range_rows("t", 0, 100)
    assert not archive.events.list_before("t", before_seq=None, limit=100, kinds=None)
    history = (await archive.page("t", limit=20, cursor=None, legacy_reader=no_anchor))["messages"]
    assert messages_from_dict(history)[-1].additional_kwargs["reasoning_content"] == "thought"
    assert archive.store.turn("t")["status"] == "complete"


def test_rebind_is_rejected_before_closing_old_database(archive, monkeypatch):
    from unittest.mock import MagicMock

    from octop.infra.db.rebind import rebind_control_plane
    from octop.infra.errors import OctopError

    server = MagicMock()
    server.user_manager.count.return_value = 0
    server.app_runtime.history_archive = archive
    open_database = MagicMock()
    monkeypatch.setattr("octop.infra.db.rebind.open_database", open_database)
    with pytest.raises(OctopError, match="Restart"):
        rebind_control_plane(server)
    open_database.assert_not_called()
    server.services.db.close.assert_not_called()


@pytest.mark.asyncio
async def test_cursor_issued_before_first_switch_survives_new_turns(archive):
    from unittest.mock import MagicMock

    from octop.infra.history.reader import read_page

    archive.messages.append_if_ready(
        "t",
        message_inputs(
            [
                HumanMessage(content="oldest", id="u0"),
                AIMessage(content="old answer", id="a0"),
                HumanMessage(content="newer", id="u1"),
                AIMessage(content="newer answer", id="a1"),
            ]
        ),
    )
    registry = MagicMock()
    first = await read_page(archive, registry, "a", "t", limit=2)
    assert first["next_cursor"].startswith("legacy:")
    tracker = RecordingTracker(
        archive, archive.begin("a", "t"), [HumanMessage(content="new v2", id="u2")]
    )
    tracker.observe({"type": "token", "content": "v2 answer"})
    await tracker.finish(completed=True)
    older = await read_page(archive, registry, "a", "t", limit=2, cursor=first["next_cursor"])
    assert [m.content for m in messages_from_dict(older["messages"])] == ["oldest", "old answer"]
    assert not older["has_more"]


@pytest.mark.asyncio
async def test_checkpoint_cursor_pins_old_snapshot_without_copying(archive):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, MagicMock

    from octop.infra.history.reader import read_page

    archive.messages.mark_projection("t", "pending")
    old = [
        HumanMessage(content="oldest", id="u0"),
        AIMessage(content="old", id="a0"),
        HumanMessage(content="newer", id="u1"),
        AIMessage(content="new", id="a1"),
    ]
    state = SimpleNamespace(
        values={"messages": old},
        config={"configurable": {"thread_id": "t", "checkpoint_id": "old"}},
    )
    graph = SimpleNamespace(aget_state=AsyncMock(return_value=state))
    registry = MagicMock()
    registry.get_agent.return_value = SimpleNamespace(graph=graph)
    first = await read_page(archive, registry, "a", "t", limit=2)
    tracker = RecordingTracker(
        archive, archive.begin("a", "t", anchor={"checkpoint_config": state.config}), []
    )
    tracker.observe({"type": "token", "content": "new turn"})
    await tracker.finish(completed=True)
    older = await read_page(archive, registry, "a", "t", limit=2, cursor=first["next_cursor"])
    assert [w["data"]["content"] for w in older["messages"]] == ["oldest", "old"]
    assert graph.aget_state.call_args.args[0]["configurable"] == {
        "thread_id": "t",
        "checkpoint_id": "old",
        "checkpoint_ns": "",
    }
    assert not archive.messages.range_rows("t", 0, 100)
    assert archive.messages.projection_status("t") == "pending"


@pytest.mark.asyncio
async def test_inline_thinking_is_not_duplicated_after_final_state(archive):
    from octop.api.routers.chat.serialize import _serialize_history_message

    tracker = RecordingTracker(archive, archive.begin("a", "t"), [])
    tracker.observe({"type": "reasoning", "message_id": "a", "content": "thought"})
    tracker.observe({"type": "token", "message_id": "a", "content": "answer"})
    tracker.observe(
        {
            "type": "state_update",
            "data": {"messages": [AIMessage(content="<think>thought</think>answer", id="a")]},
        }
    )
    await tracker.finish(completed=True)
    message = messages_from_dict(tracker.wires())[0]
    assert not message.additional_kwargs.get("reasoning_content")
    rendered = _serialize_history_message(message)
    assert rendered is not None
    assert str(rendered).count("thought") == 1


def _committed_messages(archive):
    """Read through another connection; uncommitted writer state is not visible."""
    import sqlite3

    with sqlite3.connect(archive.store.path) as connection:
        rows = connection.execute(
            "SELECT data FROM documents WHERE thread_id='t' AND kind='message' ORDER BY seq"
        ).fetchall()
        return [archive.store._decode(connection, json.loads(row[0])) for row in rows]


def _dashboard_with_chunks(archive, chunks):
    from unittest.mock import AsyncMock, MagicMock

    from harness_gateway.models import ChannelSubject, InboundMessage, TextContent

    from octop.infra.gateway.process.processor import GlobalProcessor
    from octop.infra.gateway.slash.dispatcher import SlashDispatcher
    from octop.infra.gateway.ws import WS_CHANNEL_ID

    async def stream(*_args, **_kwargs):
        for chunk in chunks:
            yield chunk

    manager = MagicMock()
    manager.stream = stream
    manager.merge_turn_mcp_servers.return_value = None
    manager.prepare_chat_mcp = AsyncMock(return_value=[])
    processor = GlobalProcessor(
        agent_manager=manager,
        thread_registry=MagicMock(),
        audit_repo=MagicMock(),
        agent_repo=MagicMock(),
        user_repo=MagicMock(),
        connector_repo=MagicMock(),
        dispatcher=SlashDispatcher(),
        thread_message_repo=archive.messages,
        history_archive=archive,
    )
    processor._record_stream_error = AsyncMock()
    msg = InboundMessage(
        channel_id=WS_CHANNEL_ID,
        channel_type="dashboard",
        tenant_id="a",
        channel_subject=ChannelSubject(subject_id="1"),
        content=[TextContent(text="question")],
        metadata={"session_key": "s", "thread_id": "t"},
    )
    return processor, msg


@pytest.mark.asyncio
async def test_every_retained_dashboard_event_is_committed_before_delivery(archive):
    chunks = [
        {"type": "reasoning", "message_id": "m1", "content": "visible thought"},
        {"type": "token", "message_id": "m1", "content": "preface"},
        {
            "type": "tool_call_chunk",
            "message_id": "m1",
            "id": "c",
            "name": "lookup",
            "args": '{"q":"value"}',
        },
        {"type": "tool_result", "id": "c", "name": "lookup", "content": "tool output"},
        {"type": "token", "message_id": "m2", "content": "answer"},
        {
            "type": "state_update",
            "data": {
                "messages": [
                    AIMessage(
                        content="answer", id="m2", response_metadata={"model_name": "final-model"}
                    )
                ]
            },
        },
    ]
    processor, msg = _dashboard_with_chunks(archive, chunks)
    stream = processor.iter_turn_chunks(msg)
    expected = ["visible thought", "preface", "value", "tool output", "answer", "final-model"]
    for chunk, needle in zip(chunks, expected, strict=True):
        delivered = await anext(stream)
        assert delivered["type"] == chunk["type"]
        assert needle in json.dumps(_committed_messages(archive))
    assert (await anext(stream))["type"] == "done"
    await stream.aclose()
    assert archive.store.turn("t")["status"] == "complete"


@pytest.mark.asyncio
async def test_write_failure_does_not_deliver_or_retry_uncommitted_content(archive, monkeypatch):
    original = archive.store.put_document
    failed = []

    def fail_after_insert(conn, **kwargs):
        original(conn, **kwargs)
        if "never-show" in json.dumps(kwargs["value"]):
            failed.append(True)
            raise OSError("simulated failed commit")

    monkeypatch.setattr(archive.store, "put_document", fail_after_insert)
    processor, msg = _dashboard_with_chunks(
        archive,
        [
            {"type": "token", "message_id": "m", "content": "visible"},
            {"type": "token", "message_id": "m", "content": "never-show"},
        ],
    )
    delivered = [chunk async for chunk in processor.iter_turn_chunks(msg)]
    assert any(chunk.get("content") == "visible" for chunk in delivered)
    assert not any("never-show" in str(chunk.get("content", "")) for chunk in delivered)
    assert any(chunk["type"] == "error" for chunk in delivered)
    assert "never-show" not in json.dumps(_committed_messages(archive))
    assert len(failed) == 1
    turn = archive.store.turn("t")
    assert turn["status"] == "failed" and turn["error"] == "archive_write_failed"
    with archive.store.db.connect() as conn:
        assert not conn.execute("SELECT 1 FROM bodies WHERE value LIKE '%never-show%'").fetchall()


@pytest.mark.asyncio
async def test_im_projection_commits_back_to_back_fragments_before_delivery(archive):
    from types import SimpleNamespace

    from octop.infra.gateway.process.stream_project import project_stream

    async def source(*_args, **_kwargs):
        yield {"type": "reasoning", "message_id": "m", "content": "thinking"}
        yield {"type": "token", "message_id": "m", "content": "reply"}

    tracker = RecordingTracker(archive, archive.begin("a", "t"), [])
    manager = SimpleNamespace(stream=source, get_agent=lambda _id: None)
    stream = project_stream(manager, "a", {}, history_tracker=tracker)
    await anext(stream)
    assert "thinking" in json.dumps(_committed_messages(archive))
    await anext(stream)
    assert "reply" in json.dumps(_committed_messages(archive))
    await stream.aclose()


def _audit_archive_writes(archive):
    with archive.store.db.connect() as conn:
        conn.executescript("""
            CREATE TEMP TABLE written_messages(id TEXT);
            CREATE TEMP TABLE written_bodies(bytes INTEGER);
            CREATE TEMP TRIGGER audit_messages AFTER UPDATE ON main.documents BEGIN
                INSERT INTO written_messages VALUES (NEW.id);
            END;
            CREATE TEMP TRIGGER audit_bodies AFTER INSERT ON main.bodies BEGIN
                INSERT INTO written_bodies VALUES (length(CAST(NEW.value AS BLOB)));
            END;
        """)


@pytest.mark.asyncio
async def test_append_reuses_large_prefix_and_does_not_rewrite_other_messages(archive):
    prefix = "".join(f"{index:04}" + "x" * 1020 for index in range(128))
    tracker = RecordingTracker(
        archive, archive.begin("a", "t"), [HumanMessage(content="keep user", id="u")]
    )
    tracker.observe({"type": "token", "message_id": "finished", "content": "earlier answer"})
    await tracker.flush()
    tracker.observe({"type": "token", "message_id": "active", "content": prefix})
    await tracker.flush()
    _audit_archive_writes(archive)
    tracker.observe({"type": "token", "message_id": "active", "content": "tail"})
    await tracker.flush()
    with archive.store.db.connect() as conn:
        assert [r[0] for r in conn.execute("SELECT id FROM written_messages")] == [
            f"message:{tracker.turn['id']}:2"
        ]
        assert conn.execute("SELECT SUM(bytes) FROM written_bodies").fetchone()[0] < 4096
        conn.execute("DELETE FROM written_messages")
        conn.execute("DELETE FROM written_bodies")
    # A full state replay with identical content must perform no document/body writes.
    tracker.observe(
        {
            "type": "state_update",
            "data": {"messages": [AIMessage(content=prefix + "tail", id="active")]},
        }
    )
    await tracker.flush()
    with archive.store.db.connect() as conn:
        conn.execute("DELETE FROM written_messages")
        conn.execute("DELETE FROM written_bodies")
    tracker.observe(
        {
            "type": "state_update",
            "data": {"messages": [AIMessage(content=prefix + "tail", id="active")]},
        }
    )
    await tracker.flush()
    with archive.store.db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM written_messages").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM written_bodies").fetchone()[0] == 0
    assert messages_from_dict(_committed_messages(archive))[-1].content == prefix + "tail"


@pytest.mark.asyncio
async def test_partial_long_tool_arguments_are_chunked_and_committed(archive):
    tracker = RecordingTracker(archive, archive.begin("a", "t"), [])
    fragment = '{"text":"' + "汉🙂" * 2048
    tracker.observe(
        {
            "type": "tool_call_chunk",
            "message_id": "m",
            "id": "call",
            "name": "write",
            "args": fragment,
        }
    )
    await tracker.flush()
    _audit_archive_writes(archive)
    tracker.observe({"type": "tool_call_chunk", "message_id": "m", "index": 0, "args": "tail"})
    await tracker.flush()
    wire = _committed_messages(archive)[0]
    assert wire["data"]["additional_kwargs"]["history_tool_args"]["0"] == fragment + "tail"
    with archive.store.db.connect() as conn:
        assert conn.execute("SELECT SUM(bytes) FROM written_bodies").fetchone()[0] < 4096
    await tracker.finish(completed=True)
    assert archive.store.turn("t")["status"] == "partial"


@pytest.mark.asyncio
async def test_cancellation_waits_for_executor_commit_before_finishing(archive, monkeypatch):
    import asyncio
    from threading import Event

    tracker = RecordingTracker(archive, archive.begin("a", "t"), [])
    tracker.observe({"type": "token", "message_id": "m", "content": "committed during cancel"})
    started, release = Event(), Event()
    original = archive.save_message_updates

    def slow_write(*args):
        started.set()
        if not release.wait(timeout=5):
            raise TimeoutError("test did not release writer")
        original(*args)

    monkeypatch.setattr(archive, "save_message_updates", slow_write)
    task = asyncio.create_task(tracker.flush())
    try:
        assert await asyncio.to_thread(started.wait, 5)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
    finally:
        release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert "committed during cancel" in json.dumps(_committed_messages(archive))
    await tracker.finish(completed=False)
    assert archive.store.turn("t")["status"] == "interrupted"


def test_process_exit_after_commit_keeps_last_fragment(archive):
    import subprocess
    import sys

    script = """
import asyncio, os, sys
from pathlib import Path
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.thread_messages import ThreadMessageRepo
from octop.infra.db.repos.trajectory_events import TrajectoryEventRepo
from octop.infra.history.store import HistoryStore
from octop.infra.history.service import HistoryArchive
from octop.infra.history.recorder import RecordingTracker
async def main():
    db = SqlitePool(Path(sys.argv[1]))
    archive = HistoryArchive(HistoryStore(Path(sys.argv[2]), identity="test"), ThreadMessageRepo(db), TrajectoryEventRepo(db), enabled=True)
    tracker = RecordingTracker(archive, archive.begin("a", "t"), [])
    tracker.observe({"type":"token", "message_id":"m", "content":"survives immediate exit"})
    await tracker.flush()
    os._exit(0)
asyncio.run(main())
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(archive.messages._db.path), str(archive.store.path)],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr
    assert "survives immediate exit" in json.dumps(_committed_messages(archive))


@pytest.mark.asyncio
async def test_old_body_encoding_remains_readable_without_rewriting_on_resume(archive):
    import hashlib

    from octop.infra.history.store import dumps

    turn = archive.begin("a", "t")
    text = "previously stored text " * 300
    body = dumps(text)
    digest = hashlib.sha256(body.encode()).hexdigest()
    doc_id = f"message:{turn['id']}:0"
    encoded = dumps(
        [
            "dict",
            [
                ["type", ["value", "ai"]],
                [
                    "data",
                    [
                        "dict",
                        [
                            ["id", ["value", "m"]],
                            ["content", ["body", digest]],
                            ["additional_kwargs", ["dict", []]],
                        ],
                    ],
                ],
            ],
        ]
    )
    with archive.store.transaction() as conn:
        conn.execute("INSERT INTO bodies VALUES (?,?)", (digest, body))
        conn.execute(
            "INSERT INTO documents VALUES (?,?,?,?,?,?)",
            (doc_id, "t", turn["id"], "message", 1, encoded),
        )
        conn.execute("INSERT INTO body_refs VALUES (?,?)", (doc_id, digest))
    archive.finish(turn["id"], "paused")
    tracker = RecordingTracker(archive, archive.begin("a", "t", resume=True), [])
    await tracker.flush()
    tracker.observe({"type": "token", "message_id": "m", "content": ""})
    await tracker.flush()
    assert messages_from_dict(_committed_messages(archive))[0].content == text
    with archive.store.db.connect() as conn:
        assert (
            conn.execute("SELECT data FROM documents WHERE id=?", (doc_id,)).fetchone()[0]
            == encoded
        )
        assert (
            conn.execute("SELECT value FROM bodies WHERE digest=?", (digest,)).fetchone()[0] == body
        )


def test_replacing_chunked_message_preserves_other_messages_shared_blocks(archive):
    turn = archive.begin("a", "t")
    text = "漢字🙂original " * 400
    first = message_to_dict(HumanMessage(content=text, id="u"))
    second = message_to_dict(AIMessage(content=text, id="a"))
    archive.save_messages(turn, [first, second])
    with archive.store.db.connect() as conn:
        assert (
            conn.execute(
                "SELECT MAX(n) FROM (SELECT COUNT(*) n FROM body_refs GROUP BY digest)"
            ).fetchone()[0]
            == 2
        )
    changed = message_to_dict(AIMessage(content="short replacement", id="a"))
    archive.save_message_updates(turn, [(1, changed)])
    assert [m.content for m in messages_from_dict(_committed_messages(archive))] == [
        text,
        "short replacement",
    ]
    with archive.store.db.connect() as conn:
        assert not conn.execute(
            "SELECT digest FROM bodies WHERE NOT EXISTS (SELECT 1 FROM body_refs WHERE body_refs.digest=bodies.digest)"
        ).fetchall()


@pytest.mark.asyncio
async def test_im_projection_stops_on_archive_failure(archive, monkeypatch):
    from types import SimpleNamespace

    from octop.infra.gateway.process.stream_project import project_stream

    async def source(*_args, **_kwargs):
        yield {"type": "token", "message_id": "m", "content": "already committed"}
        yield {"type": "token", "message_id": "m", "content": "must not be sent"}

    tracker = RecordingTracker(archive, archive.begin("a", "t"), [])
    manager = SimpleNamespace(stream=source, get_agent=lambda _id: None)
    stream = project_stream(manager, "a", {}, history_tracker=tracker)
    await anext(stream)

    def fail(*_args):
        raise OSError("write unavailable")

    monkeypatch.setattr(archive, "save_message_updates", fail)
    with pytest.raises(OSError, match="unavailable"):
        await anext(stream)
    await tracker.finish(completed=False)
    assert messages_from_dict(_committed_messages(archive))[0].content == "already committed"
    assert archive.store.turn("t")["status"] == "failed"
