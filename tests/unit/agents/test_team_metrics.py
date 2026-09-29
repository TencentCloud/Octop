"""``teams.metrics`` -- the 12-section METRICS snapshot (T-30).

The section **titles** are asserted verbatim against the upstream renderer's list, so a
rename here fails loudly rather than drifting from `lib/metrics/render.js`. The token
section is asserted on the *three-state* rule: a missing metric must never become ``0``.
"""

from __future__ import annotations

from octop.infra.agents.teams.metrics import (
    FIRST_RUNNABLE_THRESHOLD_S,
    NO_TOKEN_METRIC,
    PROVIDER_OMITS,
    SECTION_TITLES,
    RollupSources,
    TokenCell,
    rollup,
)

# Verbatim from lib/metrics/render.js (titles at @ 30/42/48/54/58/62/66/70/74/80/87/95).
UPSTREAM_TITLES = (
    "总览",
    "阶段覆盖",
    "首产物（首个可运行产物耗时）",
    "收尾预算（实现期 = 首产物→冻结 · 收尾 = 冻结→交付）",
    "角色结果（pass=交付 / rework=返工件 / fail=失败）",
    "未闭环（不计入返工率，但必须可见）",
    "高频卡点（error / 返工，去重）",
    "用户高频提问（ask，去重）",
    "决策记录（decision，去重）",
    "单源化总扫（见一个，扫全部）",
    "评审效率（轮次 / 撤销率）",
    "token 成本与上下文峰值",
)


def _event(action: str, at: int, **payload: object) -> dict[str, object]:
    return {"action": action, "at": at, "payload": payload}


def _usage(**over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "input_tokens": 100,
        "uncached_input_tokens": 40,
        "cache_read_tokens": 700,
        "cache_write_tokens": 0,
        "output_tokens": 25,
        "model_calls": 7,
    }
    base.update(over)
    return base


def test_there_are_exactly_twelve_sections_and_the_titles_are_verbatim() -> None:
    assert SECTION_TITLES == UPSTREAM_TITLES
    assert len(SECTION_TITLES) == 12
    assert [title for title, _ in rollup(RollupSources()).sections] == list(UPSTREAM_TITLES)


def test_header_and_all_twelve_headings_are_rendered() -> None:
    text = rollup(RollupSources()).render()
    assert text.startswith("# 团队指标（METRICS）\n")
    for title in UPSTREAM_TITLES:
        assert f"## {title}\n" in text


def test_rendering_is_idempotent() -> None:
    src = RollupSources(
        events=[_event("run.created", 1_000), _event("run.artifact_written", 1_060)],
        tasks=[{"status": "done", "round": 1, "verdict": None, "kind": "work"}],
    )
    assert rollup(src).render() == rollup(src).render()


def test_overview_denominator_is_runs_with_logs() -> None:
    src = RollupSources(
        events=[_event("run.created", 10)],
        tasks=[{"status": "done", "round": 3, "verdict": None, "kind": "work"}],
    )
    overview = dict(rollup(src).sections)["总览"]
    body = "\n".join(overview)
    # reworkRuns=1 (round>1), runsWithLogs=1 -> 100%, and the line names the denominator.
    assert "返工/失败率：100%（= 1/1" in body
    assert "分母是「有日志的 run」而非全部 run" in body


def test_a_run_without_events_has_a_zero_denominator_not_a_division_error() -> None:
    body = "\n".join(dict(rollup(RollupSources()).sections)["总览"])
    assert "有日志的 run：0" in body
    assert "返工/失败率：0%（= 0/0" in body


def test_phase_coverage_tallies_and_states_the_empty_case() -> None:
    empty = "\n".join(dict(rollup(RollupSources()).sections)["阶段覆盖"])
    assert "一个都还没写过" in empty
    src = RollupSources(
        events=[
            _event("run.phase_advanced", 1, to="design"),
            _event("run.phase_advanced", 2, to="design"),
            _event("run.phase_advanced", 3, to="implement"),
        ]
    )
    body = "\n".join(dict(rollup(src).sections)["阶段覆盖"])
    assert "- `design`: 2 次" in body
    assert "- `implement`: 1 次" in body
    assert body.index("`design`") < body.index("`implement`")


def test_first_runnable_uses_the_upstream_ten_minute_threshold() -> None:
    assert FIRST_RUNNABLE_THRESHOLD_S == 600
    inside = RollupSources(events=[_event("run.created", 0), _event("run.artifact_written", 599)])
    body = "\n".join(dict(rollup(inside).sections)["首产物（首个可运行产物耗时）"])
    assert "599 秒（在阈值内" in body
    outside = RollupSources(events=[_event("run.created", 0), _event("run.artifact_written", 601)])
    body = "\n".join(dict(rollup(outside).sections)["首产物（首个可运行产物耗时）"])
    assert "601 秒（超过阈值" in body


def test_first_runnable_marks_the_proxy_semantics_as_open() -> None:
    src = RollupSources(events=[_event("run.created", 0), _event("run.artifact_written", 5)])
    body = "\n".join(dict(rollup(src).sections)["首产物（首个可运行产物耗时）"])
    assert "待收口" in body, "the first-runnable proxy must stay visibly unaligned"


def test_role_results_only_count_verdict_tokens_never_prose() -> None:
    src = RollupSources(
        events=[
            _event("run.verdict", 1, role="reviewer", verdict="pass"),
            _event("run.verdict", 2, role="reviewer", verdict="needs_revision"),
            _event("run.verdict", 3, role="reviewer", verdict="looks good to me"),
            _event("run.verdict", 4, role="qa", verdict="reject"),
        ]
    )
    body = "\n".join(
        dict(rollup(src).sections)["角色结果（pass=交付 / rework=返工件 / fail=失败）"]
    )
    assert "- `reviewer:pass`: 1 次" in body
    assert "- `reviewer:needs_revision`: 1 次" in body
    assert "- `qa:reject`: 1 次" in body
    assert "looks good" not in body, "prose verdicts must never be counted"


