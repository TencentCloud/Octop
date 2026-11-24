"""Unit tests for ProactiveCareService.

Coverage:
- successful push flow with episodes, LLM success, push success, and dedup record writes
- skip push when episodes are empty
- skip push and dedup writes when the LLM call fails
- skip dedup writes when push fails
- truncate long care messages to 200 characters
- use the default prompt when SOUL.md cannot be read without interrupting the flow
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.agents import AgentRepo
from octop.infra.db.repos.care_push import CarePushRepo
from octop.infra.db.repos.sessions import SessionRepo, SessionRow
from octop.infra.db.repos.thread_messages import ThreadMessageRepo
from octop.infra.db.repos.threads import ThreadRepo
from octop.infra.db.repos.users import UserRepo
from octop.infra.gateway.gateway import Gateway
from octop.infra.gateway.threads import ThreadRegistry
from octop.infra.proactive.service import ProactiveCareService
from octop.infra.utils.ulid import new_ulid

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db(tmp_path: Path) -> SqlitePool:
    pool = SqlitePool(tmp_path / "test.db")
    run_migrations(pool)
    return pool


@pytest.fixture
def agent_id(db: SqlitePool) -> str:
    uid = UserRepo(db).create(username="alice", password_hash="h", role="admin")
    aid = new_ulid()
    AgentRepo(db).create(agent_id=aid, user_id=uid, name="bot")
    return aid


@pytest.fixture
def care_push_repo(db: SqlitePool) -> CarePushRepo:
    return CarePushRepo(db)


def _make_episode(
    ep_id: str,
    *,
    emotion: str = "sad",
    intensity: int = 4,
    people: list[str] | None = None,
    days_ago: float = 1.0,
) -> MagicMock:
    now = datetime.now(UTC)
    ep = MagicMock()
    ep.id = ep_id
    ep.emotion = emotion
    ep.intensity = intensity
    ep.people = people or ["老婆"]
    ep.topics = ["家庭"]
    ep.occurred_at = now - timedelta(days=days_ago)
    ep.summary = f"用户发生了 {ep_id} 事件"
    ep.verbatim_quote = f"原话 {ep_id}"
    return ep


def _make_agent(
    episodes: list,
    llm_response: str = "最近辛苦了，注意休息！",
    soul_md: str = "",
    llm_raises: Exception | None = None,
) -> MagicMock:
    """Create a mock HarnessAgent."""
    agent = MagicMock()
    # Mock memory.
    memory = MagicMock()
    memory.list_episodes.return_value = episodes
    agent.memory = memory
    # Mock workspace.
    workspace = MagicMock()
    workspace.aread_text = AsyncMock(return_value=soul_md)
    agent.workspace = workspace
    # Mock auxiliary LLM.
    llm = AsyncMock()
    if llm_raises:
        llm.ainvoke = AsyncMock(side_effect=llm_raises)
    else:
        llm_msg = MagicMock()
        llm_msg.content = llm_response
        llm.ainvoke = AsyncMock(return_value=llm_msg)
    model_factory = MagicMock()
    model_factory.get = MagicMock(return_value=llm)
    agent.model_factory = model_factory
    # Mock config.
    config = MagicMock()
    config.memory_aux_light_model = "openai/gpt-4o-mini"
    config.default_model = "openai/gpt-4o-mini"
    config.locale = "zh-CN"
    agent.config = config

    # Mock checkpoint append (returns messages as-is).
    async def _aappend(_thread_id: str, messages):
        return list(messages)

    agent.aappend_messages = AsyncMock(side_effect=_aappend)
    return agent


def _make_gateway(
    push_success: bool = True,
    *,
    channel_type: str = "wxwork",
    thread_id: str = "thr_default",
) -> MagicMock:
    """Create a mock Gateway wired for ProactiveCareService._deliver."""
    gateway = MagicMock()
    gateway.thread_registry = MagicMock()
    gateway.thread_registry.latest_active_thread.return_value = None

    async def _run_in_session(_agent_id: str, _session_key: str, operation):
        await operation()

    def _require_session(aid: str, sk: str) -> SessionRow:
        return SessionRow(
            id=1,
            session_key=sk,
            agent_id=aid,
            user_id=1,
            channel_type=channel_type,
            chat_type="dm",
            thread_id=thread_id,
            updated_at=0,
            channel_subject_id="user123",
            channel_chat_type="dm",
            channel_id="ch-1" if channel_type != "dashboard" else None,
        )

    gateway.run_in_session = AsyncMock(side_effect=_run_in_session)
    gateway.require_session = MagicMock(side_effect=_require_session)
    gateway.notify_dashboard_push = AsyncMock(return_value=None)
    if push_success:
        gateway.push_session_text = AsyncMock(return_value=None)
    else:
        gateway.push_session_text = AsyncMock(side_effect=RuntimeError("推送失败：网络错误"))
    return gateway


def _make_agent_manager(agent: MagicMock) -> MagicMock:
    mgr = MagicMock()
    mgr.get_agent.return_value = agent
    return mgr


def _make_service(
    agent: MagicMock,
    care_push_repo: CarePushRepo,
    push_success: bool = True,
) -> ProactiveCareService:
    gateway = _make_gateway(push_success=push_success)
    agent_manager = _make_agent_manager(agent)
    return ProactiveCareService(
        gateway=gateway,
        care_push_repo=care_push_repo,
        agent_manager=agent_manager,
    )


# ---------------------------------------------------------------------------
# Test: successful push flow
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_service_run_success(agent_id: str, care_push_repo: CarePushRepo):
    """Successful flow: episodes exist, LLM succeeds, push succeeds, dedup records are written."""
    episodes = [_make_episode("ep1"), _make_episode("ep2", people=["老板"])]
    agent = _make_agent(episodes, llm_response="最近辛苦了，注意休息！")
    service = _make_service(agent, care_push_repo, push_success=True)

    await service.run(agent_id, f"{agent_id}:wxwork:user123:dm")

    # Verify dedup records were written.
    pushed = care_push_repo.list_pushed_episode_ids(agent_id)
    assert len(pushed) > 0
    agent.model_factory.get.assert_called_once()


# ---------------------------------------------------------------------------
# Test: skip push when episodes are empty
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_service_run_no_episodes(agent_id: str, care_push_repo: CarePushRepo):
    """Should skip push, LLM calls, and dedup writes when there are no episodes."""
    agent = _make_agent([])
    service = _make_service(agent, care_push_repo)

    await service.run(agent_id, f"{agent_id}:wxwork:user123:dm")

    # Verify the LLM was not called.
    agent.get_aux_llm.assert_not_called()
    # Verify no dedup records were written.
    pushed = care_push_repo.list_pushed_episode_ids(agent_id)
    assert len(pushed) == 0


# ---------------------------------------------------------------------------
# Test: LLM call failure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_service_run_llm_failure(agent_id: str, care_push_repo: CarePushRepo):
    """Should not push, write dedup records, or raise when the LLM call fails."""
    episodes = [_make_episode("ep1")]
    agent = _make_agent(episodes, llm_raises=RuntimeError("LLM 服务不可用"))
    service = _make_service(agent, care_push_repo)

    # Should not raise.
    await service.run(agent_id, f"{agent_id}:wxwork:user123:dm")

    # Verify no dedup records were written.
    pushed = care_push_repo.list_pushed_episode_ids(agent_id)
    assert len(pushed) == 0


# ---------------------------------------------------------------------------
# Test: push failure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_service_run_push_failure(agent_id: str, care_push_repo: CarePushRepo):
    """Should not write dedup records or raise when push fails."""
    episodes = [_make_episode("ep1")]
    agent = _make_agent(episodes)
    service = _make_service(agent, care_push_repo, push_success=False)

    # Should not raise.
    await service.run(agent_id, f"{agent_id}:wxwork:user123:dm")

    # Verify no dedup records were written.
    pushed = care_push_repo.list_pushed_episode_ids(agent_id)
    assert len(pushed) == 0


# ---------------------------------------------------------------------------
# Test: long care-message truncation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_service_run_truncates_long_text(agent_id: str, care_push_repo: CarePushRepo):
    """Care messages longer than 200 characters should be truncated."""
    long_text = "关心" * 200  # 400 CJK characters.
    episodes = [_make_episode("ep1")]
    agent = _make_agent(episodes, llm_response=long_text)

    # Capture the actual pushed text.
    pushed_texts: list[str] = []

    async def _capture_push(_session, text: str, **kwargs):
        pushed_texts.append(text)

    gateway = _make_gateway(push_success=True)
    gateway.push_session_text = AsyncMock(side_effect=_capture_push)
    agent_manager = _make_agent_manager(agent)
    service = ProactiveCareService(
        gateway=gateway,
        care_push_repo=care_push_repo,
        agent_manager=agent_manager,
    )

    await service.run(agent_id, f"{agent_id}:wxwork:user123:dm")

    assert len(pushed_texts) == 1
    assert len(pushed_texts[0]) <= 200


# ---------------------------------------------------------------------------
# Test: use the default prompt when SOUL.md cannot be read
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_service_run_soul_md_failure_uses_default_prompt(
    agent_id: str, care_push_repo: CarePushRepo
):
    """Should use the default prompt and continue when SOUL.md cannot be read."""
    episodes = [_make_episode("ep1")]
    agent = _make_agent(episodes)
    # Make workspace.aread_text raise.
    agent.workspace.aread_text = AsyncMock(side_effect=FileNotFoundError("SOUL.md not found"))

    service = _make_service(agent, care_push_repo, push_success=True)

    # Should not raise, and push should complete normally.
    await service.run(agent_id, f"{agent_id}:wxwork:user123:dm")

    # Verify dedup records were written, which means push succeeded.
    pushed = care_push_repo.list_pushed_episode_ids(agent_id)
    assert len(pushed) > 0


# ---------------------------------------------------------------------------
# Test: skip when memory is disabled
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_service_run_no_memory(agent_id: str, care_push_repo: CarePushRepo):
    """Should skip push without raising when memory is disabled."""
    agent = MagicMock()
    agent.memory = None  # Memory is disabled.
    agent_manager = _make_agent_manager(agent)
    gateway = _make_gateway()
    service = ProactiveCareService(
        gateway=gateway,
        care_push_repo=care_push_repo,
        agent_manager=agent_manager,
    )

    # Should not raise.
    await service.run(agent_id, f"{agent_id}:wxwork:user123:dm")

    # Verify no dedup records were written.
    pushed = care_push_repo.list_pushed_episode_ids(agent_id)
    assert len(pushed) == 0


# ---------------------------------------------------------------------------
# Integration tests: persistence to checkpoint, thread_messages, and records
# ---------------------------------------------------------------------------


def _build_real_gateway(db: SqlitePool, agent: MagicMock) -> tuple[Gateway, MagicMock]:
    agent_manager = _make_agent_manager(agent)
    agent_manager.get_row.return_value = MagicMock(default_model=None)
    agent_manager.get_row.return_value.name = "bot"

    repos = MagicMock()
    repos.session_repo = SessionRepo(db)
    repos.thread_repo = ThreadRepo(db)
    repos.thread_message_repo = ThreadMessageRepo(db)
    repos.user_repo = UserRepo(db)

    gateway = Gateway(agent_manager=agent_manager, repos=repos)
    gateway._channel_manager = MagicMock()
    gateway._channel_manager.push_text = AsyncMock(return_value=None)
    gateway._channel_manager.get_channel = MagicMock(return_value=None)

    async def _run_in_session(_channel_id: str, _session_key: str, operation):
        await operation()

    gateway._channel_manager.run_in_session = _run_in_session
    return gateway, agent_manager


@pytest.mark.asyncio
async def test_dashboard_care_persists_ai_message_and_records_coordinates(
    db: SqlitePool,
    agent_id: str,
    care_push_repo: CarePushRepo,
) -> None:
    """Issue #3064: dashboard care writes a single AIMessage to checkpoint + thread_messages."""
    care_text = "昨天和经理聊得怎么样？记得好好休息。"
    episodes = [_make_episode("ep_dash")]
    checkpoint: list[tuple[str, str, str, str]] = []
    agent = _make_agent(episodes, llm_response=care_text)

    async def _aappend(tid: str, messages):
        checkpoint.extend((tid, m.type, m.id, m.content) for m in messages)
        return list(messages)

    agent.aappend_messages = AsyncMock(side_effect=_aappend)
    gateway, agent_manager = _build_real_gateway(db, agent)

    session_key = ThreadRegistry.dashboard_key(agent_id=agent_id, user_id=1)
    ThreadRepo(db).insert(
        thread_id="thr_dash_active",
        agent_id=agent_id,
        user_id=1,
        channel_type=ThreadRegistry.CHANNEL_DASHBOARD,
        session_key=session_key,
        last_active=1_700_000_000,
    )
    # Also create a blank bound thread to ensure _bind_latest_thread prefers the active thread.
    ThreadRepo(db).insert(
        thread_id="thr_dash_blank",
        agent_id=agent_id,
        user_id=1,
        channel_type=ThreadRegistry.CHANNEL_DASHBOARD,
        session_key=session_key,
        last_active=0,
    )
    SessionRepo(db).upsert(
        session_key=session_key,
        agent_id=agent_id,
        user_id=1,
        channel_type=ThreadRegistry.CHANNEL_DASHBOARD,
        chat_type=ThreadRegistry.CHAT_TYPE_DM,
        thread_id="thr_dash_blank",
    )

    msg_repo = ThreadMessageRepo(db)
    service = ProactiveCareService(
        gateway=gateway,
        care_push_repo=care_push_repo,
        agent_manager=agent_manager,
        thread_message_repo=msg_repo,
    )
    await service.run(agent_id, session_key)

    # Persisted to checkpoint as a single AIMessage on the active thread.
    assert len(checkpoint) == 1
    tid, role, mid, content = checkpoint[0]
    assert tid == "thr_dash_active"
    assert role == "ai"
    assert mid.startswith("care:") and mid.endswith(":assistant")
    assert content == care_text

    # Persisted to thread_messages projection so dashboard history shows it.
    rows, _ = msg_repo.page("thr_dash_active", limit=10)
    assert len(rows) == 1
    assert rows[0].role == "ai"
    assert rows[0].message_id == mid
    assert care_text in rows[0].message_json

    # Unread count bumped and care_push_records stores thread/message/text/status.
    session = SessionRepo(db).get(session_key)
    assert session is not None
    assert session.thread_id == "thr_dash_active"
    assert session.unread_count == 1

    records = care_push_repo.list_recent(agent_id)
    assert len(records) == 1
    assert records[0].thread_id == "thr_dash_active"
    assert records[0].message_id == mid
    assert records[0].care_text == care_text
    assert records[0].status == "sent"


