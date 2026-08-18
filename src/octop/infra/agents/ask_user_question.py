"""Structured human-question tool backed by a durable LangGraph interrupt."""

from __future__ import annotations

import json
from typing import Annotated, Any

from langchain_core.tools import StructuredTool
from langgraph.types import interrupt
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ASK_USER_QUESTION_TOOL = "ask_user_question"


class AskUserOption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=240)

    @field_validator("label")
    @classmethod
    def _strip_label(cls, value: str) -> str:
        return value.strip()


class AskUserPrompt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    question: str = Field(min_length=1, max_length=500)
    header: str | None = Field(default=None, max_length=24)
    options: list[AskUserOption] = Field(default_factory=list, max_length=6)
    multi_select: bool = False

    @field_validator("question")
    @classmethod
    def _strip_question(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def _unique_options(self) -> AskUserPrompt:
        labels = [option.label for option in self.options]
        if len(labels) != len(set(labels)):
            raise ValueError("option labels must be unique within a question")
        return self


def _answer_from_resume(response: Any, questions: list[AskUserPrompt]) -> dict[str, Any]:
    decisions = response.get("decisions") if isinstance(response, dict) else None
    decision = decisions[0] if isinstance(decisions, list) and decisions else None
    answers = decision.get("answers") if isinstance(decision, dict) else None
    if not isinstance(answers, list):
        raise ValueError("ask_user_question did not receive a user answer")

    expected = {question.id for question in questions}
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in answers:
        if not isinstance(raw, dict):
            raise ValueError("ask_user_question received an invalid answer")
        answer_id = raw.get("id")
        if not isinstance(answer_id, str) or answer_id not in expected or answer_id in seen:
            raise ValueError("ask_user_question received an unknown or duplicate answer id")
        selected_raw = raw.get("selected")
        selected = (
            [str(item) for item in selected_raw if isinstance(item, str)]
            if isinstance(selected_raw, list)
            else []
        )
        custom = raw.get("custom")
        item: dict[str, Any] = {"id": answer_id, "selected": selected}
        if isinstance(custom, str) and custom.strip():
            item["custom"] = custom.strip()
        normalized.append(item)
        seen.add(answer_id)
    if seen != expected:
        raise ValueError("ask_user_question requires one answer for every question")
    return {"answers": normalized}


def build_ask_user_question_tool() -> StructuredTool:
    """Return the model-facing question tool used by every Octop agent."""

    async def ask_user_question(
        questions: Annotated[
            list[AskUserPrompt],
            Field(
                min_length=1,
                max_length=3,
                description=(
                    "One to three concise questions. Put the recommended option first and "
                    "suffix its label with '(Recommended)'."
                ),
            ),
        ],
    ) -> str:
        ids = [question.id for question in questions]
        if len(ids) != len(set(ids)):
            raise ValueError("question ids must be unique")
        payload = {
            "kind": ASK_USER_QUESTION_TOOL,
            "questions": [question.model_dump(exclude_none=True) for question in questions],
        }
        response = interrupt(payload)
        answer = _answer_from_resume(response, questions)
        return json.dumps(answer, ensure_ascii=False, separators=(",", ":"))

    return StructuredTool.from_function(
        coroutine=ask_user_question,
        name=ASK_USER_QUESTION_TOOL,
        description=(
            "Ask the user one to three structured clarification questions and wait for the "
            "answer before continuing. Use this when a user choice materially changes the work."
        ),
    )


__all__ = ["ASK_USER_QUESTION_TOOL", "build_ask_user_question_tool"]