def test_role_results_empty_state_says_prose_is_ignored() -> None:
    src = RollupSources(events=[_event("run.verdict", 1, role="reviewer", verdict="lgtm")])
    body = "\n".join(
        dict(rollup(src).sections)["角色结果（pass=交付 / rework=返工件 / fail=失败）"]
    )
    assert "无判决事件" in body
    assert "散文判决一律不计" in body


def test_open_loops_counts_tasks_and_findings() -> None:
    src = RollupSources(
        tasks=[
            {"status": "done", "round": 1, "verdict": None, "kind": "work"},
            {"status": "in_progress", "round": 1, "verdict": None, "kind": "work"},
        ],
        findings=[{"status": "open", "round": 1}, {"status": "fixed", "round": 1}],
    )
    body = "\n".join(dict(rollup(src).sections)["未闭环（不计入返工率，但必须可见）"])
    assert "未完成任务：1" in body
    assert "未闭环 finding：1" in body


def test_sections_without_a_producer_stay_visible_and_flag_open_items() -> None:
    """Gaps must be *loud*: no silent section, and a 待收口 marker."""
    sections = dict(rollup(RollupSources()).sections)
    for title in (
        "高频卡点（error / 返工，去重）",
        "用户高频提问（ask，去重）",
        "单源化总扫（见一个，扫全部）",
        "评审效率（轮次 / 撤销率）",
    ):
        body = "\n".join(sections[title])
        assert "待收口" in body, title
        assert body.strip() != "", title


def test_decisions_are_deduplicated_by_id() -> None:
    src = RollupSources(
        events=[
            _event("run.decision_raised", 1, id="d1"),
            _event("run.decision_raised", 2, id="d1"),
            _event("run.decision_raised", 3, id="d2"),
            _event("run.decision_resolved", 4, id="d1"),
        ]
    )
    body = "\n".join(dict(rollup(src).sections)["决策记录（decision，去重）"])
    assert "决策（去重）：2 条" in body
    assert "已解决：1" in body


# ── section 12: the three-state rule ─────────────────────────────────────────


def test_token_cell_refuses_a_value_state_without_a_number() -> None:
    import pytest

    with pytest.raises(ValueError):
        TokenCell("in", state="value").render()


def test_token_section_honours_the_three_states() -> None:
    body = "\n".join(dict(rollup(RollupSources(usage=_usage())).sections)["token 成本与上下文峰值"])
    assert "- in：140" in body  # input + uncached, per PLAN §指标口径
    assert "- out：25" in body
    assert "- steps：7" in body
    assert PROVIDER_OMITS in body, "cache_write == 0 means 'provider omits', not a value"
    assert NO_TOKEN_METRIC in body


def test_token_section_never_fabricates_zero_for_peak_or_first() -> None:
    body = "\n".join(dict(rollup(RollupSources(usage=_usage())).sections)["token 成本与上下文峰值"])
    assert "- peak：0" not in body, "peak is not in usage_log -- 0 would read as 'cheap'"
    assert "- first：0" not in body
    assert f"- peak：{NO_TOKEN_METRIC}" in body
    assert f"- first（TTFT）：{NO_TOKEN_METRIC}" in body


def test_token_section_without_any_usage_row_is_all_empty_states() -> None:
    body = "\n".join(dict(rollup(RollupSources()).sections)["token 成本与上下文峰值"])
    assert NO_TOKEN_METRIC in body
    for fabricated in ("- in：0", "- out：0", "- steps：0"):
        assert fabricated not in body, fabricated
    assert "PG 侧**未验证**" in body


def test_token_section_states_the_three_state_rule_and_the_pg_boundary() -> None:
    body = "\n".join(dict(rollup(RollupSources(usage=_usage())).sections)["token 成本与上下文峰值"])
    assert "禁止用 0 表示「没有数据」" in body
    assert "不得声称 PG 已证" in body


def test_steps_is_model_calls_not_trajectory_steps() -> None:
    """``steps`` must stay ``usage_log.model_calls`` -- a different unit from trajectory events."""
    body = "\n".join(
        dict(rollup(RollupSources(usage=_usage(model_calls=214))).sections)[
            "token 成本与上下文峰值"
        ]
    )
    assert "- steps：214" in body


def test_module_has_no_module_level_metrics_import() -> None:
    """``infra/metrics`` must not be imported eagerly (AGENTS.md §7)."""
    from pathlib import Path

    source = Path("src/octop/infra/agents/teams/metrics.py").read_text(encoding="utf-8")
    for line in source.splitlines():
        assert not line.startswith("from octop.infra.metrics"), line
        assert not line.startswith("import octop.infra.metrics"), line


def test_module_reads_no_clock_and_no_randomness() -> None:
    """Time must come from rows, never from "now" -- otherwise the snapshot is not a
    function of the state and two exports can differ (the discipline `pm` showed in T-14:
    ban ``now/utcnow/time/today/uuid*/random`` with AST, not with a grep)."""
    import ast
    from pathlib import Path

    tree = ast.parse(Path("src/octop/infra/agents/teams/metrics.py").read_text(encoding="utf-8"))
    banned = {"time", "datetime", "uuid", "random", "secrets"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] not in banned, alias.name
        elif isinstance(node, ast.ImportFrom):
            assert (node.module or "").split(".")[0] not in banned, node.module
        # ``now()`` / ``today()`` reached through any object are banned too.
        elif isinstance(node, ast.Attribute):
            assert node.attr not in {"now", "utcnow", "today"}, node.attr
