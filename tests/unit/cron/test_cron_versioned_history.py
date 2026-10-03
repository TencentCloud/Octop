"""Cron delivery must use the same archive as refreshed/exported chat history."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from tests.unit.cron.test_cron_delivery import _command, _run_locked, _seed_dashboard_thread

from octop.infra.cron.delivery import CronDeliveryService
from octop.infra.db.repos.thread_messages import ThreadMessageRepo
from octop.infra.db.repos.trajectory_events import TrajectoryEventRepo
from octop.infra.db.repos.users import UserRepo
from octop.infra.history.reader import export_messages, read_page
from octop.infra.history.recorder import RecordingTracker
from octop.infra.history.service import HistoryArchive
from octop.infra.history.store import HistoryStore


@pytest.fixture
async def versioned_cron(tmp_path):
    db, session = _seed_dashboard_thread(tmp_path, thread_id="history-thread")
    messages = ThreadMessageRepo(db)
    store = HistoryStore(tmp_path / "history.sqlite", identity="test-cron")
    archive = HistoryArchive(store, messages, TrajectoryEventRepo(db), enabled=True)
    turn = archive.begin("a1", session.thread_id)
    assert turn is not None
    initial = RecordingTracker(archive, turn, [HumanMessage(content="old question", id="old-user")])
    initial.observe({"type": "token", "content": "old answer", "message_id": "old-ai"})
    await initial.finish(completed=True)

    harness = MagicMock()

    async def append(_thread_id, canonical):
        return canonical

    harness.aappend_messages = append
    manager = MagicMock()
    manager.get_agent.return_value = harness
    gateway = MagicMock()
    gateway.run_in_session = _run_locked
    gateway.require_session.return_value = session
    gateway.push_session_text = AsyncMock()
    gateway.notify_dashboard_push = AsyncMock()
    service = CronDeliveryService(
        gateway=gateway,
        agent_manager=manager,
        repos=SimpleNamespace(user_repo=UserRepo(db), thread_message_repo=messages),
        history_archive=archive,
    )
    request = {"messages": [HumanMessage(content="scheduled question", id="cron-user")]}
    service._build_agent_request = AsyncMock(return_value=request)

    async def stream(_agent, _request):
        yield {"type": "token", "content": "scheduled answer", "message_id": "cron-ai"}
        yield {
            "type": "state_snapshot",
            "data": {
                "messages": [
                    *request["messages"],
                    AIMessage(content="scheduled answer", id="cron-ai"),
                ]
            },
        }

    manager.stream = stream
    yield SimpleNamespace(
        service=service,
        archive=archive,
        store=store,
        messages=messages,
        manager=manager,
        gateway=gateway,
        session=session,
        db=db,
        path=tmp_path / "history.sqlite",
    )
    store.close()
    db.close()


@pytest.mark.parametrize("task_type", ["text", "agent"])
@pytest.mark.parametrize("enabled", [True, False])
async def test_cron_survives_history_refresh_and_export(versioned_cron, task_type, enabled):
    env = versioned_cron
    env.archive.enabled = enabled
    await env.service.deliver(_command(task_type=task_type, session_key=env.session.session_key))
    env.gateway.push_session_text.assert_awaited_once()
    expected = "记得喝水" if task_type == "text" else "scheduled answer"
    page = await read_page(env.archive, env.manager, "a1", env.session.thread_id, limit=20)
    contents = [wire["data"]["content"] for wire in page["messages"]]
    assert contents[:2] == ["old question", "old answer"]
    assert contents.count(expected) == 1
    exported = await export_messages(env.archive, env.manager, "a1", env.session.thread_id)
    assert exported == page["messages"]
    turn = env.store.turn(env.session.thread_id)
    assert turn["status"] == "complete"
    assert turn["format"] == ("v2" if enabled else "legacy")


async def test_interrupted_agent_retains_partial_history(versioned_cron):
    env = versioned_cron

    async def stream(_agent, _request):
        yield {"type": "token", "content": "partial scheduled answer", "message_id": "cron-ai"}
        raise RuntimeError("synthetic model failure")

    env.manager.stream = stream
    with pytest.raises(RuntimeError, match="synthetic model failure"):
        await env.service.deliver(_command(task_type="agent"))
    page = await read_page(env.archive, env.manager, "a1", env.session.thread_id, limit=20)
    assert page["messages"][-1]["data"]["content"] == "partial scheduled answer"
    assert env.store.turn(env.session.thread_id)["status"] == "interrupted"
    env.gateway.push_session_text.assert_not_awaited()


async def test_archive_write_failure_does_not_report_delivery_success(versioned_cron, monkeypatch):
    env = versioned_cron

    def fail_write(*args):
        raise OSError("synthetic archive failure")

    monkeypatch.setattr(env.archive, "save_message_updates", fail_write)
    with pytest.raises(OSError, match="synthetic archive failure"):
        await env.service.deliver(_command())
    env.gateway.push_session_text.assert_not_awaited()

    assert env.store.turn(env.session.thread_id)["status"] == "failed"
    monkeypatch.undo()
    await env.service.deliver(_command())
    env.gateway.push_session_text.assert_awaited_once()


@pytest.mark.parametrize("task_type", ["text", "agent"])
async def test_cron_history_is_persisted_across_archive_reopen(versioned_cron, task_type):
    env = versioned_cron
    await env.service.deliver(_command(task_type=task_type))
    reopened = HistoryStore(env.path, identity="test-cron")
    try:
        archive = HistoryArchive(reopened, env.messages, TrajectoryEventRepo(env.db), enabled=True)
        page = await read_page(archive, env.manager, "a1", env.session.thread_id, limit=20)
        expected = "记得喝水" if task_type == "text" else "scheduled answer"
        assert page["messages"][-1]["data"]["content"] == expected
    finally:
        reopened.close()


async def test_checkpoint_failure_releases_archive_turn(versioned_cron):
    env = versioned_cron
    harness = env.manager.get_agent.return_value
    harness.aappend_messages = AsyncMock(side_effect=RuntimeError("checkpoint failed"))
    with pytest.raises(RuntimeError, match="checkpoint failed"):
        await env.service.deliver(_command())
    assert env.store.turn(env.session.thread_id)["status"] == "interrupted"
    env.gateway.push_session_text.assert_not_awaited()
    next_turn = env.archive.begin("a1", env.session.thread_id)
    assert next_turn is not None
    env.archive.finish(next_turn["id"], "interrupted")


@pytest.mark.parametrize("task_type", ["text", "agent"])
async def test_first_versioned_cron_preserves_legacy_prefix(versioned_cron, task_type):
    env = versioned_cron
    env.archive.remove_thread(env.session.thread_id)
    from octop.infra.history.projection import message_inputs

    env.messages.append_if_ready(
        env.session.thread_id,
        message_inputs(
            [
                HumanMessage(content="legacy question", id="legacy-user"),
                AIMessage(content="legacy answer", id="legacy-ai"),
            ]
        ),
    )
    await env.service.deliver(_command(task_type=task_type))
    page = await read_page(env.archive, env.manager, "a1", env.session.thread_id, limit=20)
    assert [wire["data"]["content"] for wire in page["messages"]][:2] == [
        "legacy question",
        "legacy answer",
    ]
    assert len(page["messages"]) == 4


async def test_paused_history_is_not_overwritten_by_cron(versioned_cron):
    env = versioned_cron
    turn = env.archive.begin("a1", env.session.thread_id)
    env.archive.finish(turn["id"], "paused")
    with pytest.raises(ValueError, match="Finish the paused turn"):
        await env.service.deliver(_command())
    env.gateway.push_session_text.assert_not_awaited()
    assert env.store.turn(env.session.thread_id)["status"] == "paused"


@pytest.mark.parametrize("task_type", ["text", "agent"])
async def test_first_cron_pins_legacy_checkpoint_before_mutation(versioned_cron, task_type):
    env = versioned_cron
    env.archive.remove_thread(env.session.thread_id)
    env.messages.mark_projection(env.session.thread_id, "pending")
    config = {
        "configurable": {"thread_id": env.session.thread_id, "checkpoint_id": "old-checkpoint"}
    }
    state = SimpleNamespace(
        next=(),
        config=config,
        values={
            "messages": [
                HumanMessage(content="checkpoint question", id="checkpoint-user"),
                AIMessage(content="checkpoint answer", id="checkpoint-ai"),
            ]
        },
    )
    harness = env.manager.get_agent.return_value
    harness.graph.aget_state = AsyncMock(return_value=state)
    await env.service.deliver(_command(task_type=task_type))
    page = await read_page(env.archive, env.manager, "a1", env.session.thread_id, limit=20)
    assert [wire["data"]["content"] for wire in page["messages"]][:2] == [
        "checkpoint question",
        "checkpoint answer",
    ]
    assert len(page["messages"]) == 4
    assert harness.graph.aget_state.call_args.args[0] == config


async def test_first_cron_with_empty_checkpoint_starts_versioned_history(versioned_cron):
    env = versioned_cron
    env.archive.remove_thread(env.session.thread_id)
    env.messages.mark_projection(env.session.thread_id, "pending")
    env.manager.get_agent.return_value.graph.aget_state = AsyncMock(return_value=None)
    await env.service.deliver(_command())
    page = await read_page(env.archive, env.manager, "a1", env.session.thread_id, limit=20)
    assert len(page["messages"]) == 2
    assert page["messages"][-1]["data"]["content"] == "记得喝水"


async def test_repeated_cron_deliveries_each_remain_visible(versioned_cron):
    env = versioned_cron
    await env.service.deliver(_command())
    await env.service.deliver(_command())
    page = await read_page(env.archive, env.manager, "a1", env.session.thread_id, limit=20)
    assert [wire["data"]["content"] for wire in page["messages"]].count("记得喝水") == 2
    assert len({wire["data"]["id"] for wire in page["messages"]}) == 6
