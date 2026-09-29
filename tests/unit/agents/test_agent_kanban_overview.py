"""Kanban overview aggregation: buckets, snippets, HITL/plan waits."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from octop.infra.agents.overview import (
    ACTIVITY_BLOCKED,
    ACTIVITY_DONE,
    ACTIVITY_IDLE,
    ACTIVITY_WAITING,
    ACTIVITY_WORKING,
    KANBAN_DONE,
    KANBAN_IDLE,
    KANBAN_NEEDS_YOU,
    KANBAN_WORKING,
    agent_kanban_statuses,
    bucket_for_display_state,
    resolve_activity_state,
    resolve_display_state,
    resolve_unseen,
)
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.agents import AgentRepo
from octop.infra.db.repos.sessions import SessionRepo
from octop.infra.db.repos.thread_messages import ThreadMessageInput, ThreadMessageRepo
from octop.infra.db.repos.threads import ThreadRepo
from octop.infra.db.repos.users import UserRepo
from octop.infra.gateway.hitl.coordinator import HitlChannelCoordinator
from octop.infra.gateway.ws.ws_hub import WebSocketHub


@dataclass
class _AgentRow:
    agent_id: str
    user_id: int = 1
    last_state: str | None = "running"


@dataclass
class _Registry:
    active: set[str] = field(default_factory=set)

    def is_agent_active(self, agent_id: str) -> bool:
        return agent_id in self.active


@dataclass
class _ThreadRegistry:
    rows: dict[str, Any] = field(default_factory=dict)

    def get_thread(self, thread_id: str) -> Any:
        return self.rows.get(thread_id)


@dataclass
class _Processor:
    hitl_coordinator: HitlChannelCoordinator


@dataclass
class _Gateway:
    processor: _Processor
    ws_hub: WebSocketHub
    thread_registry: _ThreadRegistry


@dataclass
class _AppRuntime:
    agent_registry: _Registry
    gateway: _Gateway


@dataclass
class _Services:
    thread_repo: ThreadRepo
    thread_message_repo: ThreadMessageRepo
    session_repo: SessionRepo


@dataclass
class _Server:
    app_runtime: _AppRuntime
    services: _Services


def _message(role: str, text: str) -> ThreadMessageInput:
    return ThreadMessageInput(
        message_id=None,
        role=role,
        message_json=json.dumps({"type": role, "content": [{"type": "text", "text": text}]}),
        created_at=1,
    )


def _envelope_message(role: str, text: str, *, think: str | None = None) -> ThreadMessageInput:
    """Real projection shape: LangChain ``message_to_dict`` envelope + think block."""
    content = (f"<think>{think}</think>" if think else "") + text
    return ThreadMessageInput(
        message_id=None,
        role=role,
        message_json=json.dumps(
            {"type": role, "data": {"content": content}},
            ensure_ascii=False,
        ),
        created_at=1,
    )


@pytest.fixture
def server(tmp_path: Path) -> _Server:
    db = SqlitePool(tmp_path / "octop.db")
    run_migrations(db)
    UserRepo(db).create(username="testuser", password_hash="x", role="user")
    UserRepo(db).create(username="otheruser", password_hash="x", role="user")
    AgentRepo(db).create(agent_id="a1", user_id=1, name="Agent 1")
    return _Server(
        app_runtime=_AppRuntime(
            agent_registry=_Registry(),
            gateway=_Gateway(
                processor=_Processor(hitl_coordinator=HitlChannelCoordinator()),
                ws_hub=WebSocketHub(),
                thread_registry=_ThreadRegistry(),
            ),
        ),
        services=_Services(
            thread_repo=ThreadRepo(db),
            thread_message_repo=ThreadMessageRepo(db),
            session_repo=SessionRepo(db),
        ),
    )


def _seed_thread(
    server: _Server, *, agent_id: str, thread_id: str, user_id: int = 1, title: str | None = None
) -> None:
    session_key = f"{agent_id}:dashboard:{user_id}"
    server.services.thread_repo.insert(
        thread_id=thread_id,
        agent_id=agent_id,
        user_id=user_id,
        channel_type="dashboard",
        session_key=session_key,
        title=title,
    )
    server.services.session_repo.upsert(
        session_key=session_key,
        agent_id=agent_id,
        user_id=user_id,
        channel_type="dashboard",
        chat_type="single",
        thread_id=thread_id,
    )


def _set_pending_plan(server: _Server, thread_id: str) -> None:
    with server.services.thread_repo._db.transaction() as conn:  # noqa: SLF001
        conn.execute(
            "UPDATE threads SET pending_plan_path = ? WHERE thread_id = ?",
            (f"{thread_id}.md", thread_id),
        )


def _statuses(server: _Server, rows: list[_AgentRow], unread: dict[str, int] | None = None):
    return agent_kanban_statuses(server, 1, rows, unread_by_agent=unread or {})


def test_fsm_activity_priority() -> None:
    assert (
        resolve_activity_state(
            hitl_pending=True,
            failed=False,
            awaiting_plan=True,
            busy=True,
            assistant_last=True,
        )
        == ACTIVITY_BLOCKED
    )
    assert (
        resolve_activity_state(
            hitl_pending=False,
            failed=False,
            awaiting_plan=True,
            busy=True,
            assistant_last=True,
        )
        == ACTIVITY_WORKING
    )
    assert (
        resolve_activity_state(
            hitl_pending=False,
            failed=False,
            awaiting_plan=True,
            busy=False,
            assistant_last=True,
        )
        == ACTIVITY_WAITING
    )
    assert (
        resolve_activity_state(
            hitl_pending=False,
            failed=False,
            awaiting_plan=False,
            busy=False,
            assistant_last=True,
        )
        == ACTIVITY_DONE
    )
    assert (
        resolve_activity_state(
            hitl_pending=False,
            failed=False,
            awaiting_plan=False,
            busy=False,
            assistant_last=False,
        )
        == ACTIVITY_IDLE
    )
    assert (
        resolve_activity_state(
            hitl_pending=False,
            failed=False,
            awaiting_plan=False,
            busy=False,
            assistant_last=False,
            has_unread=True,
        )
        == ACTIVITY_DONE
    )


def test_fsm_done_settles_to_idle_when_seen() -> None:
    unseen = resolve_unseen(activity=ACTIVITY_DONE, unread=0, latest_active=100, last_read_at=50)
    assert unseen is True
    assert resolve_display_state(ACTIVITY_DONE, unseen=True) == ACTIVITY_DONE
    assert bucket_for_display_state(ACTIVITY_DONE) == KANBAN_DONE

    seen = resolve_unseen(activity=ACTIVITY_DONE, unread=0, latest_active=100, last_read_at=100)
    assert seen is False
    assert resolve_display_state(ACTIVITY_DONE, unseen=False) == ACTIVITY_IDLE
    assert bucket_for_display_state(ACTIVITY_IDLE) == KANBAN_IDLE


def test_fsm_attention_stays_needs_you() -> None:
    assert bucket_for_display_state(ACTIVITY_BLOCKED) == KANBAN_NEEDS_YOU
    assert bucket_for_display_state(ACTIVITY_WAITING) == KANBAN_NEEDS_YOU
    assert bucket_for_display_state(ACTIVITY_WORKING) == KANBAN_WORKING


def test_idle_when_quiet(server: _Server) -> None:
    statuses = _statuses(server, [_AgentRow("a1")])
    assert statuses["a1"]["kanban_status"] == KANBAN_IDLE
    assert statuses["a1"]["busy"] is False
    assert statuses["a1"]["latest_thread"] is None


def test_unseen_assistant_reply_is_done_until_mark_read(server: _Server) -> None:
    """A finished turn stays in Done until the user opens the chat (mark-read)."""
    _seed_thread(server, agent_id="a1", thread_id="t1", user_id=1)
    active_at = int(time.time()) - 60
    with server.services.thread_repo._db.transaction() as conn:  # noqa: SLF001
        conn.execute(
            "UPDATE threads SET last_active = ? WHERE thread_id = ?",
            (active_at, "t1"),
        )
        # Session was touched before the reply finished → still unseen.
        conn.execute(
            "UPDATE sessions SET last_read_at = ? WHERE agent_id = ?",
            (active_at - 120, "a1"),
        )
    server.services.thread_message_repo.append_legacy_interval(
        "t1",
        [
            _message("human", "hi"),
            _envelope_message("ai", "简报已完成并保存。", think="用户要两句话介绍"),
        ],
    )
    statuses = _statuses(server, [_AgentRow("a1")])
    assert statuses["a1"]["activity_state"] == ACTIVITY_DONE
    assert statuses["a1"]["unseen"] is True
    assert statuses["a1"]["kanban_status"] == KANBAN_DONE
    snippet = statuses["a1"]["latest_thread"]["message"]
    assert snippet["role"] == "assistant"
    assert snippet["text"] == "简报已完成并保存。"

    server.services.session_repo.clear_unread_for_agent("a1", 1)
    statuses = _statuses(server, [_AgentRow("a1")])
    assert statuses["a1"]["activity_state"] == ACTIVITY_DONE
    assert statuses["a1"]["unseen"] is False
    assert statuses["a1"]["kanban_status"] == KANBAN_IDLE


def test_user_last_message_is_not_done(server: _Server) -> None:
    _seed_thread(server, agent_id="a1", thread_id="t1", user_id=1)
    with server.services.thread_repo._db.transaction() as conn:  # noqa: SLF001
        conn.execute(
            "UPDATE threads SET last_active = ? WHERE thread_id = ?",
            (int(time.time()) - 30, "t1"),
        )
    server.services.thread_message_repo.append_legacy_interval(
        "t1", [_message("ai", "answer"), _message("human", "follow-up question")]
    )
    statuses = _statuses(server, [_AgentRow("a1")])
    assert statuses["a1"]["kanban_status"] == KANBAN_IDLE


def test_working_when_invocation_active(server: _Server) -> None:
    server.app_runtime.agent_registry.active.add("a1")
    statuses = _statuses(server, [_AgentRow("a1")])
    assert statuses["a1"]["kanban_status"] == KANBAN_WORKING
    assert statuses["a1"]["busy"] is True


def test_working_when_turn_active_via_ws_hub(server: _Server) -> None:
    _seed_thread(server, agent_id="a1", thread_id="t1")
    server.app_runtime.gateway.thread_registry.rows["t1"] = _AgentRow("a1")
    server.app_runtime.gateway.ws_hub.mark_turn_active("t1")
    statuses = _statuses(server, [_AgentRow("a1")])
    assert statuses["a1"]["kanban_status"] == KANBAN_WORKING


def test_working_when_starting(server: _Server) -> None:
    statuses = _statuses(server, [_AgentRow("a1", last_state="starting")])
    assert statuses["a1"]["kanban_status"] == KANBAN_WORKING


def test_done_when_unread(server: _Server) -> None:
    statuses = _statuses(server, [_AgentRow("a1")], unread={"a1": 3})
    assert statuses["a1"]["kanban_status"] == KANBAN_DONE


def test_needs_you_when_failed(server: _Server) -> None:
    statuses = _statuses(server, [_AgentRow("a1", last_state="failed")])
    assert statuses["a1"]["kanban_status"] == KANBAN_NEEDS_YOU


def test_needs_you_wins_over_working_and_done(server: _Server) -> None:
    server.app_runtime.agent_registry.active.add("a1")
    statuses = _statuses(server, [_AgentRow("a1", last_state="failed")], unread={"a1": 2})
    assert statuses["a1"]["kanban_status"] == KANBAN_NEEDS_YOU


def test_needs_you_when_hitl_pending(server: _Server) -> None:
    _seed_thread(server, agent_id="a1", thread_id="t1")
    server.app_runtime.gateway.processor.hitl_coordinator.store.register(
        thread_id="t1",
        agent_id="a1",
        user_id=1,
        session_key="a1:dashboard:t1",
        channel_type="dashboard",
        action_requests=[{"name": "bash"}],
        review_configs=None,
    )
    statuses = _statuses(server, [_AgentRow("a1")])
    assert statuses["a1"]["kanban_status"] == KANBAN_NEEDS_YOU
    assert statuses["a1"]["hitl_pending"] is not None
    assert statuses["a1"]["hitl_pending"]["count"] == 1
    assert statuses["a1"]["hitl_pending"]["thread_id"] == "t1"


def test_hitl_pending_scoped_to_other_user_is_ignored(server: _Server) -> None:
    _seed_thread(server, agent_id="a1", thread_id="t1")
    server.app_runtime.gateway.processor.hitl_coordinator.store.register(
        thread_id="t1",
        agent_id="a1",
        user_id=2,
        session_key="a1:dashboard:t1",
        channel_type="dashboard",
        action_requests=[{"name": "bash"}],
        review_configs=None,
    )
    statuses = _statuses(server, [_AgentRow("a1")])
    assert statuses["a1"]["kanban_status"] == KANBAN_IDLE
    assert statuses["a1"]["hitl_pending"] is None


def test_needs_you_when_plan_pending(server: _Server) -> None:
    _seed_thread(server, agent_id="a1", thread_id="t1")
    _set_pending_plan(server, "t1")
    statuses = _statuses(server, [_AgentRow("a1")])
    assert statuses["a1"]["kanban_status"] == KANBAN_NEEDS_YOU
    assert statuses["a1"]["pending_plan"] is True


def test_working_wins_over_stale_pending_plan(server: _Server) -> None:
    """Once a turn is running, a leftover pending_plan_path must not pin needs_you."""
    _seed_thread(server, agent_id="a1", thread_id="t1")
    _set_pending_plan(server, "t1")
    server.app_runtime.agent_registry.active.add("a1")
    statuses = _statuses(server, [_AgentRow("a1")])
    assert statuses["a1"]["kanban_status"] == KANBAN_WORKING
    assert statuses["a1"]["busy"] is True
    assert statuses["a1"]["pending_plan"] is False


def test_attention_thread_prefers_pending_over_newest(server: _Server) -> None:
    """Card deep-links to the plan-pending thread, not the latest chat."""
    _seed_thread(server, agent_id="a1", thread_id="t-plan")
    _set_pending_plan(server, "t-plan")
    _seed_thread(server, agent_id="a1", thread_id="t-new")
    with server.services.thread_repo._db.transaction() as conn:  # noqa: SLF001
        conn.execute(
            "UPDATE threads SET last_active = ? WHERE thread_id = 't-plan'",
            (int(time.time()) - 3600,),
        )
    statuses = _statuses(server, [_AgentRow("a1")])
    assert statuses["a1"]["latest_thread"]["thread_id"] == "t-new"
    assert statuses["a1"]["attention_thread_id"] == "t-plan"


def test_attention_thread_hits_hitl_first(server: _Server) -> None:
    _seed_thread(server, agent_id="a1", thread_id="t-plan")
    _set_pending_plan(server, "t-plan")
    _seed_thread(server, agent_id="a1", thread_id="t-hitl")
    server.app_runtime.gateway.processor.hitl_coordinator.store.register(
        thread_id="t-hitl",
        agent_id="a1",
        user_id=1,
        session_key="a1:dashboard:t-hitl",
        channel_type="dashboard",
        action_requests=[{"name": "bash"}],
        review_configs=None,
    )
    statuses = _statuses(server, [_AgentRow("a1")])
    assert statuses["a1"]["attention_thread_id"] == "t-hitl"


def test_attention_thread_falls_back_to_latest(server: _Server) -> None:
    _seed_thread(server, agent_id="a1", thread_id="t1", title="only chat")
    statuses = _statuses(server, [_AgentRow("a1")])
    assert statuses["a1"]["attention_thread_id"] == "t1"


def test_latest_thread_with_snippet(server: _Server) -> None:
    _seed_thread(server, agent_id="a1", thread_id="t1", title="first chat")
    _seed_thread(server, agent_id="a1", thread_id="t2", title="second chat")
    server.services.thread_message_repo.append_legacy_interval(
        "t1", [_message("human", "older question")]
    )
    server.services.thread_message_repo.append_legacy_interval(
        "t2", [_message("human", "hello"), _message("ai", "world answer")]
    )
    statuses = _statuses(server, [_AgentRow("a1")])
    latest = statuses["a1"]["latest_thread"]
    assert latest is not None
    assert latest["thread_id"] == "t2"
    assert latest["title"] == "second chat"
    assert latest["message"] is not None
    assert latest["message"]["role"] == "assistant"
    assert latest["message"]["text"] == "world answer"


def test_snippet_skips_trailing_tool_message(server: _Server) -> None:
    _seed_thread(server, agent_id="a1", thread_id="t1")
    server.services.thread_message_repo.append_legacy_interval(
        "t1",
        [_message("human", "run it"), _message("tool", "raw output"), _message("ai", "done!")],
    )
    statuses = _statuses(server, [_AgentRow("a1")])
    latest = statuses["a1"]["latest_thread"]
    assert latest is not None
    assert latest["message"] is not None
    assert latest["message"]["text"] == "done!"


def test_snippet_clipped_to_limit(server: _Server) -> None:
    _seed_thread(server, agent_id="a1", thread_id="t1")
    server.services.thread_message_repo.append_legacy_interval("t1", [_message("ai", "x" * 200)])
    statuses = _statuses(server, [_AgentRow("a1")])
    latest = statuses["a1"]["latest_thread"]
    assert latest is not None
    assert latest["message"] is not None
    text = latest["message"]["text"]
    assert len(text) <= 80
    assert text.endswith("…")


def test_snippet_strips_markdown_emphasis(server: _Server) -> None:
    _seed_thread(server, agent_id="a1", thread_id="t1")
    server.services.thread_message_repo.append_legacy_interval(
        "t1",
        [_message("ai", "请问**什么方面**的 `还有哪些` 呢？")],
    )
    statuses = _statuses(server, [_AgentRow("a1")])
    latest = statuses["a1"]["latest_thread"]
    assert latest is not None
    assert latest["message"] is not None
    text = latest["message"]["text"]
    assert "**" not in text
    assert "`" not in text
    assert "什么方面" in text
    assert "还有哪些" in text


def test_threads_of_other_users_are_invisible(server: _Server) -> None:
    _seed_thread(server, agent_id="a1", thread_id="t1", user_id=2)
    statuses = _statuses(server, [_AgentRow("a1")])
    assert statuses["a1"]["latest_thread"] is None


def test_hitl_store_lists_pending_by_user() -> None:
    from octop.infra.gateway.hitl.store import HitlPendingStore

    store = HitlPendingStore()
    for thread_id in ("t2", "t1"):
        store.register(
            thread_id=thread_id,
            agent_id="a1",
            user_id=7,
            session_key=f"a1:dashboard:{thread_id}",
            channel_type="dashboard",
            action_requests=[],
            review_configs=None,
        )
    store.register(
        thread_id="t3",
        agent_id="a2",
        user_id=8,
        session_key="a2:dashboard:t3",
        channel_type="dashboard",
        action_requests=[],
        review_configs=None,
    )
    records = store.list_pending_by_user(7)
    assert [r.thread_id for r in records] == ["t1", "t2"]
    assert store.list_pending_by_user(8)[0].agent_id == "a2"
    assert store.list_pending_by_user(9) == []


def test_ws_hub_active_turn_snapshot() -> None:
    hub = WebSocketHub()
    assert hub.active_turn_thread_ids() == set()
    hub.mark_turn_active("t1")
    snapshot = hub.active_turn_thread_ids()
    snapshot.add("t2")
    assert hub.active_turn_thread_ids() == {"t1"}
    hub.mark_turn_idle("t1")
    assert hub.active_turn_thread_ids() == set()
