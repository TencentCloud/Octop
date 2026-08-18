"""Persist and resume structured questions raised by ``ask_user_question``."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from harness_gateway.models import MessageEvent

from octop.i18n import tr
from octop.infra.db.repos.user_questions import (
    PendingUserQuestionRepo,
    PendingUserQuestionRow,
)
from octop.infra.gateway.process.usage_record import UsageTracker
from octop.infra.utils.locale import normalize_locale


def is_user_question_request(request: Any) -> bool:
    return isinstance(request, dict) and request.get("kind") == "ask_user_question"


def _questions_from_request(request: dict[str, Any]) -> list[dict[str, Any]]:
    raw = request.get("questions")
    if not isinstance(raw, list) or not raw:
        raise ValueError("ask_user_question requires at least one question")
    questions: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("ask_user_question contains an invalid question")
        question_id = item.get("id")
        text = item.get("question")
        if not isinstance(question_id, str) or not question_id or question_id in seen:
            raise ValueError("ask_user_question contains an invalid or duplicate id")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("ask_user_question contains an empty question")
        options_raw = item.get("options")
        options = [dict(option) for option in options_raw or [] if isinstance(option, dict)]
        questions.append(
            {
                "id": question_id,
                "question": text.strip(),
                **({"header": item["header"]} if isinstance(item.get("header"), str) else {}),
                "options": options,
                "multi_select": item.get("multi_select") is True,
            }
        )
        seen.add(question_id)
    return questions


def _format_channel_card(record: PendingUserQuestionRow, locale: str) -> str:
    lines = [tr("slash.questions.card_title", locale)]
    for index, question in enumerate(record.questions, start=1):
        lines.append(f"{index}. **{question['question']}**")
        options = question.get("options")
        if isinstance(options, list):
            for option_index, option in enumerate(options, start=1):
                if isinstance(option, dict) and isinstance(option.get("label"), str):
                    label = option["label"]
                    description = option.get("description")
                    suffix = f" — {description}" if isinstance(description, str) else ""
                    lines.append(f"   {option_index}) {label}{suffix}")
    if len(record.questions) == 1:
        lines.append(tr("slash.questions.card_footer_single", locale))
    else:
        lines.append(tr("slash.questions.card_footer_multiple", locale))
    lines.append(tr("slash.questions.card_pending_id", locale, pending_id=record.pending_id))
    return "\n".join(lines)


def _single_answer(question: dict[str, Any], text: str) -> dict[str, Any]:
    value = text.strip()
    if not value:
        raise ValueError("answer is empty")
    options = question.get("options")
    labels = [
        str(option["label"])
        for option in options or []
        if isinstance(option, dict) and isinstance(option.get("label"), str)
    ]
    selected: list[str] = []
    custom: str | None = None
    if labels:
        pieces = [part.strip() for part in value.split(",") if part.strip()]
        for piece in pieces:
            if piece.isdigit() and 1 <= int(piece) <= len(labels):
                label = labels[int(piece) - 1]
            else:
                label = next((item for item in labels if item.casefold() == piece.casefold()), "")
            if label and label not in selected:
                selected.append(label)
            elif not label:
                custom = value
                selected = [] if question.get("multi_select") is not True else selected
                break
        if question.get("multi_select") is not True and len(selected) > 1:
            raise ValueError("single-select question accepts only one option")
    else:
        custom = value
    answer: dict[str, Any] = {"id": question["id"], "selected": selected}
    if custom:
        answer["custom"] = custom
    return answer


def parse_channel_answers(record: PendingUserQuestionRow, text: str) -> list[dict[str, Any]]:
    """Parse `/answer` text; batches use `1=value; 2=value`."""
    if len(record.questions) == 1:
        return [_single_answer(record.questions[0], text)]
    parts = [part.strip() for part in text.split(";") if part.strip()]
    values: dict[str, str] = {}
    for part in parts:
        key, separator, value = part.partition("=")
        if not separator:
            raise ValueError("multiple questions require `1=answer; 2=answer`")
        values[key.strip()] = value.strip()
    answers: list[dict[str, Any]] = []
    for index, question in enumerate(record.questions, start=1):
        answer_value = values.get(str(index)) or values.get(str(question["id"]))
        if answer_value is None:
            raise ValueError(f"missing answer for question {index}")
        answers.append(_single_answer(question, answer_value))
    return answers


def validate_answers(
    record: PendingUserQuestionRow, raw_answers: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Validate a structured Dashboard response against the persisted request."""
    by_id = {str(item.get("id")): item for item in raw_answers if isinstance(item, dict)}
    if len(by_id) != len(record.questions):
        raise ValueError("one answer is required for every question")
    normalized: list[dict[str, Any]] = []
    for question in record.questions:
        question_id = str(question["id"])
        raw = by_id.get(question_id)
        if raw is None:
            raise ValueError(f"missing answer for {question_id}")
        selected_raw = raw.get("selected")
        selected = (
            [str(item) for item in selected_raw if isinstance(item, str)]
            if isinstance(selected_raw, list)
            else []
        )
        labels = {
            str(option["label"])
            for option in question.get("options") or []
            if isinstance(option, dict) and isinstance(option.get("label"), str)
        }
        if any(label not in labels for label in selected):
            raise ValueError(f"unknown option for {question_id}")
        if question.get("multi_select") is not True and len(selected) > 1:
            raise ValueError(f"{question_id} accepts only one option")
        custom_raw = raw.get("custom")
        custom = custom_raw.strip() if isinstance(custom_raw, str) else ""
        item: dict[str, Any] = {"id": question_id, "selected": selected}
        if custom:
            item["custom"] = custom
        normalized.append(item)
    return normalized


