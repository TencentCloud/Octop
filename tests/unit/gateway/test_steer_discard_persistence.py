"""Queued steers a cancel drops stay in the thread history (issue #2220)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from octop.infra.gateway.process.processor import GlobalProcessor
from octop.infra.gateway.slash.dispatcher import SlashDispatcher


def _processor(agent_manager: MagicMock, history_repo: MagicMock) -> GlobalProcessor:
    return GlobalProcessor(
        agent_manager=agent_manager,
        thread_registry=MagicMock(),
        audit_repo=MagicMock(),
        agent_repo=MagicMock(),
        user_repo=MagicMock(),
        connector_repo=MagicMock(),
        dispatcher=SlashDispatcher(),
        thread_message_repo=history_repo,
        gateway=None,
    )


@pytest.mark.asyncio
async def test_persist_discarded_steers_records_each_text_in_order() -> None:
    recorded: list[tuple[str, object]] = {}

    harness = MagicMock()

    async def _append(thread_id: str, messages: object) -> object:
        recorded["append"] = (thread_id, messages)
        return list(messages)  # type: ignore[arg-type]

    harness.aappend_messages = _append
    agent_manager = MagicMock()
    agent_manager.get_agent.return_value = harness
    history_repo = MagicMock()
    processor = _processor(agent_manager, history_repo)

    await processor.persist_discarded_steers(
        "thread-1",
        agent_id="agent-1",
        texts=["follow up Q2", "   ", "and Q3"],
    )

    agent_manager.get_agent.assert_called_once_with("agent-1")
    thread_id, messages = recorded["append"]
    assert thread_id == "thread-1"
    # Blank texts are dropped; the rest keep their queued order.
    assert [m.content for m in messages] == ["follow up Q2", "and Q3"]
    history_repo.append_if_ready.assert_called_once()
    proj_thread, projected = history_repo.append_if_ready.call_args.args
    assert proj_thread == "thread-1"
    assert len(projected) == 2


@pytest.mark.asyncio
async def test_persist_discarded_steers_noop_without_texts() -> None:
    agent_manager = MagicMock()
    history_repo = MagicMock()
    processor = _processor(agent_manager, history_repo)

    await processor.persist_discarded_steers("thread-1", agent_id="agent-1", texts=[])

    agent_manager.get_agent.assert_not_called()
    history_repo.append_if_ready.assert_not_called()
