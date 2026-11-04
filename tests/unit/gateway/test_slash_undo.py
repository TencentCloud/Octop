"""Slash /undo rewinds the current thread and prefills the removed question."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from octop.infra.agents.threads.rewind import RewindOutcome
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.gateway.slash import BufferSink, SlashCommand
from octop.infra.gateway.slash.ctx import SlashCtx
from octop.infra.gateway.slash.handlers.session import cmd_undo
from octop.infra.gateway.ws import WebSocketHub


def _ctx(*, hub: WebSocketHub | None = None, manager: MagicMock | None = None) -> SlashCtx:
    registry = MagicMock()
    registry.get_bound_thread_id.return_value = "thr_active"
    return SlashCtx(
        agent_id="a1",
        user_id=1,
        channel_type="dashboard",
        session_key="sk",
        thread_registry=registry,
        agent_manager=manager,
        locale="en",
        ws_hub=hub,
    )


@pytest.mark.asyncio
async def test_cmd_undo_allows_the_command_turn_itself() -> None:
    """Dashboard marks the slash request active before /undo runs."""
    hub = WebSocketHub()
    hub.mark_turn_active("thr_active")
    manager = MagicMock()
    manager.get_agent.return_value = MagicMock()

    async def _rewind(**kwargs: object) -> RewindOutcome:
        assert kwargs["turns"] == 1
        return RewindOutcome(turns_undone=1, prefill_text="q", cut_message_id="u", removed_count=1)

    sink = BufferSink()
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr("octop.infra.gateway.slash.handlers.session.rewind_thread", _rewind)
        await cmd_undo(MagicMock(), SlashCommand("undo", ""), _ctx(hub=hub, manager=manager), sink)
    assert sink.actions
    assert "still in progress" not in sink.lines[0]


@pytest.mark.asyncio
async def test_cmd_undo_plain_command_undoes_one_turn() -> None:
    manager = MagicMock()
    manager.get_agent.return_value = MagicMock()
    seen: list[int] = []

    async def _rewind(**kwargs: object) -> RewindOutcome:
        seen.append(int(kwargs["turns"]))  # type: ignore[arg-type]
        return RewindOutcome(turns_undone=1, prefill_text="q", cut_message_id="u", removed_count=1)

    sink = BufferSink()
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr("octop.infra.gateway.slash.handlers.session.rewind_thread", _rewind)
        await cmd_undo(MagicMock(), SlashCommand("undo", ""), _ctx(manager=manager), sink)
        await cmd_undo(MagicMock(), SlashCommand("undo", "[n]"), _ctx(manager=manager), sink)
    assert seen == [1, 1]


@pytest.mark.asyncio
async def test_cmd_undo_rejects_a_bad_count() -> None:
    sink = BufferSink()
    await cmd_undo(MagicMock(), SlashCommand("undo", "abc"), _ctx(manager=MagicMock()), sink)
    assert sink.lines == ["Usage: /undo, or /undo 3 to undo the last 3 turns"]


@pytest.mark.asyncio
async def test_cmd_undo_rewinds_and_prefills() -> None:
    manager = MagicMock()
    harness = MagicMock()
    manager.get_agent.return_value = harness
    repo = MagicMock()
    archive = MagicMock()
    outcome = RewindOutcome(
        turns_undone=2,
        prefill_text="what happened",
        cut_message_id="u2",
        removed_count=4,
    )

    async def _rewind(**kwargs: object) -> RewindOutcome:
        assert kwargs["turns"] == 2
        assert kwargs["thread_id"] == "thr_active"
        assert kwargs["thread_message_repo"] is repo
        return outcome

    sink = BufferSink()
    ctx = _ctx(manager=manager)
    ctx.thread_message_repo = repo
    ctx.history_archive = archive
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(
            "octop.infra.gateway.slash.handlers.session.rewind_thread",
            _rewind,
        )
        await cmd_undo(MagicMock(), SlashCommand("undo", "2"), ctx, sink)

    assert sink.actions == [
        {
            "action": "undo",
            "prefill": "what happened",
            "thread_id": "thr_active",
            "message_id": "u2",
        }
    ]
    assert "2" in sink.lines[0]
    assert "Files and memories are unchanged." in sink.lines[0]


@pytest.mark.asyncio
async def test_cmd_undo_reports_an_empty_thread() -> None:
    manager = MagicMock()
    manager.get_agent.return_value = MagicMock()
    sink = BufferSink()

    async def _rewind(**_kwargs: object) -> RewindOutcome:
        raise OctopError(ErrorCode.UNDO_EMPTY, "empty")

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(
            "octop.infra.gateway.slash.handlers.session.rewind_thread",
            _rewind,
        )
        await cmd_undo(MagicMock(), SlashCommand("undo", ""), _ctx(manager=manager), sink)
    assert sink.lines == ["Nothing to undo in this conversation."]
    assert sink.actions == []