@dataclass
class QuestionResumeOutcome:
    completed_turn: bool = False


class UserQuestionCoordinator:
    def __init__(self, repo: PendingUserQuestionRepo) -> None:
        self.repo = repo
        self.repo.recover_interrupted_resumes()

    def register_from_request(
        self,
        request: dict[str, Any],
        *,
        thread_id: str,
        agent_id: str,
        user_id: int,
        session_key: str,
        channel_type: str,
    ) -> PendingUserQuestionRow:
        return self.repo.register(
            thread_id=thread_id,
            agent_id=agent_id,
            user_id=user_id,
            session_key=session_key,
            channel_type=channel_type,
            questions=_questions_from_request(request),
        )

    def pending_payload(
        self, *, thread_id: str, agent_id: str, user_id: int
    ) -> dict[str, Any] | None:
        row = self.repo.pending_for_thread(thread_id, agent_id=agent_id, user_id=user_id)
        if row is None:
            return None
        return {"pending_id": row.pending_id, "questions": row.questions}

    def channel_card(self, record: PendingUserQuestionRow, locale: str) -> str:
        return _format_channel_card(record, normalize_locale(locale))

    def auto_answer_for_thread(
        self, *, thread_id: str, agent_id: str, user_id: int
    ) -> PendingUserQuestionRow | None:
        record = self.repo.pending_for_thread(thread_id, agent_id=agent_id, user_id=user_id)
        if record is None or len(record.questions) != 1:
            return None
        return record if not record.questions[0].get("options") else None

    async def iter_channel_answer(
        self,
        *,
        record: PendingUserQuestionRow,
        answer_text: str,
        agent_manager: Any,
        hitl_coordinator: Any,
        locale: str,
        usage_tracker: UsageTracker,
        outcome: QuestionResumeOutcome,
    ) -> AsyncIterator[MessageEvent]:
        lang = normalize_locale(locale)
        try:
            answers = parse_channel_answers(record, answer_text)
        except ValueError as exc:
            yield MessageEvent.text(tr("slash.questions.invalid_answer", lang, error=str(exc)))
            return
        if not self.repo.claim(record.pending_id, agent_id=record.agent_id, user_id=record.user_id):
            yield MessageEvent.text(tr("slash.questions.none_pending", lang))
            return
        yield MessageEvent.text(tr("slash.questions.answer_ack", lang))
        try:
            from octop.infra.gateway.hitl.coordinator import HitlStreamContext
            from octop.infra.gateway.process.stream_project import (
                StreamProjectionState,
                project_resume_stream,
            )

            projection = StreamProjectionState()
            async for event in project_resume_stream(
                agent_manager,
                record.agent_id,
                record.thread_id,
                [{"type": "answer", "answers": answers}],
                usage_tracker=usage_tracker,
                locale=lang,
                projection_state=projection,
                hitl_coordinator=hitl_coordinator,
                hitl_ctx=HitlStreamContext(
                    thread_id=record.thread_id,
                    agent_id=record.agent_id,
                    user_id=record.user_id,
                    session_key=record.session_key,
                    channel_type=record.channel_type,
                ),
                question_coordinator=self,
            ):
                yield event
            self.repo.mark_answered(record.pending_id, answers)
            outcome.completed_turn = True
        except Exception:
            self.repo.release(record.pending_id)
            raise


__all__ = [
    "QuestionResumeOutcome",
    "UserQuestionCoordinator",
    "is_user_question_request",
    "parse_channel_answers",
    "validate_answers",
]
