"""Unit tests for the ``ask_user_question`` HITL channel."""

from __future__ import annotations

import pytest

from octop.infra.gateway.hitl.coordinator import (
    HitlChannelCoordinator,
    decision_rejection_reason,
)
from octop.infra.gateway.hitl.format import (
    extract_questions,
    format_ask_card,
    format_hitl_card,
    is_ask_action_requests,
    parse_ask_reply,
)
from octop.infra.gateway.hitl.store import HitlPendingStore

SINGLE_CHOICE = [
    {
        "name": "ask_user_question",
        "args": {
            "questions": [
                {
                    "header": "Storage",
                    "question": "Which database should we use?",
                    "options": [
                        {"label": "PostgreSQL", "description": "Concurrent writes"},
                        {"label": "SQLite", "description": "Zero ops"},
                    ],
                }
            ]
        },
    }
]

MULTI_CHOICE = [
    {
        "name": "ask_user_question",
        "args": {
            "questions": [
                {
                    "question": "Which channels should be enabled?",
                    "multi_select": True,
                    "options": [
                        {"label": "Feishu"},
                        {"label": "Slack"},
                        {"label": "Telegram"},
                    ],
                }
            ]
        },
    }
]

OPEN_ENDED = [
    {
        "name": "ask_user_question",
        "args": {"questions": [{"question": "What should the report cover?"}]},
    }
]

THREE_QUESTIONS = [
    {
        "name": "ask_user_question",
        "args": {
            "questions": [
                {
                    "header": "Destination",
                    "question": "Where should we go?",
                    "options": [{"label": "Mountains"}, {"label": "City"}],
                },
                {
                    "header": "Budget",
                    "question": "What is the budget?",
                    "options": [{"label": "Economy"}, {"label": "Premium"}],
                },
                {
                    "header": "Transport",
                    "question": "How should we travel?",
                    "options": [{"label": "Train"}, {"label": "Drive"}],
                },
            ]
        },
    }
]

APPROVAL = [{"name": "execute", "args": {"command": "ls"}}]


def _questions(actions: list[dict]) -> list[dict]:
    return extract_questions(actions)


class TestDetection:
    def test_ask_actions_detected(self) -> None:
        assert is_ask_action_requests(SINGLE_CHOICE)

    def test_approval_actions_not_detected(self) -> None:
        assert not is_ask_action_requests(APPROVAL)

    def test_empty_actions_not_detected(self) -> None:
        assert not is_ask_action_requests([])

    def test_extract_questions(self) -> None:
        questions = _questions(SINGLE_CHOICE)
        assert len(questions) == 1
        assert questions[0]["question"] == "Which database should we use?"

    def test_extract_questions_ignores_malformed(self) -> None:
        actions = [{"name": "ask_user_question", "args": {"questions": "nope"}}]
        assert extract_questions(actions) == []


class TestCard:
    def test_hitl_card_dispatches_to_ask(self) -> None:
        card = format_hitl_card(SINGLE_CHOICE, pending_id="p1", locale="en")
        assert "PostgreSQL" in card
        assert "a) PostgreSQL" in card
        assert "b) SQLite" in card
        assert "p1" in card

    def test_ask_card_shows_header(self) -> None:
        card = format_ask_card(_questions(SINGLE_CHOICE), pending_id="p1", locale="en")
        assert "[Storage]" in card

    def test_multi_select_hint(self) -> None:
        card = format_ask_card(_questions(MULTI_CHOICE), pending_id="p1", locale="en")
        assert "multiple allowed" in card

    def test_open_ended_hint(self) -> None:
        card = format_ask_card(_questions(OPEN_ENDED), pending_id="p1", locale="en")
        assert "answer in a sentence" in card

    def test_approval_card_unchanged(self) -> None:
        card = format_hitl_card(APPROVAL, pending_id="p1", locale="en")
        assert "command" in card

    def test_zh_locale(self) -> None:
        card = format_hitl_card(SINGLE_CHOICE, pending_id="p1", locale="zh")
        assert "拍板" in card

    def test_im_card_shows_only_current_question(self) -> None:
        questions = _questions(THREE_QUESTIONS)
        first = format_ask_card(questions, pending_id="p1", locale="en")
        assert "Question 1 of 3" in first
        assert "Where should we go?" in first
        assert "What is the budget?" not in first

        second = format_ask_card(
            questions,
            pending_id="p1",
            locale="en",
            question_index=1,
        )
        assert "Question 2 of 3" in second
        assert "What is the budget?" in second
        assert "Where should we go?" not in second

    def test_im_options_are_separated_by_blank_lines(self) -> None:
        card = format_ask_card(_questions(SINGLE_CHOICE), pending_id="p1", locale="en")
        assert "a) PostgreSQL — Concurrent writes\n\n" in card


