from __future__ import annotations

import json
from typing import Any

import pytest

from octop.infra.agents.ask_user_question import build_ask_user_question_tool


@pytest.mark.asyncio
async def test_ask_user_question_interrupts_and_returns_compact_answers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_interrupt(request: dict[str, Any]) -> dict[str, Any]:
        captured.update(request)
        return {
            "decisions": [
                {
                    "type": "answer",
                    "answers": [{"id": "database", "selected": ["SQLite"]}],
                }
            ]
        }

    monkeypatch.setattr("octop.infra.agents.ask_user_question.interrupt", fake_interrupt)
    tool = build_ask_user_question_tool()
    result = await tool.ainvoke(
        {
            "questions": [
                {
                    "id": "database",
                    "header": "Storage",
                    "question": "Which database?",
                    "options": [
                        {"label": "SQLite", "description": "Single-node"},
                        {"label": "PostgreSQL"},
                    ],
                }
            ]
        }
    )

    assert captured["kind"] == "ask_user_question"
    assert captured["questions"][0]["id"] == "database"
    assert json.loads(result) == {"answers": [{"id": "database", "selected": ["SQLite"]}]}


@pytest.mark.asyncio
async def test_ask_user_question_rejects_duplicate_question_ids() -> None:
    tool = build_ask_user_question_tool()
    with pytest.raises(ValueError, match="question ids must be unique"):
        await tool.ainvoke(
            {
                "questions": [
                    {"id": "same", "question": "First?"},
                    {"id": "same", "question": "Second?"},
                ]
            }
        )
