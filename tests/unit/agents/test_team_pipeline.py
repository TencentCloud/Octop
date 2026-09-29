"""T-10 — team-run pipeline kernel (phase vocabulary, gates, tiers, graphs).

Every gate gets both sides: a case that must be refused (with the rejection code
PLAN §门禁落点④ names) and a case that must pass, so no gate can be a no-op.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from octop.i18n import tr
from octop.infra.agents.teams.pipeline import (
    ALLOWED_KINDS,
    DEFAULT_TIER,
    GRAPH_CODES,
    PHASE_REQUIRED_ARTIFACTS,
    PHASE_TRANSITIONS,
    PHASE_ZH,
    PHASES,
    ROLLBACK_LIMIT,
    TIER_SPEC,
    TIER_ZH,
    TIERS,
    V_CONTRACT_DEP_STALLED,
    V_FINDING_REOPENED_INPUT_MISSING,
    V_KIND_UNKNOWN,
    V_QUALITY_OWNER_INVALID,
    V_REWORK_LOOP_UNESCALATED,
    V_VERIFY_MISSING,
    SpecBoundaryState,
    advance_gate,
    assert_capacity,
    check_run,
    decision_gate,
    finding_reopened,
    missing_artifacts,
    norm_title,
    normalize_tier,
    phase_sequence,
    spec_boundary_state,
    trim_roster,
    validate_task_graph,
)
from octop.infra.errors import ErrorCode, OctopError

_PIPELINE_PATH = (
    Path(__file__).resolve().parents[3]
    / "src"
    / "octop"
    / "infra"
    / "agents"
    / "teams"
    / "pipeline.py"
)

# phase id -> the ``teams.phase.<key>`` i18n key that carries its display name
_PHASE_I18N_KEY = {
    "clarify": "clarify",
    "research": "research",
    "design": "design",
    "spec-review": "spec_review",
    "方案确认": "plan_approval",
    "implement": "implement",
    "review": "review",
    "test": "test",
    "deliver": "deliver",
}

_SPEC_FILLED = (
    "# SPEC\n\n"
    "## 边界与禁止项（强制）\n\n"
    "| 码名 | HTTP | 语义 |\n"
    "|---|---|---|\n"
    "| B1 | 400 | 非法角色 |\n\n"
    "## 下一节\n\n正文\n"
)
_SPEC_EMPTY = (
    "# SPEC\n\n"
    "## 边界与禁止项（强制）\n\n"
    "| 码名 | HTTP | 语义 |\n"
    "|---|---|---|\n"
    "|  |  |  |\n"
    "| | | |\n"
)


def _run(**overrides: object) -> dict[str, object]:
    """A run snapshot that passes every gate unless the test overrides a key."""
    run: dict[str, object] = {
        "phase": "clarify",
        "status": "running",
        "tier": "standard",
        "present_artifacts": ["SPEC.md"],
    }
    run.update(overrides)
    return run


def _assert_code(exc_info: pytest.ExceptionInfo[OctopError], code: ErrorCode) -> OctopError:
    error = exc_info.value
    assert error.code is code, f"expected {code.value}, got {error.code.value}"
    return error


# ─────────────────────────────────────────────────────────────────────────────
# Vocabulary (A2.1) — verbatim values and one display-name source
# ─────────────────────────────────────────────────────────────────────────────


def test_phases_are_the_nine_verbatim_values_in_pipeline_order() -> None:
    assert PHASES == (
        "clarify",
        "research",
        "design",
        "spec-review",
        "方案确认",
        "implement",
        "review",
        "test",
        "deliver",
    )
    assert "方案确认" in PHASES, "the Chinese phase id must stay verbatim (A2.1)"


def test_phase_zh_covers_every_phase_and_matches_the_i18n_bundle() -> None:
    assert set(PHASE_ZH) == set(PHASES)
    assert set(_PHASE_I18N_KEY) == set(PHASES)
    for phase in PHASES:
        key = _PHASE_I18N_KEY[phase]
        assert PHASE_ZH[phase] == tr(f"teams.phase.{key}", "zh"), phase
        assert tr(f"teams.phase.{key}", "zh") != tr(f"teams.phase.{key}", "en")


def test_phase_transitions_cover_every_phase_and_are_derived_from_phases() -> None:
    assert set(PHASE_TRANSITIONS) == set(PHASES)
    for index, phase in enumerate(PHASES[:-1]):
        assert PHASE_TRANSITIONS[phase] == (PHASES[index + 1],)
    assert PHASE_TRANSITIONS[PHASES[-1]] == ()


def test_phase_required_artifacts_only_name_known_run_artifacts() -> None:
    known = {
        "TASK.md",
        "ROSTER.json",
        "STATE.json",
        "任务看板.md",
        "SPEC.md",
        "PLAN.md",
        "RESEARCH.md",
        "TASKS.json",
        "REVIEW-SPEC.md",
        "REVIEW.md",
        "TEST.md",
        "SUMMARY.md",
        "RETRO.md",
        "AUTHORITY.md",
        "RUN.log.md",
        "METRICS.md",
        "UI.md",
        "DATA.md",
        "SECURITY.md",
        "RELEASE.md",
        "DOCS.md",
        "DECISIONS.md",
    }
    assert set(PHASE_REQUIRED_ARTIFACTS) == set(PHASES)
    for phase, names in PHASE_REQUIRED_ARTIFACTS.items():
        assert set(names) <= known, phase


# ─────────────────────────────────────────────────────────────────────────────
# G10 — tier vocabulary
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("quick", "quick"),
        ("standard", "standard"),
        ("strict", "strict"),
        ("Quick", "quick"),
        ("  STRICT  ", "strict"),
        ("快速档", "quick"),
        ("标准档", "standard"),
        ("严格档", "strict"),
        ("快速", "quick"),
        ("标准", "standard"),
        ("严格", "strict"),
        ("quick档", "quick"),
        ("\u3000快速档\u3000", "quick"),
    ],
)
def test_normalize_tier_recognises_ids_labels_and_the_档_spelling(
    value: str, expected: str
) -> None:
    assert normalize_tier(value) == expected


def test_normalize_tier_treats_none_as_not_supplied() -> None:
    assert normalize_tier(None) == DEFAULT_TIER == "standard"


@pytest.mark.parametrize(
    "value", ["quickk", "", "   ", "fast", "档", 5, ["quick"], {"tier": "quick"}]
)
def test_normalize_tier_refuses_unknown_values_instead_of_defaulting(value: object) -> None:
    with pytest.raises(OctopError) as excinfo:
        normalize_tier(value)
    error = _assert_code(excinfo, ErrorCode.TEAM_TIER_INVALID)
    assert error.status == 400
    assert "快速档" in error.details["allowed"]


def test_tier_spec_keeps_the_authoritative_caps() -> None:
    assert TIERS == ("quick", "standard", "strict")
    assert set(TIER_ZH) == set(TIERS)
    assert TIER_SPEC["quick"].role_cap == 3
    assert TIER_SPEC["quick"].default_roles == ("pm", "backend", "qa")
    assert TIER_SPEC["quick"].acceptance_cap == 10
    assert TIER_SPEC["quick"].dispatch_cap == 15
    assert TIER_SPEC["quick"].independent_review is False
    assert TIER_SPEC["standard"].role_cap == 6
    assert TIER_SPEC["standard"].acceptance_cap == 30
    assert TIER_SPEC["standard"].dispatch_cap == 40
    assert TIER_SPEC["standard"].independent_review is True
    assert TIER_SPEC["strict"].role_cap == 12
    assert TIER_SPEC["strict"].acceptance_cap is None
    assert TIER_SPEC["strict"].dispatch_cap is None
    assert len(TIER_SPEC["strict"].default_roles) == 12


def test_quick_tier_trims_the_phase_sequence_and_keeps_clarify_and_deliver() -> None:
    assert phase_sequence("quick") == ("clarify", "implement", "test", "deliver")
    assert phase_sequence("快速档") == phase_sequence("quick")
    for tier in TIERS:
        assert "clarify" in phase_sequence(tier)
        assert "deliver" in phase_sequence(tier)


# ─────────────────────────────────────────────────────────────────────────────
# G2 / A2.2 / A2.5 — phase-order gate
# ─────────────────────────────────────────────────────────────────────────────


def test_advance_gate_refuses_a_skipped_phase_with_the_allowed_list() -> None:
    with pytest.raises(OctopError) as excinfo:
        advance_gate(_run(phase="clarify"), "implement")
    error = _assert_code(excinfo, ErrorCode.TEAM_RUN_PHASE_INVALID)
    assert error.status == 409
    assert error.details["allowed"] == ["research"], "SPEC A2.2 的 detail.allowed"


def test_advance_gate_allows_the_next_phase() -> None:
    assert advance_gate(_run(phase="clarify"), "research") == "research"


def test_advance_gate_refuses_an_unknown_target_phase() -> None:
    with pytest.raises(OctopError) as excinfo:
        advance_gate(_run(phase="clarify"), "plan-approval")
    _assert_code(excinfo, ErrorCode.TEAM_RUN_PHASE_INVALID)
    assert "方案确认" in PHASES, "the renamed target must stay unrecognised"


def test_advance_gate_refuses_a_terminal_run() -> None:
    for status in ("complete", "failed", "cancelled"):
        with pytest.raises(OctopError) as excinfo:
            advance_gate(_run(phase="review", status=status), "test")
        error = _assert_code(excinfo, ErrorCode.TEAM_RUN_TERMINAL)
        assert error.status == 409


def test_advance_gate_refuses_when_the_phase_artifact_is_missing() -> None:
    """A2.3 — delete SPEC.md, then clarify → research must be refused."""
    with pytest.raises(OctopError) as excinfo:
        advance_gate(_run(phase="clarify", present_artifacts=[]), "research")
    error = _assert_code(excinfo, ErrorCode.TEAM_PHASE_GATE_FAILED)
    assert error.status == 409
    assert error.details["missing"] == ["SPEC.md"]
    assert missing_artifacts(_run(present_artifacts=[])) == ("SPEC.md",)
    assert missing_artifacts(_run()) == ()


def test_advance_gate_allows_the_single_legal_rollback_once_then_escalates() -> None:
    """A2.5 / S3 — the only rollback is 方案确认 → design, at most once per run."""
    rollback = _run(phase="方案确认", rollback_count=0)
    assert advance_gate(rollback, "design") == "design"

    with pytest.raises(OctopError) as excinfo:
        advance_gate(_run(phase="方案确认", rollback_count=ROLLBACK_LIMIT), "design")
    error = _assert_code(excinfo, ErrorCode.TEAM_RUN_PHASE_INVALID)
    assert error.details["reason"] == "rollback_limit"
    assert error.details["escalate"] is True


@pytest.mark.parametrize("phase", ["spec-review", "implement", "review", "test", "deliver"])
def test_advance_gate_refuses_every_other_rollback(phase: str) -> None:
    """``design`` is forward from research, so only genuinely backwards moves count."""
    with pytest.raises(OctopError) as excinfo:
        advance_gate(
            _run(phase=phase, present_artifacts=list(PHASE_REQUIRED_ARTIFACTS[phase])), "design"
        )
    _assert_code(excinfo, ErrorCode.TEAM_RUN_PHASE_INVALID)


def test_advance_gate_follows_the_quick_tier_sequence() -> None:
    quick = _run(tier="quick", phase="clarify", spec_text=_SPEC_FILLED)
    assert advance_gate(quick, "implement") == "implement"
    with pytest.raises(OctopError) as excinfo:
        advance_gate(quick, "research")
    _assert_code(excinfo, ErrorCode.TEAM_RUN_PHASE_INVALID)


# ─────────────────────────────────────────────────────────────────────────────
# G3 — confirmation gate
# ─────────────────────────────────────────────────────────────────────────────


def test_decision_gate_refuses_a_pending_decision() -> None:
    with pytest.raises(OctopError) as excinfo:
        decision_gate(_run(phase="方案确认", pending_decision={"id": "d1", "kind": "escalate"}))
    error = _assert_code(excinfo, ErrorCode.TEAM_DECISION_PENDING)
    assert error.status == 409
    assert error.details["decision_id"] == "d1"


def test_decision_gate_passes_when_there_is_no_open_decision() -> None:
    decision_gate(_run(phase="方案确认"))
    decision_gate(_run(phase="方案确认", pending_decision={"id": "d1", "status": "resolved"}))


def test_advance_to_implement_is_refused_until_the_decision_is_resolved() -> None:
    blocked = _run(
        phase="方案确认",
        pending_decision={"id": "d1", "kind": "clarify"},
        spec_text=_SPEC_FILLED,
    )
    with pytest.raises(OctopError) as excinfo:
        advance_gate(blocked, "implement")
    _assert_code(excinfo, ErrorCode.TEAM_DECISION_PENDING)

    resolved = _run(
        phase="方案确认",
        pending_decision={"id": "d1", "status": "resolved"},
        spec_text=_SPEC_FILLED,
    )
    assert advance_gate(resolved, "implement") == "implement"


# ─────────────────────────────────────────────────────────────────────────────
# G4 — spec-boundary gate
# ─────────────────────────────────────────────────────────────────────────────


def test_spec_boundary_state_classifies_filled_empty_and_missing() -> None:
    assert spec_boundary_state(_SPEC_FILLED) is SpecBoundaryState.FILLED
    assert spec_boundary_state(_SPEC_EMPTY) is SpecBoundaryState.EMPTY
    assert spec_boundary_state("# SPEC\n\n## 目标\n\n正文\n") is SpecBoundaryState.MISSING
    assert spec_boundary_state("") is SpecBoundaryState.MISSING
    assert spec_boundary_state(None) is SpecBoundaryState.MISSING


def test_spec_boundary_state_stops_at_the_next_heading() -> None:
    text = "## 边界与禁止项\n\n| 码名 |\n|---|\n|  |\n\n## 后面的表\n\n| a |\n|---|\n| b |\n"
    assert spec_boundary_state(text) is SpecBoundaryState.EMPTY


def test_advance_to_implement_is_refused_while_the_boundary_table_is_empty() -> None:
    for text in (_SPEC_EMPTY, "", None, "# SPEC\n\n## 目标\n"):
        with pytest.raises(OctopError) as excinfo:
            advance_gate(_run(phase="方案确认", spec_text=text), "implement")
        _assert_code(excinfo, ErrorCode.TEAM_SPEC_BOUNDARY_EMPTY)


def test_advance_to_implement_fails_closed_when_the_spec_text_is_absent() -> None:
    """No ``spec_text`` key at all is not evidence of a filled table (G4 is hard)."""
    run = _run(phase="方案确认")
    assert "spec_text" not in run
    with pytest.raises(OctopError) as excinfo:
        advance_gate(run, "implement")
    error = _assert_code(excinfo, ErrorCode.TEAM_SPEC_BOUNDARY_EMPTY)
    assert error.details["state"] == "missing"


def test_advance_to_implement_passes_with_a_filled_boundary_table() -> None:
    assert advance_gate(_run(phase="方案确认", spec_text=_SPEC_FILLED), "implement") == "implement"


# ─────────────────────────────────────────────────────────────────────────────
# G9 — capacity gate and roster trimming
# ─────────────────────────────────────────────────────────────────────────────


def test_assert_capacity_refuses_the_fourth_member_on_the_quick_tier() -> None:
    with pytest.raises(OctopError) as excinfo:
        assert_capacity({"tier": "quick"}, member_count=4)
    error = _assert_code(excinfo, ErrorCode.TEAM_RUN_MEMBER_LIMIT)
    assert error.status == 409
    assert error.details == {"tier": "quick", "limit": 3, "count": 4}


def test_assert_capacity_passes_at_the_cap_and_below() -> None:
    assert_capacity({"tier": "quick"}, member_count=3)
    assert_capacity({"tier": "standard"}, member_count=6)
    assert_capacity({"tier": "strict"}, member_count=12)


def test_assert_capacity_refuses_tasks_over_the_tier_cap() -> None:
    with pytest.raises(OctopError) as excinfo:
        assert_capacity({"tier": "quick"}, task_count=16)
    error = _assert_code(excinfo, ErrorCode.TEAM_RUN_TASK_LIMIT)
    assert error.status == 409
    assert error.details["limit"] == 15
    assert_capacity({"tier": "standard"}, task_count=40)
    assert_capacity({"tier": "strict"}, task_count=10_000)


def test_assert_capacity_accepts_a_chinese_tier_label() -> None:
    with pytest.raises(OctopError) as excinfo:
        assert_capacity({"tier": "快速档"}, member_count=4)
    _assert_code(excinfo, ErrorCode.TEAM_RUN_MEMBER_LIMIT)


def test_trim_roster_keeps_the_lead_and_the_default_roles() -> None:
    roster = [
        {"agent_id": "m0", "role": "frontend"},
        {"agent_id": "m1", "role": "docs"},
        {"agent_id": "m2", "role": "backend"},
        {"agent_id": "m3", "role": "qa"},
        {"agent_id": "m4", "role": "pm"},
    ]
    trimmed = trim_roster(roster, "quick", lead_agent_id="m2")
    assert [m["agent_id"] for m in trimmed.kept] == ["m2", "m3", "m4"]
    assert trimmed.skipped_roles == ("frontend", "docs")


def test_trim_roster_never_cuts_the_team_host() -> None:
    """Rule ① beats everything; rule ③ then keeps manifest order (docs before frontend)."""
    roster = [
        {"agent_id": "m0", "role": "docs"},
        {"agent_id": "host", "role": "ui"},
        {"agent_id": "m2", "role": "backend"},
        {"agent_id": "m3", "role": "frontend"},
    ]
    trimmed = trim_roster(roster, "quick", host_agent_id="host")
    assert [m["agent_id"] for m in trimmed.kept] == ["m0", "host", "m2"]
    assert "host" in {m["agent_id"] for m in trimmed.kept}
    assert trimmed.skipped_roles == ("frontend",)


def test_trim_roster_is_a_no_op_at_or_below_the_cap() -> None:
    roster = [{"agent_id": "m0", "role": "pm"}, {"agent_id": "m1", "role": "backend"}]
    trimmed = trim_roster(roster, "quick")
    assert trimmed.kept == tuple(roster)
    assert trimmed.skipped == ()


# ─────────────────────────────────────────────────────────────────────────────
# G6 — contract-freeze gate: four hard graph invariants
# ─────────────────────────────────────────────────────────────────────────────


def test_graph_codes_are_the_four_authoritative_values() -> None:
    assert GRAPH_CODES == ("missing-id", "duplicate-id", "self-dependency", "cycle")


def test_validate_task_graph_accepts_a_dag() -> None:
    assert (
        validate_task_graph(
            [
                {"id": "a", "dependsOn": []},
                {"id": "b", "dependsOn": ["a"]},
                {"id": "c", "dependsOn": ["a", "b"]},
            ]
        )
        is None
    )


def test_validate_task_graph_reports_a_task_without_an_id() -> None:
    with pytest.raises(OctopError) as excinfo:
        validate_task_graph([{"id": "a"}, {"dependsOn": []}])
    error = _assert_code(excinfo, ErrorCode.TEAM_TASK_GRAPH_INVALID)
    assert error.status == 409
    assert error.details["code"] == "missing-id"


def test_validate_task_graph_reports_a_missing_dependency() -> None:
    with pytest.raises(OctopError) as excinfo:
        validate_task_graph([{"id": "a", "dependsOn": ["b"]}])
    error = _assert_code(excinfo, ErrorCode.TEAM_TASK_GRAPH_INVALID)
    assert error.details["code"] == "missing-id"
    assert error.details["missing"] == ["b"]
    assert error.details["path"] == ["a", "b"]


def test_validate_task_graph_reports_a_duplicate_id() -> None:
    with pytest.raises(OctopError) as excinfo:
        validate_task_graph([{"id": "a"}, {"id": "a", "dependsOn": []}])
    error = _assert_code(excinfo, ErrorCode.TEAM_TASK_GRAPH_INVALID)
    assert error.details["code"] == "duplicate-id"
    assert error.details["path"] == ["a"]


def test_validate_task_graph_reports_a_self_dependency_before_calling_it_a_cycle() -> None:
    with pytest.raises(OctopError) as excinfo:
        validate_task_graph([{"id": "a", "dependsOn": ["a"]}])
    error = _assert_code(excinfo, ErrorCode.TEAM_TASK_GRAPH_INVALID)
    assert error.details["code"] == "self-dependency"


def test_validate_task_graph_reports_the_concrete_cycle_path() -> None:
    with pytest.raises(OctopError) as excinfo:
        validate_task_graph(
            [
                {"id": "a", "dependsOn": ["b"]},
                {"id": "b", "dependsOn": ["c"]},
                {"id": "c", "dependsOn": ["a"]},
            ]
        )
    error = _assert_code(excinfo, ErrorCode.TEAM_TASK_GRAPH_INVALID)
    assert error.details["code"] == "cycle"
    path = error.details["path"]
    assert path[0] == path[-1], f"cycle path must close: {path}"
    assert set(path) == {"a", "b", "c"}


def test_validate_task_graph_finds_a_cycle_that_does_not_start_at_the_first_task() -> None:
    with pytest.raises(OctopError) as excinfo:
        validate_task_graph(
            [
                {"id": "root", "dependsOn": []},
                {"id": "x", "dependsOn": ["y"]},
                {"id": "y", "dependsOn": ["x"]},
            ]
        )
    error = _assert_code(excinfo, ErrorCode.TEAM_TASK_GRAPH_INVALID)
    assert error.details["code"] == "cycle"
    assert error.details["path"][0] == error.details["path"][-1]


# ─────────────────────────────────────────────────────────────────────────────
# G16 — finding reopen (detection + forced escalation)
# ─────────────────────────────────────────────────────────────────────────────


def test_norm_title_ignores_the_finding_id_severity_case_and_whitespace() -> None:
    assert norm_title("FIND-24（P2）：grep 断言自证不可通过") == norm_title(
        "find-31 (p1)  grep   断言自证不可通过"
    )
    assert norm_title("FIND-24：a") != norm_title("FIND-24：b")


def _rounds(*entries: tuple[int, str, str]) -> list[dict[str, object]]:
    return [
        {"round": number, "findings": [title], "verdict": verdict}
        for number, title, verdict in entries
    ]


def test_finding_reopened_detects_the_same_title_in_adjacent_non_pass_rounds() -> None:
    reopened = finding_reopened(
        {
            "finding_rounds": _rounds(
                (1, "FIND-24：grep 断言自证不可通过", "needs_revision"),
                (2, "FIND-31：grep 断言自证不可通过", "reject"),
            )
        }
    )
    assert reopened is not None
    assert reopened.rounds == (1, 2)
    assert reopened.title == norm_title("FIND-24：grep 断言自证不可通过")


def test_finding_reopened_is_not_reported_for_genuine_convergence() -> None:
    assert (
        finding_reopened(
            {
                "finding_rounds": _rounds(
                    (1, "FIND-24：a", "needs_revision"),
                    (2, "FIND-25：a", "pass"),
                )
            }
        )
        is None
    )
    assert (
        finding_reopened(
            {
                "finding_rounds": _rounds(
                    (1, "FIND-24：a", "needs_revision"),
                    (2, "FIND-25：b", "needs_revision"),
                )
            }
        )
        is None
    )


def test_finding_reopened_cannot_be_told_from_no_input_without_the_marker() -> None:
    assert finding_reopened({}) is None
    assert finding_reopened({"finding_rounds": []}) is None
    report = check_run({})
    assert V_FINDING_REOPENED_INPUT_MISSING in report.violations
    assert V_FINDING_REOPENED_INPUT_MISSING not in check_run({"finding_rounds": []}).violations


def test_advance_gate_blocks_a_reopened_finding_and_asks_for_an_escalation() -> None:
    run = _run(
        phase="review",
        present_artifacts=["REVIEW.md"],
        finding_rounds=_rounds(
            (1, "FIND-24：grep 断言自证不可通过", "needs_revision"),
            (2, "FIND-31：grep 断言自证不可通过", "needs_revision"),
        ),
    )
    with pytest.raises(OctopError) as excinfo:
        advance_gate(run, "test")
    error = _assert_code(excinfo, ErrorCode.TEAM_FINDING_REOPENED)
    assert error.status == 409
    assert error.details["rounds"] == [1, 2]
    assert error.details["decision"] == {"kind": "escalate", "reason": "finding_reopened"}


# ─────────────────────────────────────────────────────────────────────────────
# V1/V3/V4 — read-side report (reports, never blocks)
# ─────────────────────────────────────────────────────────────────────────────


def _report_keys(run: dict[str, object]) -> set[str]:
    return set(check_run(run).violations)


def test_check_run_reports_an_unregistered_kind() -> None:
    assert V_KIND_UNKNOWN in _report_keys({"tasks": [{"id": "a", "kind": "whatever"}]})
    assert V_KIND_UNKNOWN not in _report_keys({"tasks": [{"id": "a", "kind": ALLOWED_KINDS[0]}]})


def test_check_run_reports_a_quality_task_owned_by_the_wrong_role() -> None:
    task = {"id": "a", "kind": "quality", "role": "backend"}
    assert V_QUALITY_OWNER_INVALID in _report_keys({"tasks": [task]})
    assert V_QUALITY_OWNER_INVALID not in _report_keys(
        {"tasks": [{"id": "a", "kind": "quality", "role": "reviewer"}]}
    )


def test_check_run_reports_a_done_task_whose_verify_never_ran() -> None:
    task = {"id": "a", "kind": "implementation", "status": "done", "verify": ["pytest -q"]}
    assert V_VERIFY_MISSING in _report_keys({"tasks": [task]})
    assert V_VERIFY_MISSING not in _report_keys(
        {"tasks": [{**task, "verifiedAt": "2026-09-29T00:00:00Z"}]}
    )
    assert V_VERIFY_MISSING not in _report_keys(
        {"tasks": [{"id": "a", "kind": "implementation", "status": "todo", "verify": ["pytest"]}]}
    )


def test_check_run_reports_a_round_over_the_limit_that_was_never_escalated() -> None:
    run: dict[str, object] = {
        "max_review_rounds": 3,
        "finding_rounds": _rounds((4, "FIND-1：x", "needs_revision")),
    }
    assert V_REWORK_LOOP_UNESCALATED in _report_keys(run)
    assert V_REWORK_LOOP_UNESCALATED not in _report_keys({**run, "escalated": True})


def test_check_run_reports_a_started_task_with_unfinished_dependencies() -> None:
    tasks = [
        {"id": "a", "kind": "implementation", "status": "doing"},
        {"id": "b", "kind": "implementation", "status": "doing", "dependsOn": ["a"]},
    ]
    assert V_CONTRACT_DEP_STALLED in _report_keys({"tasks": tasks})
    finished = [tasks[0], {**tasks[1]}]
    finished[0] = {**tasks[0], "status": "done"}
    assert V_CONTRACT_DEP_STALLED not in _report_keys({"tasks": finished})


def test_check_run_never_raises_on_a_broken_board() -> None:
    report = check_run(
        {
            "tasks": [
                {"id": "a", "kind": "whatever"},
                {"id": "b", "kind": "quality", "role": "backend"},
                {"kind": "implementation"},
            ]
        }
    )
    assert report.has(V_KIND_UNKNOWN)
    assert report.has(V_QUALITY_OWNER_INVALID)
    assert report.violations == tuple(dict.fromkeys(report.violations))


# ─────────────────────────────────────────────────────────────────────────────
# Module discipline — pure functions, zero IO, no DB
# ─────────────────────────────────────────────────────────────────────────────


def test_pipeline_module_imports_no_io_or_db_dependency() -> None:
    source = _PIPELINE_PATH.read_text(encoding="utf-8")
    imported = {
        match.group(1).split(".")[0]
        for match in re.finditer(r"^\s*(?:from|import)\s+([A-Za-z_][\w.]*)", source, re.MULTILINE)
    }
    assert imported <= {"__future__", "re", "collections", "dataclasses", "enum", "typing", "octop"}
    assert "octop.infra.db" not in source
    assert "octop.infra.agents.memory" not in source


def test_pipeline_public_gates_are_pure_over_their_input() -> None:
    run = _run(phase="clarify")
    before = dict(run)
    advance_gate(run, "research")
    check_run(run)
    trim_roster([{"agent_id": "m0", "role": "pm"}], "quick")
    assert run == before, "gates must not mutate the snapshot they are given"
