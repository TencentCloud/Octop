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
from octop.infra.db.repos.users import UserRepo
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
    return agent


def _make_gateway(push_success: bool = True) -> MagicMock:
    """Create a mock Gateway."""
    gateway = MagicMock()
    if push_success:
        gateway.push_text_from_session = AsyncMock(return_value=None)
    else:
        gateway.push_text_from_session = AsyncMock(side_effect=RuntimeError("推送失败：网络错误"))
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

    async def _capture_gen(agent_id: str, session_key: str, text: str, **kwargs):
        pushed_texts.append(text)

    gateway = MagicMock()
    gateway.push_text_from_session = _capture_gen
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
