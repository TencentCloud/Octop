"""tests/unit/test_global_processor_team.py"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from harness_agent.teams.inbox import InboxMessage
from harness_agent.teams.processor import ReplyEvent

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.agents import AgentRepo
from octop.infra.db.repos.sessions import SessionRepo
from octop.infra.db.repos.threads import ThreadRepo
from octop.infra.db.repos.users import UserRepo
from octop.infra.gateway.process.processor import GlobalProcessor
from octop.infra.gateway.slash.dispatcher import SlashDispatcher
from octop.infra.gateway.threads import ThreadRegistry


@pytest.fixture
def processor_env(tmp_path: Path) -> dict[str, object]:
    db = SqlitePool(tmp_path / "octop.db")
    run_migrations(db)
    UserRepo(db).create(username="u", password_hash="h", role="user")
    AgentRepo(db).create(agent_id="parent", user_id=1, name="Parent")
    AgentRepo(db).create(agent_id="child", user_id=1, name="Researcher")

    repos = MagicMock()
    repos.session_repo = SessionRepo(db)
    repos.thread_repo = ThreadRepo(db)
    repos.channel_repo = MagicMock()
    repos.audit_repo = MagicMock()
    repos.agent_repo = AgentRepo(db)
    repos.user_repo = UserRepo(db)
    repos.connector_repo = MagicMock()

    agent_manager = MagicMock()
    agent_manager.get_row.side_effect = lambda aid: AgentRepo(db).get(aid)

    from octop.infra.gateway.gateway import Gateway

    gw = Gateway(agent_manager=agent_manager, repos=repos)
    gw._channel_manager = MagicMock()

    parent_sk = ThreadRegistry.dashboard_key(agent_id="parent", user_id=1)
    gw.thread_registry._threads.insert(
        thread_id="thr_parent",
        agent_id="parent",
        user_id=1,
        channel_type="dashboard",
        session_key=parent_sk,
    )
    gw.thread_registry._sessions.upsert(
        session_key=parent_sk,
        agent_id="parent",
        user_id=1,
        channel_type="dashboard",
        chat_type="dm",
        thread_id="thr_parent",
    )

    processor = GlobalProcessor(
        agent_manager=agent_manager,
        thread_registry=gw.thread_registry,
        audit_repo=repos.audit_repo,
        agent_repo=repos.agent_repo,
        user_repo=repos.user_repo,
        connector_repo=repos.connector_repo,
        dispatcher=SlashDispatcher(),
        gateway=gw,
    )
    return {"processor": processor, "gateway": gw, "parent_sk": parent_sk}


def test_compose_followup_uses_peer_display_name(processor_env: dict) -> None:
    processor = processor_env["processor"]
    msg = InboxMessage(
        id="job-1",
        target_agent_id="child",
        source_agent_id="parent",
        source_thread_id="thr_parent",
        message="survey market",
        user_id=1,
        original_user_prompt="market size?",
    )
    text = processor.compose_followup(msg, result_text="findings", error_text=None)
    assert "Researcher" in text
    assert "findings" in text


@pytest.mark.asyncio
async def test_on_reply_increments_unread_on_dashboard(processor_env: dict) -> None:
    processor = processor_env["processor"]
    parent_sk = processor_env["parent_sk"]

    await processor.on_reply(
        ReplyEvent(
            inbox_id="job-1",
            status="done",
            source_agent_id="parent",
            source_thread_id="thr_parent",
            target_agent_id="child",
            user_id=1,
            reply_text="final synthesized reply",
            metadata={"session_key": parent_sk},
        )
    )

    session = processor_env["gateway"].thread_registry.get_session(parent_sk)  # type: ignore[attr-defined]
    assert session is not None
    assert session.unread_count == 1


def test_resolve_harness_model_auto_expert_omits_model() -> None:
    processor = GlobalProcessor(
        agent_manager=MagicMock(),
        thread_registry=MagicMock(),
        audit_repo=MagicMock(),
        agent_repo=MagicMock(),
        user_repo=MagicMock(),
        connector_repo=MagicMock(),
        dispatcher=MagicMock(),
        usage_repo=MagicMock(),
        gateway=MagicMock(),
    )
    processor._agent_manager.get_thread_model.return_value = None
    processor._agent_repo.get.return_value = MagicMock(default_model=None)
    processor._agent_manager.get_config.return_value = {}
    processor._agent_manager.providers.resolve_explicit_default_model.return_value = None

    assert (
        processor._resolve_harness_model(
            "a1",
            "t1",
            None,
            needs_multimodal=True,
        )
        is None
    )


def test_resolve_harness_model_uses_agent_default_and_upgrades_vision() -> None:
    processor = GlobalProcessor(
        agent_manager=MagicMock(),
        thread_registry=MagicMock(),
        audit_repo=MagicMock(),
        agent_repo=MagicMock(),
        user_repo=MagicMock(),
        connector_repo=MagicMock(),
        dispatcher=MagicMock(),
        usage_repo=MagicMock(),
        gateway=MagicMock(),
    )
    processor._agent_manager.get_thread_model.return_value = None
    processor._agent_repo.get.return_value = MagicMock(default_model="p/text-only")
    processor._agent_manager.get_config.return_value = {}
    processor._agent_manager.providers.resolve_explicit_default_model.return_value = "p/text-only"
    processor._agent_manager.providers.resolve_model_for_multimodal_turn.return_value = "p/vision"

    resolved = processor._resolve_harness_model(
        "a1",
        "t1",
        None,
        needs_multimodal=True,
    )
    assert resolved == "p/vision"
    processor._agent_manager.providers.resolve_model_for_multimodal_turn.assert_called_once_with(
        "p/text-only",
        needs_multimodal=True,
    )


def test_resolve_harness_model_dashboard_override_wins() -> None:
    processor = GlobalProcessor(
        agent_manager=MagicMock(),
        thread_registry=MagicMock(),
        audit_repo=MagicMock(),
        agent_repo=MagicMock(),
        user_repo=MagicMock(),
        connector_repo=MagicMock(),
        dispatcher=MagicMock(),
        usage_repo=MagicMock(),
        gateway=MagicMock(),
    )
    processor._agent_manager.get_thread_model.return_value = None
    processor._agent_repo.get.return_value = MagicMock(default_model="p/default")
    processor._agent_manager.providers.resolve_model_for_multimodal_turn.return_value = "p/picked"

    resolved = processor._resolve_harness_model(
        "a1",
        "t1",
        {"model": "p/picked"},
        needs_multimodal=False,
    )
    assert resolved == "p/picked"
    processor._agent_manager.providers.resolve_model_for_multimodal_turn.assert_called_once_with(
        "p/picked",
        needs_multimodal=False,
    )