@pytest.mark.asyncio
async def test_im_care_persists_ai_message_for_reply_context(
    db: SqlitePool,
    agent_id: str,
    care_push_repo: CarePushRepo,
) -> None:
    """IM care also persists a single AIMessage so the agent remembers what it asked."""
    care_text = "这周加班辛苦了，今天早点歇着吧。"
    checkpoint: list[tuple[str, str, str, str]] = []
    agent = _make_agent([_make_episode("ep_im")], llm_response=care_text)

    async def _aappend(tid: str, messages):
        checkpoint.extend((tid, m.type, m.id, m.content) for m in messages)
        return list(messages)

    agent.aappend_messages = AsyncMock(side_effect=_aappend)
    gateway, agent_manager = _build_real_gateway(db, agent)
    gateway.notify_dashboard_push = AsyncMock(return_value=None)

    session_key = ThreadRegistry.make_key(
        agent_id=agent_id,
        channel_type="weixin",
        channel_subject_id="wx_u1",
        channel_chat_type="dm",
    )
    ThreadRepo(db).insert(
        thread_id="thr_im",
        agent_id=agent_id,
        user_id=1,
        channel_type="weixin",
        session_key=session_key,
        last_active=1_700_000_000,
    )
    SessionRepo(db).upsert(
        session_key=session_key,
        agent_id=agent_id,
        user_id=1,
        channel_type="weixin",
        chat_type="dm",
        thread_id="thr_im",
        channel_id="ch_wx_1",
    )

    msg_repo = ThreadMessageRepo(db)
    service = ProactiveCareService(
        gateway=gateway,
        care_push_repo=care_push_repo,
        agent_manager=agent_manager,
        thread_message_repo=msg_repo,
    )
    await service.run(agent_id, session_key)

    assert len(checkpoint) == 1
    assert checkpoint[0][0] == "thr_im"
    assert checkpoint[0][1] == "ai"
    rows, _ = msg_repo.page("thr_im", limit=10)
    assert len(rows) == 1
    assert rows[0].role == "ai"
    gateway.notify_dashboard_push.assert_not_awaited()


