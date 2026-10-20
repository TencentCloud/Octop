"""Tests for the ``ask_user_question`` built-in tool and its HITL wiring."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from octop_harness.builtin.tools import ASK_USER_TOOL_NAME, ask_user_question
from octop_harness.builtin.tools.ask_user import (
    HEADLESS_FALLBACK,
    MAX_OPTIONS,
    MAX_QUESTIONS,
    AskUserQuestionArgs,
)

ONE_QUESTION = {
    "questions": [
        {
            "header": "Storage",
            "question": "Which database?",
            "options": [
                {"label": "PostgreSQL", "description": "Concurrent writes"},
                {"label": "SQLite", "description": "Zero ops"},
            ],
        }
    ]
}


class TestSchema:
    def test_tool_name(self) -> None:
        assert ask_user_question.name == ASK_USER_TOOL_NAME

    def test_accepts_valid_payload(self) -> None:
        args = AskUserQuestionArgs.model_validate(ONE_QUESTION)
        assert args.questions[0].header == "Storage"
        assert args.questions[0].options[1].label == "SQLite"

    def test_options_are_optional(self) -> None:
        args = AskUserQuestionArgs.model_validate({"questions": [{"question": "Why?"}]})
        assert args.questions[0].options == []
        assert args.questions[0].multi_select is False

    def test_rejects_empty_questions(self) -> None:
        with pytest.raises(ValidationError):
            AskUserQuestionArgs.model_validate({"questions": []})

    def test_rejects_too_many_questions(self) -> None:
        payload = {"questions": [{"question": f"q{i}"} for i in range(MAX_QUESTIONS + 1)]}
        with pytest.raises(ValidationError):
            AskUserQuestionArgs.model_validate(payload)

    def test_rejects_too_many_options(self) -> None:
        payload = {
            "questions": [
                {
                    "question": "q",
                    "options": [{"label": f"o{i}"} for i in range(MAX_OPTIONS + 1)],
                }
            ]
        }
        with pytest.raises(ValidationError):
            AskUserQuestionArgs.model_validate(payload)

    def test_rejects_blank_question(self) -> None:
        with pytest.raises(ValidationError):
            AskUserQuestionArgs.model_validate({"questions": [{"question": ""}]})

    def test_strips_whitespace(self) -> None:
        args = AskUserQuestionArgs.model_validate({"questions": [{"question": "  q  "}]})
        assert args.questions[0].question == "q"

    def test_schema_exposes_questions(self) -> None:
        schema = ask_user_question.args_schema.model_json_schema()
        assert "questions" in schema["properties"]


class TestHeadlessFallback:
    def test_returns_instruction_not_block(self) -> None:
        assert ask_user_question.invoke(ONE_QUESTION) == HEADLESS_FALLBACK

    def test_fallback_discourages_retry(self) -> None:
        assert "do not call ask_user_question again" in HEADLESS_FALLBACK.lower()


class TestAgentWiring:
    def _active(self, **overrides: object) -> bool:
        from octop_harness.agent import HarnessAgent
        from octop_harness.config import HarnessAgentConfig

        agent = HarnessAgent.__new__(HarnessAgent)
        agent._config = HarnessAgentConfig(**overrides)  # type: ignore[arg-type]
        return agent._ask_user_active()

    def test_enabled_by_default(self) -> None:
        assert self._active() is True

    def test_disabled_by_config_flag(self) -> None:
        assert self._active(ask_user_enabled=False) is False

    def test_disabled_when_tool_disabled(self) -> None:
        assert self._active(tools_disabled=[ASK_USER_TOOL_NAME]) is False

    def test_config_roundtrip(self) -> None:
        from octop_harness.config import HarnessAgentConfig

        cfg = HarnessAgentConfig(ask_user_enabled=False)
        assert cfg.to_dict()["ask_user_enabled"] is False
