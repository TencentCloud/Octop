"""The member page must stamp only the files edited in the turn it projects."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from octop_harness.teams.util import PeerCall

from octop.infra.agents.teams.team_manager import TeamManager


def _manager() -> tuple[TeamManager, MagicMock]:
    repo = MagicMock()
    repo.append_if_ready = MagicMock(return_value=1)
    repo.projection_status = MagicMock(return_value="ready")
    manager = TeamManager(
        agent_manager=MagicMock(),
        thread_registry=MagicMock(),
        user_repo=MagicMock(),
        thread_message_repo=repo,
    )
    return manager, repo


def _write(call_id: str, path: str) -> dict[str, Any]:
    return {"name": "write_file", "id": call_id, "args": {"path": path}}


def _turn(call_id: str, path: str, prompt: str, answer: str) -> list[Any]:
    return [
        HumanMessage(content=prompt),
        AIMessage(content="", tool_calls=[_write(call_id, path)]),
        ToolMessage(content="ok", tool_call_id=call_id, name="write_file"),
        AIMessage(content=answer),
    ]


def _edited_files(items: list[Any], answer: str) -> list[str]:
    final = [item for item in items if item.role == "ai" and answer in item.message_json]
    assert final, f"no projected bubble carrying {answer!r}"
    wire = json.loads(final[-1].message_json)
    return wire["data"]["additional_kwargs"]["edited_files"]


@pytest.mark.asyncio
async def test_record_peer_turn_stamps_only_the_files_of_its_own_turn() -> None:
    """The peer thread is reused, so ``result["messages"]`` carries earlier turns.

    The member page slices the projection down to the current turn
    (``_peer_turn_messages``) but must not read the "edited N files" card from the
    unsliced list, or every later answer re-lists files from previous dispatches.
    """
    manager, repo = _manager()
    history = _turn("c1", "old.md", "先写一份", "第一份写好了") + _turn(
        "c2", "new.md", "再写一份", "第二份写好了"
    )

    await manager.record_peer_turn(
        PeerCall(
            from_agent_id="host",
            to_agent_id="child",
            user_id=1,
            message="再写一份",
            source_thread_id="thr_room",
            source_session_key=None,
            job_id="job2",
        ),
        "thr_room~child",
        {"messages": history},
    )

    member = [c for c in repo.append_if_ready.call_args_list if c.args[0] == "thr_room~child"]
    assert member
    assert _edited_files(member[0].args[1], "第二份写好了") == ["new.md"]
