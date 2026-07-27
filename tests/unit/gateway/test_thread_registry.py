"""tests/unit/test_thread_registry.py"""

from __future__ import annotations

from pathlib import Path

import pytest

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.agents import AgentRepo
from octop.infra.db.repos.sessions import SessionRepo
from octop.infra.db.repos.threads import ThreadRepo
from octop.infra.db.repos.users import UserRepo
from octop.infra.gateway.threads import ThreadRegistry


@pytest.fixture
def registry(tmp_path: Path) -> ThreadRegistry:
    db = SqlitePool(tmp_path / "octop.db")
    run_migrations(db)
    UserRepo(db).create(username="testuser", password_hash="x", role="user")
    AgentRepo(db).create(agent_id="a1", user_id=1, name="Agent 1")
    AgentRepo(db).create(agent_id="a2", user_id=1, name="Agent 2")
    return ThreadRegistry(session_repo=SessionRepo(db), thread_repo=ThreadRepo(db))


@pytest.mark.asyncio
async def test_get_or_create_stable(registry: ThreadRegistry) -> None:
    tid1 = await registry.get_or_create(
        agent_id="a1",
        user_id=1,
        channel_type="feishu",
        channel_subject_id="ou_x",
        channel_chat_type="dm",
    )
    tid2 = await registry.get_or_create(
        agent_id="a1",
        user_id=1,
        channel_type="feishu",
        channel_subject_id="ou_x",
        channel_chat_type="dm",
    )
    assert tid1 == tid2
    assert tid1.startswith("thr_")


@pytest.mark.asyncio
async def test_reset_creates_new(registry: ThreadRegistry) -> None:
    tid1 = await registry.get_or_create(
        agent_id="a1",
        user_id=1,
        channel_type="feishu",
        channel_subject_id="ou_x",
        channel_chat_type="dm",
    )
    tid2 = await registry.reset(
        agent_id="a1",
        user_id=1,
        channel_type="feishu",
        channel_subject_id="ou_x",
        channel_chat_type="dm",
    )
    assert tid1 != tid2
    assert len(registry.list_threads(agent_id="a1")) == 2
    row = registry.get_thread(tid2)
    assert row is not None
    assert row.last_active == 0


@pytest.mark.asyncio
async def test_different_agents_isolated(registry: ThreadRegistry) -> None:
    tid1 = await registry.get_or_create(
        agent_id="a1",
        user_id=1,
        channel_type="feishu",
        channel_subject_id="ou_x",
        channel_chat_type="dm",
    )
    tid2 = await registry.get_or_create(
        agent_id="a2",
        user_id=1,
        channel_type="feishu",
        channel_subject_id="ou_x",
        channel_chat_type="dm",
    )
    assert tid1 != tid2


@pytest.mark.asyncio
async def test_rebind(registry: ThreadRegistry) -> None:
    sk = "a1:feishu:ou_x:dm"
    tid1 = await registry.get_or_create(
        agent_id="a1",
        user_id=1,
        channel_type="feishu",
        channel_subject_id="ou_x",
        channel_chat_type="dm",
    )
    await registry.reset(
        agent_id="a1",
        user_id=1,
        channel_type="feishu",
        channel_subject_id="ou_x",
        channel_chat_type="dm",
    )
    await registry.rebind(session_key=sk, thread_id=tid1, agent_id="a1")
    tid2 = registry.get_bound_thread_id(sk)
    assert tid2 == tid1


@pytest.mark.asyncio
async def test_rebind_rejects_foreign_thread(registry: ThreadRegistry) -> None:
    sk = ThreadRegistry.dashboard_key(agent_id="a1", user_id=1)
    tid = await registry.get_or_create(
        agent_id="a2",
        user_id=1,
        channel_type="dashboard",
        channel_subject_id="1",
        channel_chat_type="dm",
    )
    with pytest.raises(ValueError, match="does not belong"):
        await registry.rebind(session_key=sk, thread_id=tid, agent_id="a1")


@pytest.mark.asyncio
async def test_rebind_repairs_stale_session_agent_id(registry: ThreadRegistry) -> None:
    sk = ThreadRegistry.dashboard_key(agent_id="a1", user_id=1)
    tid = await registry.get_or_create(
        agent_id="a1",
        user_id=1,
        channel_type="dashboard",
        channel_subject_id="1",
        channel_chat_type="dm",
    )
    registry._sessions.set_agent_id(sk, "a2")
    await registry.rebind(session_key=sk, thread_id=tid, agent_id="a1")
    row = registry.get_session(sk)
    assert row is not None
    assert row.agent_id == "a1"
    assert row.thread_id == tid


@pytest.mark.asyncio
async def test_get_or_create_by_key_rejects_agent_mismatch(registry: ThreadRegistry) -> None:
    sk = ThreadRegistry.dashboard_key(agent_id="a1", user_id=1)
    await registry.get_or_create_by_key(
        session_key=sk,
        agent_id="a1",
        user_id=1,
        channel_type="dashboard",
    )
    with pytest.raises(ValueError, match="belongs to agent"):
        await registry.get_or_create_by_key(
            session_key=sk,
            agent_id="a2",
            user_id=1,
            channel_type="dashboard",
        )


@pytest.mark.asyncio
async def test_get_or_create_by_key_backfills_channel_id(registry: ThreadRegistry) -> None:
    sk = ThreadRegistry.make_key(agent_id="a1", channel_type="feishu", channel_subject_id="ou_x")
    await registry.get_or_create_by_key(
        session_key=sk,
        agent_id="a1",
        user_id=1,
        channel_type="feishu",
    )
    await registry.get_or_create_by_key(
        session_key=sk,
        agent_id="a1",
        user_id=1,
        channel_type="feishu",
        channel_channel_id="ch-feishu-1",
    )
    row = registry.get_session(sk)
    assert row is not None
    assert row.channel_id == "ch-feishu-1"
