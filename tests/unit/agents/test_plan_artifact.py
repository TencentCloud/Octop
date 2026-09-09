"""Unit tests for Plan → Craft brief artifact (#616 P5)."""

from __future__ import annotations

from octop.infra.agents.plan_artifact import format_plan_brief, parse_plan_brief_steps


def test_format_plan_brief_round_trip_steps() -> None:
    brief = format_plan_brief(
        summary="Ship conversation modes.",
        todos=[
            {"id": "1", "content": "Ask denylist", "status": "completed"},
            {"id": "2", "content": "Plan CTA", "status": "pending"},
        ],
    )
    assert "Approved plan" in brief
    assert "Ship conversation modes." in brief
    assert "Execute this plan now." in brief
    steps = parse_plan_brief_steps(brief)
    assert steps[0].startswith("Ask denylist")
    assert "Plan CTA" in steps[1]


def test_format_plan_brief_summary_only() -> None:
    brief = format_plan_brief(summary="Just do the thing.")
    assert "Just do the thing." in brief
    assert parse_plan_brief_steps(brief) == []
