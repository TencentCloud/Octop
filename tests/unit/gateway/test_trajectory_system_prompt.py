"""Model system prompt rows stay on the turn that captured them."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.agents import AgentRepo
from octop.infra.db.repos.threads import ThreadRepo
from octop.infra.db.repos.trajectory_events import TrajectoryEventRepo
from octop.infra.db.repos.users import UserRepo
from octop.infra.gateway.process.processor import GlobalProcessor
from octop.infra.gateway.slash.dispatcher import SlashDispatcher
from octop.infra.history.trajectory.live import TrajectoryLiveBus
from octop.infra.history.trajectory.service import TrajectoryService
from octop.infra.history.trajectory.store import TrajectoryStore


def _processor(
    tmp_path: Path, prompts: dict[str, str]
) -> tuple[GlobalProcessor, TrajectoryService]:
    db = SqlitePool(tmp_path / "octop.db")
    run_migrations(db)
    user_id = UserRepo(db).create(username="traj-user", password_hash="h", role="user")
    AgentRepo(db).create(agent_id="A1", user_id=user_id, name="Agent")
    ThreadRepo(db).insert(
        thread_id="T1",
        agent_id="A1",
        user_id=user_id,
        channel_type="dashboard",
        session_key="sk-T1",
        last_active=0,
    )
    service = TrajectoryService(TrajectoryStore(TrajectoryEventRepo(db)), TrajectoryLiveBus())
    agent = MagicMock()
    agent.model_system_prompt.side_effect = lambda thread_id: prompts.get(thread_id)
    agent.clear_model_system_prompt.side_effect = lambda thread_id: prompts.pop(thread_id, None)
    agent_manager = MagicMock()
    agent_manager.get_agent.return_value = agent
    processor = GlobalProcessor(
        agent_manager=agent_manager,
        thread_registry=MagicMock(),
        audit_repo=MagicMock(),
        agent_repo=MagicMock(),
        user_repo=MagicMock(),
        connector_repo=MagicMock(),
        dispatcher=SlashDispatcher(),
        trajectory_service=service,
    )
    return processor, service


def test_leftover_prompt_stays_on_its_turn_and_does_not_split_the_reply(tmp_path: Path) -> None:
    prompts: dict[str, str] = {}
    processor, service = _processor(tmp_path, prompts)

    def observe(chunk: dict[str, object]) -> None:
        processor._observe_trajectory(
            agent_id="A1",
            thread_id="T1",
            chunk=chunk,
            enabled=True,
        )

    observe({"type": "user", "content": "hi"})
    processor._pending_system_prompt.add("T1")
    prompts["T1"] = "prompt one"
    # The next user message arrives before any model chunk flushed the capture.
    observe({"type": "user", "content": "next"})
    prompts["T1"] = "prompt two"
    processor._pending_system_prompt.add("T1")
    observe({"type": "token", "content": "ok"})
    observe({"type": "token", "content": "!"})
    service.finish_turn("T1")

    listed = service.list_events("T1", before_seq=None, limit=20, kinds=None)
    prompts_rows = [event for event in listed if event.payload.get("source") == "model_system"]
    users = [event for event in listed if event.kind == "user"]
    assistants = [event for event in listed if event.kind == "assistant"]
    assert [event.payload["content"] for event in prompts_rows] == ["prompt one", "prompt two"]
    assert prompts_rows[0].turn_id == users[0].turn_id
    assert prompts_rows[1].turn_id == users[1].turn_id
    assert prompts_rows[0].turn_id != prompts_rows[1].turn_id
    assert len(assistants) == 1
    assert assistants[0].payload["content"] == "ok!"
    assert assistants[0].turn_id == users[1].turn_id
