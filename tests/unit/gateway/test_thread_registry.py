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
    assert len(registry.list_threads(agent_id="a1", user_id=1)) == 2
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
    assert row.channel_metadata is not None
    assert row.channel_metadata["channel_id"] == "ch-feishu-1"


@pytest.mark.asyncio
async def test_inbound_rebinds_session_to_replacement_channel(registry: ThreadRegistry) -> None:
    """A deleted channel's id must not stay bound, or proactive push breaks."""
    sk = ThreadRegistry.make_key(agent_id="a1", channel_type="feishu", channel_subject_id="ou_x")
    await registry.get_or_create_by_key(
        session_key=sk,
        agent_id="a1",
        user_id=1,
        channel_type="feishu",
        channel_channel_id="ch-old",
    )
    await registry.get_or_create_by_key(
        session_key=sk,
        agent_id="a1",
        user_id=1,
        channel_type="feishu",
        channel_channel_id="ch-new",
    )
    row = registry.get_session(sk)
    assert row is not None
    assert row.channel_id == "ch-new"
    assert row.channel_metadata is not None
    assert row.channel_metadata["channel_id"] == "ch-new"


@pytest.mark.asyncio
async def test_get_or_create_rebinds_replacement_channel(registry: ThreadRegistry) -> None:
    await registry.get_or_create(
        agent_id="a1",
        user_id=1,
        channel_type="feishu",
        channel_subject_id="ou_x",
        channel_id="ch-old",
    )
    await registry.get_or_create(
        agent_id="a1",
        user_id=1,
        channel_type="feishu",
        channel_subject_id="ou_x",
        channel_id="ch-new",
    )
    sk = ThreadRegistry.make_key(agent_id="a1", channel_type="feishu", channel_subject_id="ou_x")
    row = registry.get_session(sk)
    assert row is not None
    assert row.channel_id == "ch-new"
    assert row.channel_metadata is not None
    assert row.channel_metadata["channel_id"] == "ch-new"


@pytest.mark.asyncio
async def test_same_channel_id_does_not_rewrite_session(registry: ThreadRegistry) -> None:
    sk = ThreadRegistry.make_key(agent_id="a1", channel_type="feishu", channel_subject_id="ou_x")
    await registry.get_or_create_by_key(
        session_key=sk,
        agent_id="a1",
        user_id=1,
        channel_type="feishu",
        channel_channel_id="ch-same",
    )
    before = registry.get_session(sk)
    assert before is not None
    await registry.get_or_create_by_key(
        session_key=sk,
        agent_id="a1",
        user_id=1,
        channel_type="feishu",
        channel_channel_id="ch-same",
    )
    after = registry.get_session(sk)
    assert after is not None
    assert after.updated_at == before.updated_at
    assert after.channel_id == "ch-same"


@pytest.mark.asyncio
async def test_metadata_refresh_keeps_bound_channel_id(registry: ThreadRegistry) -> None:
    sk = ThreadRegistry.make_key(agent_id="a1", channel_type="feishu", channel_subject_id="ou_x")
    await registry.get_or_create_by_key(
        session_key=sk,
        agent_id="a1",
        user_id=1,
        channel_type="feishu",
        channel_channel_id="ch-keep",
    )
    await registry.get_or_create_by_key(
        session_key=sk,
        agent_id="a1",
        user_id=1,
        channel_type="feishu",
        channel_metadata={"chat_id": "oc_1"},
    )
    row = registry.get_session(sk)
    assert row is not None
    assert row.channel_id == "ch-keep"
    assert row.channel_metadata is not None
    assert row.channel_metadata["channel_id"] == "ch-keep"
    assert row.channel_metadata["chat_id"] == "oc_1"


@pytest.mark.asyncio
async def test_delete_thread_clears_session_binding(registry: ThreadRegistry) -> None:
    """Deleting a thread must unbind the session that points at it (#833).

    ``sessions.thread_id`` has no foreign key onto ``threads``, so without an
    explicit cleanup the session outlives its thread and keeps resolving to a
    dead id — replies still stream back but nothing lands in ``thread_messages``.
    """
    sk = ThreadRegistry.make_key(agent_id="a1", channel_type="feishu", channel_subject_id="ou_x")
    tid = await registry.get_or_create_by_key(
        session_key=sk, agent_id="a1", user_id=1, channel_type="feishu"
    )
    assert registry.get_bound_thread_id(sk) == tid

    registry.delete_thread(tid)

    assert registry.get_thread(tid) is None
    assert registry.get_session(sk) is None
    assert registry.get_bound_thread_id(sk) is None