@pytest.mark.asyncio
async def test_locked_can_send_false_discards_without_persisting(
    db: SqlitePool,
    agent_id: str,
    care_push_repo: CarePushRepo,
) -> None:
    """A second can_send() check inside the session lock prevents race-condition pushes."""
    agent = _make_agent([_make_episode("ep_race")], llm_response="你好呀")
    gateway, agent_manager = _build_real_gateway(db, agent)
    session_key = ThreadRegistry.dashboard_key(agent_id=agent_id, user_id=1)
    ThreadRepo(db).insert(
        thread_id="thr_race",
        agent_id=agent_id,
        user_id=1,
        channel_type=ThreadRegistry.CHANNEL_DASHBOARD,
        session_key=session_key,
        last_active=1_700_000_000,
    )
    SessionRepo(db).upsert(
        session_key=session_key,
        agent_id=agent_id,
        user_id=1,
        channel_type=ThreadRegistry.CHANNEL_DASHBOARD,
        chat_type="dm",
        thread_id="thr_race",
    )

    # First check (outside lock) returns True; second check (inside lock) returns False.
    checks = iter([True, False])
    service = ProactiveCareService(
        gateway=gateway,
        care_push_repo=care_push_repo,
        agent_manager=agent_manager,
        thread_message_repo=ThreadMessageRepo(db),
    )
    await service.run(agent_id, session_key, can_send=lambda: next(checks))

    agent.aappend_messages.assert_not_awaited()
    gateway._channel_manager.push_text.assert_not_awaited()
    assert care_push_repo.list_recent(agent_id) == []
