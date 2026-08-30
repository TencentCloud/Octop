"""Validation for the HITL resume request body."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from octop.api.routers.chat.models import HitlResumeBody


def _body(decisions: list[dict]) -> HitlResumeBody:
    return HitlResumeBody(thread_id="thr1", decisions=decisions)


class TestAccepted:
    def test_approve(self) -> None:
        assert _body([{"type": "approve"}]).decisions[0]["type"] == "approve"

    def test_reject_with_message(self) -> None:
        assert _body([{"type": "reject", "message": "no"}]).decisions[0]["message"] == "no"

    def test_reject_without_message(self) -> None:
        assert _body([{"type": "reject"}]).decisions[0]["type"] == "reject"

    def test_respond(self) -> None:
        assert (
            _body([{"type": "respond", "message": "PostgreSQL"}]).decisions[0]["message"]
            == "PostgreSQL"
        )

    def test_edit(self) -> None:
        decision = {"type": "edit", "edited_action": {"name": "execute", "args": {}}}
        assert _body([decision]).decisions[0]["type"] == "edit"

    def test_multiple_decisions(self) -> None:
        assert len(_body([{"type": "approve"}, {"type": "approve"}]).decisions) == 2


class TestRejected:
    def test_empty_decisions(self) -> None:
        with pytest.raises(ValidationError):
            _body([])

    def test_unknown_type(self) -> None:
        with pytest.raises(ValidationError, match="unsupported decision type"):
            _body([{"type": "detonate"}])

    def test_missing_type(self) -> None:
        with pytest.raises(ValidationError, match="unsupported decision type"):
            _body([{"message": "hi"}])

    def test_respond_without_message(self) -> None:
        with pytest.raises(ValidationError, match="non-empty 'message'"):
            _body([{"type": "respond"}])

    def test_respond_with_blank_message(self) -> None:
        with pytest.raises(ValidationError, match="non-empty 'message'"):
            _body([{"type": "respond", "message": "   "}])

    def test_edit_without_edited_action(self) -> None:
        with pytest.raises(ValidationError, match="edited_action"):
            _body([{"type": "edit"}])

    def test_non_string_message(self) -> None:
        with pytest.raises(ValidationError, match="must be a string"):
            _body([{"type": "reject", "message": 42}])

    def test_oversized_message(self) -> None:
        with pytest.raises(ValidationError, match="exceeds"):
            _body([{"type": "respond", "message": "x" * 8001}])

    def test_too_many_decisions(self) -> None:
        with pytest.raises(ValidationError):
            _body([{"type": "approve"}] * 17)