class TestReplyParsing:
    @pytest.mark.parametrize("reply", ["a", "1"])
    def test_letter_and_digit_select_first_option(self, reply: str) -> None:
        answer = parse_ask_reply(reply, _questions(SINGLE_CHOICE), locale="en")
        assert "PostgreSQL" in answer

    def test_second_option(self) -> None:
        answer = parse_ask_reply("b", _questions(SINGLE_CHOICE), locale="en")
        assert "SQLite" in answer

    def test_multi_select_expands_all(self) -> None:
        answer = parse_ask_reply("a,c", _questions(MULTI_CHOICE), locale="en")
        assert "Feishu" in answer
        assert "Telegram" in answer

    def test_single_select_keeps_one(self) -> None:
        answer = parse_ask_reply("a,b", _questions(SINGLE_CHOICE), locale="en")
        assert "SQLite" not in answer
        assert "PostgreSQL" in answer

    def test_out_of_range_forwarded_verbatim(self) -> None:
        answer = parse_ask_reply("z", _questions(SINGLE_CHOICE), locale="en")
        assert answer == "z"

    def test_free_text_forwarded_verbatim(self) -> None:
        text = "SQLite, but enable WAL mode"
        assert parse_ask_reply(text, _questions(SINGLE_CHOICE), locale="en") == text

    def test_topic_switch_forwarded_verbatim(self) -> None:
        text = "actually, show me the logs first"
        assert parse_ask_reply(text, _questions(SINGLE_CHOICE), locale="en") == text

    def test_open_ended_forwarded_verbatim(self) -> None:
        assert parse_ask_reply("a", _questions(OPEN_ENDED), locale="en") == "a"

    def test_multi_question_forwarded_verbatim(self) -> None:
        questions = _questions(SINGLE_CHOICE) + _questions(MULTI_CHOICE)
        assert parse_ask_reply("a", questions, locale="en") == "a"


