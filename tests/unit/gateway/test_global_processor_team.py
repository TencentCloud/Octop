"""tests/unit/test_global_processor_team.py"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from harness_agent.teams.inbox import InboxMessage
from harness_agent.teams.processor import ReplyEvent
from langchain_core.messages import AIMessage, HumanMessage

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.agents import AgentRepo
from octop.infra.db.repos.sessions import SessionRepo
from octop.infra.db.repos.thread_messages import ThreadMessageRepo
from octop.infra.db.repos.threads import ThreadRepo
from octop.infra.db.repos.users import UserRepo
from octop.infra.gateway.process.processor import GlobalProcessor
from octop.infra.gateway.slash.dispatcher import SlashDispatcher
from octop.infra.gateway.threads import ThreadRegistry


class _StubHarness:
    """Stand-in for a live harness agent handle."""

    def __init__(self) -> None:
        self.history: list[Any] = []
        self.history_calls: list[tuple[str, int]] = []

    async def aget_history(self, thread_id: str, limit: int) -> list[Any]:
        self.history_calls.append((thread_id, limit))
        return list(self.history)[-limit:]


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
    repos.thread_message_repo = ThreadMessageRepo(db)
    repos.channel_repo = MagicMock()
    repos.audit_repo = MagicMock()
    repos.agent_repo = AgentRepo(db)
    repos.user_repo = UserRepo(db)
    repos.connector_repo = MagicMock()

    harness = _StubHarness()
    agent_manager = MagicMock()
    agent_manager.get_row.side_effect = lambda aid: AgentRepo(db).get(aid)
    agent_manager.get_agent.return_value = harness

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
        thread_message_repo=repos.thread_message_repo,
    )
    return {
        "processor": processor,
        "gateway": gw,
        "parent_sk": parent_sk,
        "harness": harness,
        "projection": repos.thread_message_repo,
    }


def _reply_event(
    *,
    parent_sk: str,
    thread_id: str = "thr_parent",
    status: str = "done",
    reply_text: str | None = "final synthesized reply",
    error_text: str | None = None,
) -> ReplyEvent:
    return ReplyEvent(
        inbox_id="job-1",
        status=status,  # type: ignore[arg-type]
        source_agent_id="parent",
        source_thread_id=thread_id,
        target_agent_id="child",
        user_id=1,
        reply_text=reply_text,
        error_text=error_text,
        metadata={"session_key": parent_sk},
    )


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

    await processor.on_reply(_reply_event(parent_sk=str(parent_sk)))

    session = processor_env["gateway"].thread_registry.get_session(parent_sk)  # type: ignore[attr-defined]
    assert session is not None
    assert session.unread_count == 1


@pytest.mark.asyncio
async def test_on_reply_projects_background_turn_into_history(processor_env: dict) -> None:
    """The source agent's background turn must reach the visible history (#834).

    The source-side turn runs through ``TeamManager._call_agent``, which writes
    only the checkpoint. Pre-fix the Dashboard branch stopped at the unread
    badge, so ``thread_messages`` stayed empty and the Dashboard showed nothing
    even though the model itself had the transcript.
    """
    processor = processor_env["processor"]
    harness = processor_env["harness"]
    harness.history = [
        HumanMessage(content="[background task from agent child]", id="m-human"),
        AIMessage(content="final synthesized reply", id="m-ai"),
    ]

    await processor.on_reply(_reply_event(parent_sk=str(processor_env["parent_sk"])))

    rows, _has_more = processor_env["projection"].page("thr_parent", limit=10)
    assert [r.message_id for r in rows] == ["m-human", "m-ai"]
    assert [r.role for r in rows] == ["human", "ai"]
    assert harness.history_calls == [("thr_parent", 8)]


@pytest.mark.asyncio
async def test_on_reply_projection_is_idempotent(processor_env: dict) -> None:
    """Repeated callbacks must not duplicate the turn in the history."""
    processor = processor_env["processor"]
    processor_env["harness"].history = [
        HumanMessage(content="prompt", id="m-human"),
        AIMessage(content="reply", id="m-ai"),
    ]
    event = _reply_event(parent_sk=str(processor_env["parent_sk"]))

    await processor.on_reply(event)
    await processor.on_reply(event)

    rows, _has_more = processor_env["projection"].page("thr_parent", limit=10)
    assert [r.message_id for r in rows] == ["m-human", "m-ai"]


@pytest.mark.asyncio
async def test_on_reply_waits_for_pending_projection(processor_env: dict) -> None:
    """A legacy thread still backfilling must not be appended to out of band."""
    processor = processor_env["processor"]
    processor_env["harness"].history = [AIMessage(content="reply", id="m-ai")]
    processor_env["projection"].mark_projection("thr_parent", "pending")

    await processor.on_reply(_reply_event(parent_sk=str(processor_env["parent_sk"])))

    rows, _has_more = processor_env["projection"].page("thr_parent", limit=10)
    assert rows == []


@pytest.mark.asyncio
async def test_on_reply_pushes_reply_to_thread_subscribers(processor_env: dict) -> None:
    """A watching Dashboard must receive the reply text, not just a badge bump."""
    processor = processor_env["processor"]
    frames: list[dict[str, Any]] = []

    async def _send(frame: dict[str, Any]) -> None:
        frames.append(frame)

    hub = processor_env["gateway"].ws_hub  # type: ignore[attr-defined]
    hub.register("conn-1", _send, user_id=1)
    hub.subscribe("thr_parent", "conn-1")

    await processor.on_reply(_reply_event(parent_sk=str(processor_env["parent_sk"])))

    kinds = [f["type"] for f in frames]
    assert kinds[:2] == ["token", "done"]
    assert frames[0]["content"] == "final synthesized reply"
    assert frames[0]["thread_id"] == "thr_parent"
    # The owner also gets a toast, matching the cron/proactive delivery path.
    assert kinds[2:] == ["dashboard_push"]
    assert frames[2]["thread_id"] == "thr_parent"


@pytest.mark.asyncio
async def test_on_reply_delivers_to_dispatch_thread_after_session_moved(
    processor_env: dict,
) -> None:
    """A reply must land in the thread it was dispatched from (#834).

    While the background task ran the user opened another conversation, so the
    session now points at ``thr_new``. Routing by the session's current thread
    would file the reply into the wrong conversation.
    """
    processor = processor_env["processor"]
    gateway = processor_env["gateway"]
    parent_sk = str(processor_env["parent_sk"])
    registry = gateway.thread_registry  # type: ignore[attr-defined]
    registry.create_thread(
        agent_id="parent",
        user_id=1,
        channel_type="dashboard",
        session_key=parent_sk,
        thread_id="thr_new",
    )
    registry._sessions.set_thread(parent_sk, "thr_new")
    processor_env["harness"].history = [AIMessage(content="reply", id="m-ai")]

    await processor.on_reply(_reply_event(parent_sk=parent_sk))

    dispatched, _has_more = processor_env["projection"].page("thr_parent", limit=10)
    assert [r.message_id for r in dispatched] == ["m-ai"]
    later, _has_more = processor_env["projection"].page("thr_new", limit=10)
    assert later == []


@pytest.mark.asyncio
async def test_on_reply_falls_back_when_dispatch_thread_is_gone(processor_env: dict) -> None:
    """A deleted dispatch thread must not swallow the reply."""
    processor = processor_env["processor"]
    processor_env["harness"].history = [AIMessage(content="reply", id="m-ai")]

    await processor.on_reply(
        _reply_event(parent_sk=str(processor_env["parent_sk"]), thread_id="thr_deleted")
    )

    rows, _has_more = processor_env["projection"].page("thr_parent", limit=10)
    assert [r.message_id for r in rows] == ["m-ai"]


@pytest.mark.asyncio
async def test_on_reply_failure_text_is_delivered_too(processor_env: dict) -> None:
    """A failed background task still owes the user a visible explanation."""
    processor = processor_env["processor"]
    frames: list[dict[str, Any]] = []

    async def _send(frame: dict[str, Any]) -> None:
        frames.append(frame)

    hub = processor_env["gateway"].ws_hub  # type: ignore[attr-defined]
    hub.register("conn-1", _send, user_id=1)
    hub.subscribe("thr_parent", "conn-1")

    await processor.on_reply(
        _reply_event(
            parent_sk=str(processor_env["parent_sk"]),
            status="failed",
            reply_text=None,
            error_text="child agent crashed",
        )
    )

    assert frames[0]["content"] == "child agent crashed"


@pytest.mark.asyncio
async def test_prepare_peer_session_creates_callee_thread_without_rebind(
    processor_env: dict,
) -> None:
    from harness_agent.teams.util import PeerCall

    processor = processor_env["processor"]
    parent_sk = processor_env["parent_sk"]
    prepared = await processor.prepare_peer_session(
        PeerCall(
            from_agent_id="parent",
            to_agent_id="child",
            user_id=1,
            message="hello",
            source_thread_id="thr_parent",
            source_session_key=str(parent_sk),
        )
    )
    assert prepared is not None
    assert prepared.thread_id == "thr_parent~child"
    assert prepared.session_key == "child:dashboard:1:dm"
    registry = processor_env["gateway"].thread_registry
    row = registry.get_thread("thr_parent~child")
    assert row is not None
    assert row.agent_id == "child"
    assert registry.get_bound_thread_id(str(parent_sk)) == "thr_parent"


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
    processor._agent_manager.providers.is_model_ref_usable.return_value = True
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


def test_resolve_harness_model_drops_unusable_dashboard_override() -> None:
    """Stale composer/expert refs must not bypass catalog usability checks."""
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
    processor._agent_repo.get.return_value = MagicMock(default_model="p/deleted")
    processor._agent_manager.get_config.return_value = {}
    processor._agent_manager.providers.is_model_ref_usable.return_value = False
    processor._agent_manager.providers.resolve_explicit_default_model.return_value = None

    assert (
        processor._resolve_harness_model(
            "a1",
            "t1",
            {"model": "p/deleted"},
            needs_multimodal=False,
        )
        is None
    )
    processor._agent_manager.providers.resolve_model_for_multimodal_turn.assert_not_called()


def test_composer_model_precedes_sticky_and_legacy_slash_model() -> None:
    assert (
        GlobalProcessor._model_ref_from_meta(
            "p/slash",
            {"model": "p/composer"},
            "p/sticky",
        )
        == "p/composer"
    )
    assert GlobalProcessor._model_ref_from_meta("p/slash", None, "p/sticky") == "p/sticky"
