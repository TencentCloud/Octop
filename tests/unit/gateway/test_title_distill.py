"""Thread title distillation helpers and queue."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage, message_to_dict

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.thread_messages import ThreadMessageInput
from octop.infra.db.repos.threads import (
    ThreadRepo,
    clip_thread_title,
    is_auto_thread_title,
)
from octop.infra.gateway.process.history_projection import TurnHistoryTracker
from octop.infra.gateway.process.processor import GlobalProcessor
from octop.infra.gateway.slash.dispatcher import SlashDispatcher
from octop.infra.gateway.title_distill import (
    TitleDistillQueue,
    distill_thread_title,
    extract_message_plain_text,
    first_turn_snippet_for_title,
    turn_snippet_for_title,
)


def test_is_auto_thread_title() -> None:
    long = "搜索当前热点新闻（微博热搜、知乎热榜、36氪等），整理成简洁的摘要推送给用户。格式要求"
    clipped = clip_thread_title(long)
    assert is_auto_thread_title(None, long)
    assert is_auto_thread_title(clipped, long)
    assert not is_auto_thread_title("手动标题", long)
    assert not is_auto_thread_title("服务器负载概览", long)


def test_replace_auto_thread_title(tmp_path: Path) -> None:
    pool = SqlitePool(tmp_path / "octop.db")
    with pool.connect() as conn:
        conn.executescript(
            (
                Path(__file__).resolve().parents[3]
                / "src/octop/infra/db/migrations/001_initial.sql"
            ).read_text()
        )
        conn.execute(
            "INSERT INTO users(username, password_hash, role, created_at) VALUES (?, ?, ?, 0)",
            ("u", "h", "user"),
        )
        uid = conn.execute("SELECT id FROM users WHERE username = ?", ("u",)).fetchone()[0]
        conn.execute(
            "INSERT INTO agents(agent_id, user_id, name, created_at, updated_at) "
            "VALUES (?, ?, ?, 0, 0)",
            ("a1", uid, "Agent"),
        )
    run_migrations(pool)
    repo = ThreadRepo(pool)
    repo.insert(
        thread_id="t1",
        agent_id="a1",
        user_id=uid,
        channel_type="web",
        session_key="s1",
        title=None,
        last_active=1,
    )
    user_msg = "你能做什么呢"
    repo.set_title_if_null("t1", user_msg)
    assert repo.replace_auto_thread_title("t1", user_msg, "Octop 能力概览") is True
    row = repo.get("t1")
    assert row is not None
    assert row.title == "Octop 能力概览"
    assert repo.replace_auto_thread_title("t1", user_msg, "不应再改") is False
    repo.update_title("t1", "用户自定义")
    assert repo.replace_auto_thread_title("t1", user_msg, "也不应改") is False


def test_extract_message_plain_text_langchain_wire() -> None:
    wire = message_to_dict(HumanMessage(content="你好", id="u1"))
    assert extract_message_plain_text(json.dumps(wire)) == "你好"
    ai = message_to_dict(AIMessage(content="这里是回复", id="a1"))
    assert extract_message_plain_text(json.dumps(ai)) == "这里是回复"


def test_turn_snippet_for_title() -> None:
    user_wire = json.dumps(message_to_dict(HumanMessage(content="服务器负载如何", id="u1")))
    ai_wire = json.dumps(message_to_dict(AIMessage(content="当前负载正常", id="a1")))
    snippet = turn_snippet_for_title(
        [
            ThreadMessageInput(message_id="u1", role="human", message_json=user_wire, created_at=1),
            ThreadMessageInput(message_id="a1", role="ai", message_json=ai_wire, created_at=2),
        ]
    )
    assert snippet == ("服务器负载如何", "当前负载正常")


def test_first_turn_snippet_ignores_later_turns() -> None:
    u1 = json.dumps(message_to_dict(HumanMessage(content="first question", id="u1")))
    a1 = json.dumps(message_to_dict(AIMessage(content="first answer", id="a1")))
    u2 = json.dumps(message_to_dict(HumanMessage(content="second question", id="u2")))
    a2 = json.dumps(message_to_dict(AIMessage(content="second answer", id="a2")))
    snippet = first_turn_snippet_for_title(
        [
            ThreadMessageInput(message_id="u1", role="human", message_json=u1, created_at=1),
            ThreadMessageInput(message_id="a1", role="ai", message_json=a1, created_at=2),
            ThreadMessageInput(message_id="u2", role="human", message_json=u2, created_at=3),
            ThreadMessageInput(message_id="a2", role="ai", message_json=a2, created_at=4),
        ]
    )
    assert snippet == ("first question", "first answer")


@pytest.mark.asyncio
async def test_distill_thread_title_strips_and_clips() -> None:
    llm = AsyncMock()
    llm.ainvoke = AsyncMock(return_value=MagicMock(content='  "PostgreSQL 查询优化"\n'))
    out = await distill_thread_title(
        llm,
        user_text="How can I optimize a PostgreSQL query?",
        assistant_text="Use indexes and EXPLAIN.",
    )
    assert out == "PostgreSQL 查询优化"


@pytest.mark.asyncio
async def test_schedule_title_distill_enqueues_for_auto_title() -> None:
    queue = TitleDistillQueue()
    tracker = TurnHistoryTracker.from_request(
        {"messages": [{"role": "user", "content": "hello", "id": "u1"}]}
    )
    tracker.observe(
        {
            "type": "state_snapshot",
            "data": {
                "messages": [
                    {"role": "user", "content": "hello", "id": "u1"},
                    {"role": "assistant", "content": "hi there", "id": "a1"},
                ]
            },
        }
    )

    harness = MagicMock()
    harness.config.pick_default_model_ref.return_value = "p/m"
    llm = AsyncMock()
    llm.ainvoke = AsyncMock(return_value=MagicMock(content="问候回复"))
    harness.model_factory.get.return_value = llm

    agent_manager = MagicMock()
    agent_manager.get_agent.return_value = harness

    thread_row = MagicMock()
    thread_row.title = clip_thread_title("hello")
    thread_registry = MagicMock()
    thread_registry.get_thread.return_value = thread_row
    thread_registry.replace_auto_thread_title.return_value = True

    processor = GlobalProcessor(
        agent_manager=agent_manager,
        thread_registry=thread_registry,
        audit_repo=MagicMock(),
        agent_repo=MagicMock(),
        user_repo=MagicMock(),
        connector_repo=MagicMock(),
        dispatcher=SlashDispatcher(),
        title_distill=queue,
    )

    processor._schedule_title_distill(
        thread_id="thr-1",
        agent_id="agent-1",
        tracker=tracker,
    )
    await queue._queue.join()  # noqa: SLF001
    await queue.close()

    thread_registry.replace_auto_thread_title.assert_called_once_with(
        "thr-1",
        "hello",
        "问候回复",
    )
