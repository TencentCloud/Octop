"""Validation for the proactive-care config request body.

``max_interval_hours`` has no ceiling in the dashboard form (the ``InputNumber``
only sets ``min={1}``), so the API is the only place that can keep an absurd
value from being persisted. A stored value that large makes the agent's
proactive-care loop either schedule the next push years out or die outright in
``compute_next_trigger`` (``OverflowError`` at ``infra/proactive/scheduler.py:83``),
and the PUT that caused it returns 200.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from octop.api.routers.proactive_care import ProactiveCareConfigBody
from octop.infra.proactive.scheduler import compute_next_trigger

# 7 days — must stay in sync with the router's own guard rail constant.
CEILING_HOURS = 168


def _body(**kwargs: object) -> ProactiveCareConfigBody:
    return ProactiveCareConfigBody.model_validate(kwargs)


class TestAccepted:
    def test_defaults(self) -> None:
        body = _body()
        assert (body.min_interval_hours, body.max_interval_hours) == (5, 24)

    def test_ceiling_is_accepted(self) -> None:
        body = _body(min_interval_hours=5, max_interval_hours=CEILING_HOURS)
        assert body.max_interval_hours == CEILING_HOURS

    def test_guard_rail_constant_matches_the_ceiling(self) -> None:
        from octop.api.routers import proactive_care

        assert proactive_care._MAX_INTERVAL_HOURS == CEILING_HOURS


class TestRejected:
    def test_above_ceiling(self) -> None:
        with pytest.raises(ValidationError, match="max_interval_hours 不能大于"):
            _body(min_interval_hours=5, max_interval_hours=CEILING_HOURS + 1)

    def test_overflowing_value(self) -> None:
        with pytest.raises(ValidationError, match="max_interval_hours 不能大于"):
            _body(min_interval_hours=5, max_interval_hours=99_999_999_999)

    def test_huge_min_still_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _body(min_interval_hours=99_999_999_999)


def test_ceiling_keeps_the_scheduled_push_reachable() -> None:
    """The accepted ceiling must not itself schedule a push beyond the calendar."""
    now = datetime(2026, 9, 23, 10, 0, tzinfo=UTC)
    nxt = compute_next_trigger(
        now=now,
        active_hours_start="09:00",
        active_hours_end="22:00",
        min_interval_hours=5,
        max_interval_hours=CEILING_HOURS,
        timezone_name="Asia/Shanghai",
    )
    assert 0 < (nxt - now).total_seconds() < 9 * 24 * 3600