@pytest.mark.asyncio
async def test_delete_thread_leaves_other_sessions_alone(registry: ThreadRegistry) -> None:
    """Only sessions bound to the removed thread may be dropped."""
    sk_a = ThreadRegistry.make_key(agent_id="a1", channel_type="feishu", channel_subject_id="ou_a")
    sk_b = ThreadRegistry.make_key(agent_id="a1", channel_type="feishu", channel_subject_id="ou_b")
    tid_a = await registry.get_or_create_by_key(
        session_key=sk_a, agent_id="a1", user_id=1, channel_type="feishu"
    )
    tid_b = await registry.get_or_create_by_key(
        session_key=sk_b, agent_id="a1", user_id=1, channel_type="feishu"
    )

    registry.delete_thread(tid_a)

    assert registry.get_session(sk_a) is None
    assert registry.get_bound_thread_id(sk_b) == tid_b


@pytest.mark.asyncio
async def test_dangling_session_is_treated_as_unbound(registry: ThreadRegistry) -> None:
    """A session whose thread vanished must not hand out a dead id (#833).

    Covers rows left behind by a pre-fix database, where the thread is gone but
    the session row survives.
    """
    sk = ThreadRegistry.make_key(agent_id="a1", channel_type="feishu", channel_subject_id="ou_x")
    tid = await registry.get_or_create_by_key(
        session_key=sk, agent_id="a1", user_id=1, channel_type="feishu"
    )
    # Simulate the pre-fix state: thread gone, session still pointing at it.
    registry._threads.delete(tid)
    assert registry.get_session(sk) is not None

    assert registry.get_bound_thread_id(sk) is None


@pytest.mark.asyncio
async def test_get_or_create_by_key_recovers_from_dangling_session(
    registry: ThreadRegistry,
) -> None:
    """A dangling binding must fall through to a fresh thread, not be returned."""
    sk = ThreadRegistry.make_key(agent_id="a1", channel_type="feishu", channel_subject_id="ou_x")
    dead = await registry.get_or_create_by_key(
        session_key=sk, agent_id="a1", user_id=1, channel_type="feishu"
    )
    registry._threads.delete(dead)

    fresh = await registry.get_or_create_by_key(
        session_key=sk, agent_id="a1", user_id=1, channel_type="feishu"
    )

    assert fresh != dead
    assert registry.get_thread(fresh) is not None
    assert registry.get_bound_thread_id(sk) == fresh


@pytest.mark.asyncio
async def test_get_or_create_recovers_from_dangling_session(registry: ThreadRegistry) -> None:
    dead = await registry.get_or_create(
        agent_id="a1",
        user_id=1,
        channel_type="feishu",
        channel_subject_id="ou_x",
    )
    registry._threads.delete(dead)

    fresh = await registry.get_or_create(
        agent_id="a1",
        user_id=1,
        channel_type="feishu",
        channel_subject_id="ou_x",
    )

    assert fresh != dead
    assert registry.get_thread(fresh) is not None


@pytest.mark.asyncio
async def test_dangling_session_still_rejects_agent_mismatch(registry: ThreadRegistry) -> None:
    """The dangling check must not weaken the cross-agent guard."""
    sk = ThreadRegistry.make_key(agent_id="a1", channel_type="feishu", channel_subject_id="ou_x")
    tid = await registry.get_or_create_by_key(
        session_key=sk, agent_id="a1", user_id=1, channel_type="feishu"
    )
    registry._threads.delete(tid)

    with pytest.raises(ValueError, match="belongs to agent"):
        await registry.get_or_create_by_key(
            session_key=sk, agent_id="a2", user_id=1, channel_type="feishu"
        )


def test_peer_session_key_rewrites_agent_segment() -> None:
    src = ThreadRegistry.make_key(
        agent_id="a1",
        channel_type="dashboard",
        channel_subject_id="7",
    )
    out = ThreadRegistry.peer_session_key(src, "a2")
    assert out == "a2:dashboard:7:dm"
    assert ThreadRegistry.peer_session_key("not-a-key", "a2") is None


@pytest.mark.asyncio
async def test_ensure_thread_is_stable_and_does_not_rebind(registry: ThreadRegistry) -> None:
    bound = await registry.get_or_create(
        agent_id="a2",
        user_id=1,
        channel_type="dashboard",
        channel_subject_id="1",
    )
    sk = ThreadRegistry.make_key(agent_id="a2", channel_type="dashboard", channel_subject_id="1")
    derived = "thr_src~a2"
    assert (
        registry.ensure_thread(
            thread_id=derived,
            agent_id="a2",
            user_id=1,
            channel_type="dashboard",
            session_key=sk,
        )
        == derived
    )
    assert (
        registry.ensure_thread(
            thread_id=derived,
            agent_id="a2",
            user_id=1,
            channel_type="dashboard",
            session_key=sk,
        )
        == derived
    )
    assert registry.get_bound_thread_id(sk) == bound
    row = registry.get_thread(derived)
    assert row is not None
    assert row.agent_id == "a2"
    ids = {t.thread_id for t in registry.list_threads(agent_id="a2", user_id=1)}
    assert derived in ids
    assert bound in ids