class TestCoordinatorRouting:
    def _register(self, store: HitlPendingStore, actions: list[dict]) -> None:
        store.register(
            thread_id="thr1",
            agent_id="agent1",
            user_id=7,
            session_key="sk1",
            channel_type="feishu",
            action_requests=actions,
            review_configs=None,
        )

    def test_resolves_ask_pending(self) -> None:
        coordinator = HitlChannelCoordinator(HitlPendingStore())
        self._register(coordinator.store, SINGLE_CHOICE)
        record = coordinator.resolve_ask_pending("sk1", agent_id="agent1", user_id=7)
        assert record is not None
        assert record.thread_id == "thr1"

    def test_approval_pending_not_routed(self) -> None:
        coordinator = HitlChannelCoordinator(HitlPendingStore())
        self._register(coordinator.store, APPROVAL)
        assert coordinator.resolve_ask_pending("sk1", agent_id="agent1", user_id=7) is None

    def test_other_user_cannot_answer(self) -> None:
        coordinator = HitlChannelCoordinator(HitlPendingStore())
        self._register(coordinator.store, SINGLE_CHOICE)
        assert coordinator.resolve_ask_pending("sk1", agent_id="agent1", user_id=99) is None

    def test_other_agent_not_routed(self) -> None:
        coordinator = HitlChannelCoordinator(HitlPendingStore())
        self._register(coordinator.store, SINGLE_CHOICE)
        assert coordinator.resolve_ask_pending("sk1", agent_id="other", user_id=7) is None

    def test_no_pending(self) -> None:
        coordinator = HitlChannelCoordinator(HitlPendingStore())
        assert coordinator.resolve_ask_pending("sk1", agent_id="agent1", user_id=7) is None

    def test_build_answer_decisions(self) -> None:
        coordinator = HitlChannelCoordinator(HitlPendingStore())
        self._register(coordinator.store, SINGLE_CHOICE)
        record = coordinator.resolve_ask_pending("sk1", agent_id="agent1", user_id=7)
        assert record is not None
        decisions = coordinator.build_answer_decisions(record, "a", locale="en")
        assert len(decisions) == 1
        assert decisions[0]["type"] == "respond"
        assert "PostgreSQL" in decisions[0]["message"]

    def test_resolved_pending_not_routed(self) -> None:
        coordinator = HitlChannelCoordinator(HitlPendingStore())
        self._register(coordinator.store, SINGLE_CHOICE)
        record = coordinator.resolve_ask_pending("sk1", agent_id="agent1", user_id=7)
        assert record is not None
        coordinator.store.mark_resolved(record.pending_id, "approved")
        assert coordinator.resolve_ask_pending("sk1", agent_id="agent1", user_id=7) is None

    def test_multiple_questions_are_collected_before_resume(self) -> None:
        coordinator = HitlChannelCoordinator(HitlPendingStore())
        self._register(coordinator.store, THREE_QUESTIONS)
        record = coordinator.resolve_ask_pending("sk1", agent_id="agent1", user_id=7)
        assert record is not None

        resume, next_card = coordinator.collect_ask_reply(record, "a", locale="en")
        assert resume is None
        assert next_card is not None
        assert "Question 2 of 3" in next_card
        assert record.ask_answers == ["Mountains"]

        resume, next_card = coordinator.collect_ask_reply(record, "b", locale="en")
        assert resume is None
        assert next_card is not None
        assert "Question 3 of 3" in next_card
        assert record.ask_answers == ["Mountains", "Premium"]

        resume, next_card = coordinator.collect_ask_reply(record, "a", locale="en")
        assert next_card is None
        assert resume is not None
        assert "Destination: Mountains" in resume
        assert "Budget: Premium" in resume
        assert "Transport: Train" in resume


ASK_REVIEW = [{"action_name": "ask_user_question", "allowed_decisions": ["respond"]}]
APPROVAL_REVIEW = [{"action_name": "execute", "allowed_decisions": ["approve", "reject"]}]


class TestDecisionValidation:
    """A stale client must fail fast at the API, not deep inside the graph."""

    def _record(self, actions: list[dict], review: list[dict] | None):
        store = HitlPendingStore()
        return store.register(
            thread_id="thr1",
            agent_id="agent1",
            user_id=7,
            session_key="sk1",
            channel_type="dashboard",
            action_requests=actions,
            review_configs=review,
        )

    def test_approve_on_ask_tool_rejected(self) -> None:
        record = self._record(SINGLE_CHOICE, ASK_REVIEW)
        reason = decision_rejection_reason(record, [{"type": "approve"}])
        assert reason is not None
        assert "not allowed" in reason
        assert "ask_user_question" in reason

    def test_respond_on_ask_tool_accepted(self) -> None:
        record = self._record(SINGLE_CHOICE, ASK_REVIEW)
        decisions = [{"type": "respond", "message": "PostgreSQL"}]
        assert decision_rejection_reason(record, decisions) is None

    def test_respond_on_approval_tool_rejected(self) -> None:
        record = self._record(APPROVAL, APPROVAL_REVIEW)
        reason = decision_rejection_reason(record, [{"type": "respond", "message": "x"}])
        assert reason is not None
        assert "not allowed" in reason

    def test_approve_on_approval_tool_accepted(self) -> None:
        record = self._record(APPROVAL, APPROVAL_REVIEW)
        assert decision_rejection_reason(record, [{"type": "approve"}]) is None

    def test_count_mismatch_rejected(self) -> None:
        record = self._record(SINGLE_CHOICE, ASK_REVIEW)
        decisions = [{"type": "respond", "message": "a"}, {"type": "respond", "message": "b"}]
        reason = decision_rejection_reason(record, decisions)
        assert reason is not None
        assert "expected 1 decision" in reason

    def test_missing_review_configs_allows_anything(self) -> None:
        record = self._record(SINGLE_CHOICE, None)
        assert decision_rejection_reason(record, [{"type": "approve"}]) is None
