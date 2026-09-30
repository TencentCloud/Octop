"""Auto-tag hook: schedule tagging on the thread's first completed turn.

The trigger is ``last_active == 0`` (no turn completed yet), not a title
None→set transition — the dashboard pre-writes the title via PATCH before the
first turn finishes, so the title is always set by hook time.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.agents import AgentRepo
from octop.infra.db.repos.sessions import SessionRepo
from octop.infra.db.repos.threads import ThreadRepo
from octop.infra.db.repos.users import UserRepo
from octop.infra.gateway.process.processor import GlobalProcessor
from octop.infra.gateway.slash.dispatcher import SlashDispatcher
from octop.infra.gateway.threads import ThreadRegistry


class _RecordingTagger:
    """Stand-in for AutoTagger; records calls, optionally raising."""

    def __init__(self, exc: BaseException | None = None):
        self.calls: list[dict[str, Any]] = []
        self._exc = exc

    async def maybe_tag_thread(self, **kwargs: Any) -> None:
        self.calls.append(kwargs)
        if self._exc is not None:
            raise self._exc


@pytest.fixture
def registry(tmp_path: Path) -> tuple[ThreadRegistry, ThreadRepo]:
    db = SqlitePool(tmp_path / "octop.db")
    run_migrations(db)
    UserRepo(db).create(username="u", password_hash="h", role="user")
    AgentRepo(db).create(agent_id="a1", user_id=1, name="Agent 1")
    threads = ThreadRepo(db)
    return ThreadRegistry(session_repo=SessionRepo(db), thread_repo=threads), threads


def _processor(registry: ThreadRegistry, tagger: Any = None) -> GlobalProcessor:
    return GlobalProcessor(
        agent_manager=MagicMock(),
        thread_registry=registry,
        audit_repo=MagicMock(),
        agent_repo=MagicMock(),
        user_repo=MagicMock(),
        connector_repo=MagicMock(),
        dispatcher=SlashDispatcher(),
        auto_tagger=tagger,
    )


def _insert(threads: ThreadRepo, thread_id: str, **kwargs: Any) -> None:
    kwargs.setdefault("last_active", 0)
    threads.insert(
        thread_id=thread_id,
        agent_id="a1",
        user_id=1,
        channel_type="dashboard",
        session_key=ThreadRegistry.dashboard_key(agent_id="a1", user_id=1),
        **kwargs,
    )


@pytest.mark.asyncio
async def test_first_turn_schedules_auto_tag(
    registry: tuple[ThreadRegistry, ThreadRepo],
):
    reg, threads = registry
    _insert(threads, "thr_1")
    tagger = _RecordingTagger()
    processor = _processor(reg, tagger)

    processor._touch_thread_after_turn("thr_1", "帮我写一份周报")
    await asyncio.sleep(0.01)

    assert len(tagger.calls) == 1
    call = tagger.calls[0]
    assert call["agent_id"] == "a1"
    assert call["user_id"] == 1
    assert call["thread_id"] == "thr_1"
    assert call["title"] == "帮我写一份周报"
    assert call["first_message"] == "帮我写一份周报"
    row = reg.get_thread("thr_1")
    assert row is not None and row.title == "帮我写一份周报"


@pytest.mark.asyncio
async def test_first_turn_with_preset_title_schedules(
    registry: tuple[ThreadRegistry, ThreadRepo],
):
    # Regression: the dashboard PATCHes the title before the turn completes,
    # so the hook must trigger on the first turn itself, not on title change.
    reg, threads = registry
    _insert(threads, "thr_1", title="来日常聊聊天吧")
    tagger = _RecordingTagger()
    processor = _processor(reg, tagger)

    processor._touch_thread_after_turn("thr_1", "来日常聊聊天吧")
    await asyncio.sleep(0.01)

    assert len(tagger.calls) == 1
    assert tagger.calls[0]["title"] == "来日常聊聊天吧"


@pytest.mark.asyncio
async def test_second_turn_does_not_reschedule(
    registry: tuple[ThreadRegistry, ThreadRepo],
):
    reg, threads = registry
    _insert(threads, "thr_1")
    tagger = _RecordingTagger()
    processor = _processor(reg, tagger)

    processor._touch_thread_after_turn("thr_1", "首条消息")
    processor._touch_thread_after_turn("thr_1", "后续消息")
    await asyncio.sleep(0.01)

    assert len(tagger.calls) == 1


@pytest.mark.asyncio
async def test_first_turn_with_existing_tags_skips(
    registry: tuple[ThreadRegistry, ThreadRepo],
):
    reg, threads = registry
    _insert(threads, "thr_1", tags=["已有标签"])
    tagger = _RecordingTagger()
    processor = _processor(reg, tagger)

    processor._touch_thread_after_turn("thr_1", "首条消息")
    await asyncio.sleep(0.01)

    assert tagger.calls == []


@pytest.mark.asyncio
async def test_first_turn_without_text_still_schedules(
    registry: tuple[ThreadRegistry, ThreadRepo],
):
    reg, threads = registry
    _insert(threads, "thr_1")
    tagger = _RecordingTagger()
    processor = _processor(reg, tagger)

    processor._touch_thread_after_turn("thr_1", None)
    await asyncio.sleep(0.01)

    assert len(tagger.calls) == 1
    assert tagger.calls[0]["title"] == ""
    assert tagger.calls[0]["first_message"] == ""


@pytest.mark.asyncio
async def test_without_tagger_is_noop(
    registry: tuple[ThreadRegistry, ThreadRepo],
):
    reg, threads = registry
    _insert(threads, "thr_1")
    processor = _processor(reg)

    processor._touch_thread_after_turn("thr_1", "首条消息")
    await asyncio.sleep(0.01)

    row = reg.get_thread("thr_1")
    assert row is not None and row.title == "首条消息"


@pytest.mark.asyncio
async def test_tagger_failure_stays_silent(
    registry: tuple[ThreadRegistry, ThreadRepo],
):
    reg, threads = registry
    _insert(threads, "thr_1")
    tagger = _RecordingTagger(exc=RuntimeError("boom"))
    processor = _processor(reg, tagger)

    processor._touch_thread_after_turn("thr_1", "首条消息")
    await asyncio.sleep(0.01)

    assert len(tagger.calls) == 1
