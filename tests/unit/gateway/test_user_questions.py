from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from harness_gateway.models import MessageEventType, TextContent

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.user_questions import PendingUserQuestionRepo
from octop.infra.gateway.hitl.coordinator import HitlChannelCoordinator, HitlStreamContext
from octop.infra.gateway.process.stream_project import StreamProjectionState, project_stream
from octop.infra.gateway.questions.coordinator import (
    UserQuestionCoordinator,
    parse_channel_answers,
    validate_answers,
)


def _repo(tmp_path: Path) -> PendingUserQuestionRepo:
    pool = SqlitePool(tmp_path / "octop.db")
    run_migrations(pool)
    return PendingUserQuestionRepo(pool)


def _record(tmp_path: Path):
    repo = _repo(tmp_path)
    coordinator = UserQuestionCoordinator(repo)
    record = coordinator.register_from_request(
        {
            "kind": "ask_user_question",
            "questions": [
                {
                    "id": "database",
                    "question": "Which database?",
                    "options": [{"label": "SQLite"}, {"label": "PostgreSQL"}],
                }
            ],
        },
        thread_id="thread-1",
        agent_id="agent-1",
        user_id=7,
        session_key="session-1",
        channel_type="wechat",
    )
    return repo, coordinator, record


def test_pending_question_survives_coordinator_recreation(tmp_path: Path) -> None:
    repo, _coordinator, record = _record(tmp_path)
    assert repo.claim(record.pending_id, agent_id="agent-1", user_id=7)

    recreated = UserQuestionCoordinator(repo)
    recovered = recreated.pending_payload(thread_id="thread-1", agent_id="agent-1", user_id=7)

    assert recovered is not None
    assert recovered["pending_id"] == record.pending_id
    assert recovered["questions"][0]["id"] == "database"


def test_pending_question_claim_is_exactly_once(tmp_path: Path) -> None:
    repo, _coordinator, record = _record(tmp_path)
    assert repo.claim(record.pending_id, agent_id="agent-1", user_id=7)
    assert not repo.claim(record.pending_id, agent_id="agent-1", user_id=7)


def test_channel_answer_accepts_option_number(tmp_path: Path) -> None:
    _repo_value, _coordinator, record = _record(tmp_path)
    assert parse_channel_answers(record, "2") == [{"id": "database", "selected": ["PostgreSQL"]}]


def test_dashboard_answer_rejects_unknown_option(tmp_path: Path) -> None:
    _repo_value, _coordinator, record = _record(tmp_path)
    try:
        validate_answers(record, [{"id": "database", "selected": ["MongoDB"]}])
    except ValueError as exc:
        assert "unknown option" in str(exc)
    else:  # pragma: no cover - assertion guard
        raise AssertionError("unknown option was accepted")


@pytest.mark.asyncio
async def test_channel_projection_persists_and_renders_question(tmp_path: Path) -> None:
    async def _stream(*_args: object, **_kwargs: object):
        yield {
            "type": "hitl_required",
            "request": {
                "kind": "ask_user_question",
                "questions": [
                    {
                        "id": "database",
                        "question": "Which database?",
                        "options": [{"label": "SQLite"}, {"label": "PostgreSQL"}],
                    }
                ],
            },
        }

    repo = _repo(tmp_path)
    questions = UserQuestionCoordinator(repo)
    agent_manager = MagicMock()
    agent_manager.stream = _stream
    projection = StreamProjectionState()

    events = [
        event
        async for event in project_stream(
            agent_manager,
            "agent-1",
            {"thread_id": "thread-1", "messages": []},
            projection_state=projection,
            hitl_coordinator=HitlChannelCoordinator(),
            hitl_ctx=HitlStreamContext(
                thread_id="thread-1",
                agent_id="agent-1",
                user_id=7,
                session_key="session-1",
                channel_type="wechat",
            ),
            question_coordinator=questions,
        )
    ]

    assert projection.hitl_paused is True
    assert len(events) == 1
    assert events[0].type == MessageEventType.MESSAGE
    content = events[0].content[0]
    assert isinstance(content, TextContent)
    assert "Which database?" in content.text
    assert "/answer" in content.text
    assert (
        questions.pending_payload(thread_id="thread-1", agent_id="agent-1", user_id=7) is not None
    )
