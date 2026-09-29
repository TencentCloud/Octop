"""Run events -> the 12 upstream METRICS sections (T-30).

Section titles are **verbatim** from the upstream renderer
(``lib/metrics/render.js · renderMetrics @ 19``, titles at ``@ 30/42/48/54/58/62/66/70/74/80/87/95``);
so are the two time windows and the rework denominator:

* ``summarizeFirstRunnable @ 66`` -- ``first-runnable - run:started``, threshold **600 s**;
* ``summarizeClosingBudget @ 153`` -- implementation = first artifact -> freeze, closing =
  freeze -> deliver, red line **0.5**;
* ``reworkRate = round(reworkRuns / runsWithLogs * 100)`` -- the denominator is
  **runs with logs**, not all runs (``command.js @ 5481``).

Octop sources: ``timeline_events`` written by ``run_service`` (13-action vocabulary),
``project_tasks``, ``project_task_findings`` and ``usage_log``.

Honesty rules (PLAN §指标口径 + SPEC assumption A-12):

* a section whose upstream event family **has no Octop producer yet** renders an
  explicit "（…还没写过）" line -- never a silent empty line, and **never a fabricated 0**
  (a 0 reads as "this was cheap", which is the failure mode upstream calls out at
  ``render.js`` section 11/12);
* section 12 distinguishes **three** states -- ``VALUE`` / ``NO_TOKEN_METRIC`` /
  ``PROVIDER_OMITS`` -- and only the first may print a number;
* ``steps`` is ``usage_log.model_calls`` and must **not** be swapped for
  ``TrajectoryMetrics.steps`` (different unit; swapping creates a second definition of
  "steps").

``infra/metrics.py`` is deliberately **untouched**: the 12 sections are an on-demand
snapshot computed from rows, so they need no new in-process counters.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Literal

from octop.infra.db.repos._base import DbRow

#: Verbatim section titles from the upstream renderer (``render.js @ 30..@ 95``).
SECTION_TITLES: tuple[str, ...] = (
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

FIRST_RUNNABLE_THRESHOLD_S = 600
CLOSING_BUDGET_RED_LINE = 0.5

TokenState = Literal["value", "no_token_metric", "provider_omits"]

#: The three states, and the only wording allowed for the two empty ones.
NO_TOKEN_METRIC = "暂无 token 口径"
PROVIDER_OMITS = "该 provider 不回填"


@dataclass(frozen=True)
class TokenCell:
    """One token figure: a number **or** one of the two honest empty states."""

    name: str
    value: int | None = None
    state: TokenState = "value"

    def render(self) -> str:
        if self.state == "value":
            if self.value is None:
                raise ValueError(f"{self.name}: state=value requires a number")
            return f"- {self.name}：{self.value}"
        if self.state == "provider_omits":
            return f"- {self.name}：{PROVIDER_OMITS}（列存在但该 provider 从不回填）"
        return f"- {self.name}：{NO_TOKEN_METRIC}（{PROVIDER_OMITS} 之外的第二种空态）"


@dataclass
class RollupSources:
    """Everything the rollup reads, injected so the module stays repo-agnostic."""

    events: list[DbRow] = field(default_factory=list)
    tasks: list[DbRow] = field(default_factory=list)
    findings: list[DbRow] = field(default_factory=list)
    usage: DbRow | None = None


def _payload(raw: object) -> dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        decoded = json.loads(str(raw))
    except ValueError:
        return {}
    return decoded if isinstance(decoded, dict) else {}


def _actions(events: list[DbRow]) -> list[tuple[str, int, dict[str, Any]]]:
    out: list[tuple[str, int, dict[str, Any]]] = []
    for e in events:
        at = e["at"]
        out.append((str(e["action"]), int(at) if at is not None else 0, _payload(e["payload"])))
    return sorted(out, key=lambda item: item[1])


def _tally_lines(counts: dict[str, int], empty: str) -> str:
    if not counts:
        return f"- （{empty}）"
    return "\n".join(
        f"- `{key}`: {value} 次"
        for key, value in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    )


def _verdict_token(payload: dict[str, Any]) -> str | None:
    """Only a ``verdict=`` token counts -- prose verdicts are ignored (upstream
    ``verdictFromToken @ 128`` never falls back to prose)."""
    raw = payload.get("verdict")
    if raw is None:
        return None
    token = str(raw).strip().lower()
    return token if token in {"pass", "needs_revision", "reject"} else None


def _rework_runs(tasks: list[DbRow], findings: list[DbRow]) -> int:
    """A run reworked if any task went past round 1, was rejected, or is a repair task."""
    for t in tasks:
        if int(t["round"] or 1) > 1:
            return 1
        if str(t["verdict"] or "") in {"needs_revision", "reject"}:
            return 1
        if str(t["kind"] or "") == "repair":
            return 1
    for f in findings:
        if int(f["round"] or 1) > 1:
            return 1
    return 0


def _overview(src: RollupSources) -> list[str]:
    stepped = _actions(src.events)
    runs_with_logs = 1 if stepped else 0
    rework_runs = _rework_runs(src.tasks, src.findings)
    rate = round((rework_runs / runs_with_logs) * 100) if runs_with_logs else 0
    completed = sum(1 for t in src.tasks if str(t["status"]) in {"done", "completed"})
    return [
        "- 总 run 数：1（本聚合以单个 run 为单位）",
        "- 非 run 条目（无事件、无任务的目录，未计入）：0 个",
        f"- 已完成：{completed}",
        f"- 有日志的 run：{runs_with_logs}",
        f"- 返工/失败率：{rate}%（= {rework_runs}/{runs_with_logs}，"
        "分母是「有日志的 run」而非全部 run）",
        "- 返工判定口径（多源，可审计）：`project_tasks.round > 1` 或 "
        "`verdict ∈ {needs_revision, reject}` 或 `kind = repair`，"
        "或 `project_task_findings.round > 1`（对齐上游 "
        "`TASKS.json` 的 repair/round/verdict 多源判定）",
    ]


def _phase_coverage(src: RollupSources) -> list[str]:
    counts: dict[str, int] = {}
    for action, _at, payload in _actions(src.events):
        if action == "run.phase_advanced":
            counts[str(payload.get("to") or payload.get("phase") or "unknown")] = (
                counts.get(str(payload.get("to") or payload.get("phase") or "unknown"), 0) + 1
            )
    return _tally_lines(counts, "无阶段推进事件：`run.phase_advanced` 一个都还没写过").split("\n")


def _first_runnable(src: RollupSources) -> list[str]:
    stepped = _actions(src.events)
    started = next((at for action, at, _ in stepped if action == "run.created"), None)
    first_artifact = next(
        (at for action, at, _ in stepped if action == "run.artifact_written"), None
    )
    if started is None:
        return ["- （无 `run.created` 事件：这个 run 还没被 run_service 建过）"]
    if first_artifact is None:
        return [
            "- （无 `run.artifact_written` 事件：首个产物还没落过）",
            f"- 阈值口径：{FIRST_RUNNABLE_THRESHOLD_S} 秒（上游 "
            "`summarizeFirstRunnable @ 66`），暂无样本可判",
        ]
    delta = max(0, first_artifact - started)
    verdict = "在阈值内" if delta <= FIRST_RUNNABLE_THRESHOLD_S else "超过阈值"
    return [
        f"- 首产物耗时：{delta} 秒（{verdict}，阈值 {FIRST_RUNNABLE_THRESHOLD_S} 秒）",
        "- ⚠️ **待收口**：上游的 `first-runnable` 是**独立事件族**（「首个**可运行**产物」），"
        "Octop 词汇表里只有 `run.artifact_written`（任何产物）⇒ 上值以「首个产物」代理，"
        "**语义未对齐**，等词汇表补 `first-runnable` 后收紧",
    ]


def _closing_budget(src: RollupSources) -> list[str]:
    stepped = _actions(src.events)
    first_artifact = next(
        (at for action, at, _ in stepped if action == "run.artifact_written"), None
    )
    first_verdict = next((at for action, at, _ in stepped if action == "run.verdict"), None)
    delivered = next(
        (
            at
            for action, at, payload in stepped
            if action == "run.phase_advanced"
            and str(payload.get("to") or "") in {"交付", "deliver"}
        ),
        None,
    )
    lines: list[str] = []
    if first_artifact is None or first_verdict is None:
        lines.append(
            "- （样本不足：需要 `run.artifact_written` 与 `run.verdict` 两个事件才算得出实现期）"
        )
    else:
        lines.append(f"- 实现期（首产物 → 首个判决）：{max(0, first_verdict - first_artifact)} 秒")
    if first_verdict is None or delivered is None:
        lines.append("- （样本不足：收尾期需要 `run.verdict` 与「交付」阶段推进）")
    else:
        lines.append(f"- 收尾期（首个判决 → 交付）：{max(0, delivered - first_verdict)} 秒")
    lines.append(
        f"- 红线：收尾占比 > {CLOSING_BUDGET_RED_LINE:g} 报警（上游 `summarizeClosingBudget @ 153`）"
    )
    lines.append(
        "- ⚠️ **待收口**：上游的「冻结」标记在 Octop 词汇表里**没有对应事件** ⇒ 本节的"
        "「实现期/收尾期」以 `首个产物 / 首个判决 / 交付阶段` 代理，**分界语义未对齐**"
    )
    return lines


def _role_results(src: RollupSources) -> list[str]:
    counts: dict[str, int] = {}
    for action, _at, payload in _actions(src.events):
        if action != "run.verdict":
            continue
        token = _verdict_token(payload)
        if token is None:
            continue  # prose verdicts never count
        role = str(payload.get("role") or "unknown")
        counts[f"{role}:{token}"] = counts.get(f"{role}:{token}", 0) + 1
    lines = _tally_lines(counts, "无判决事件（或全部是非 token 的散文判决，一律不计）").split("\n")
    lines.append(
        "- 口径：**只认 `verdict=` token**（pass / needs_revision / reject），散文判决一律不计"
    )
    return lines


def _open_loops(src: RollupSources) -> list[str]:
    closed = {"done", "completed", "cancelled"}
    open_tasks = [t for t in src.tasks if str(t["status"]) not in closed]
    open_findings = [f for f in src.findings if str(f["status"]) == "open"]
    return [
        f"- 未完成任务：{len(open_tasks)}",
        f"- 未闭环 finding：{len(open_findings)}",
        "- 口径：本节**不计入返工率**，但必须可见（上游 §「未闭环」标题逐字如此）",
    ]


def _hotspots(src: RollupSources) -> list[str]:
    return [
        "- （无卡点登记：Octop 的 timeline 词表里**没有 `error:*` 事件族**）",
        "- ⚠️ **待收口**：上游按 `ENV_ERROR_FAMILIES @ 166` 把 `error:external-write` / "
        "`error:stale-runtime` / `error:platform` / `error:dispatch` / `error:timeout` 归环境类，"
        "其余归过程类；Octop 需先在 timeline 词汇表补 `error:*` 才谈得上本节",
    ]


def _frequent_asks(src: RollupSources) -> list[str]:
    return [
        "- （无提问登记：Octop 的 timeline 词表里**没有 `ask` 事件族**）",
        "- ⚠️ **待收口**：上游从日志的 `ask` 事件去重统计",
    ]


def _decisions(src: RollupSources) -> list[str]:
    raised: dict[str, int] = {}
    resolved = 0
    for action, _at, payload in _actions(src.events):
        key = str(payload.get("id") or payload.get("decision_id") or "")
        if action == "run.decision_raised" and key:
            raised[key] = raised.get(key, 0) + 1
        elif action == "run.decision_resolved":
            resolved += 1
    return [
        f"- 决策（去重）：{len(raised)} 条",
        f"- 已解决：{resolved}",
        "- 口径：按 `payload.id` 去重（上游「decision，去重」逐字）",
    ]


#: SPEC A6: with no ``scan:*`` event this section must still carry this string
#: **verbatim** -- a static "还没写过" sentence would keep A6's no-event branch red.
SINGLE_SOURCE_EMPTY = "暂无 scan:single-source 事件族"


def _scan_events(events: list[DbRow]) -> list[tuple[str, str, int]]:
    """Deduped ``scan:*`` rows as ``(key, fact, hits)``.

    The dedup口径 is ``_decisions``' own (``payload.id`` → ``payload.decision_id``);
    an event without an id cannot be deduped, so it is **not counted** and the section
    stays visibly short instead of double counting (SPEC Q5 "漏写 id 的事件不计入").
    """
    seen: dict[str, tuple[str, int]] = {}
    for action, _at, payload in _actions(events):
        if not action.startswith("scan:"):
            continue
        key = str(payload.get("id") or payload.get("decision_id") or "")
        if not key:
            continue
        hits_raw = payload.get("hits")
        seen[key] = (
            str(payload.get("fact") or action),
            hits_raw if isinstance(hits_raw, int) else 0,
        )
    return [(key, fact, hits) for key, (fact, hits) in sorted(seen.items())]


def _single_source_scan(src: RollupSources) -> list[str]:
    """Section 10 -- **real** numbers from ``scan:*`` events, or one explicit empty line.

    Pure rendering (PLAN I5): no filesystem IO here, the scan itself is
    ``single_source.scan`` and its result reaches this function only as a timeline row.
    """
    rows = _scan_events(src.events)
    if not rows:
        return [
            f"- （{SINGLE_SOURCE_EMPTY}）",
            "- ⚠️ **待收口**（空态不等于没有可扫的）：上游明确说这条义务**没有代码能强制**"
            "（要求 lead 发现第一个副本时当轮全仓总扫），唯一抓手是「让它可见」——"
            " 所以**没人登记本身就是一种可见状态**，不得静默省略；"
            "登记写入方 = `RunService.write_artifact`（PLAN §3.1），"
            "格式逐字 `scan:single-source — <事实名> · 命中 N 处`",
        ]
    per_fact: dict[str, int] = {}
    for _key, fact, hits in rows:
        per_fact[fact] = per_fact.get(fact, 0) + hits
    lines = [f"- 已登记扫描（按 `payload.id` 去重）：{len(rows)} 条"]
    lines += [f"- `{fact}`：命中 {hits} 处" for fact, hits in sorted(per_fact.items())]
    lines += [
        f"- 覆盖事实：{len(per_fact)} 个 · 命中合计：{sum(per_fact.values())} 处",
        "- 口径：事件 = `scan:single-source` 的 `payload.id` / `fact` / `hits`，"
        "去重与决策节同一口径；缺 `payload.id` 的事件**不计入**（显式可见，不静默）",
    ]
    return lines


def _review_efficiency(src: RollupSources) -> list[str]:
    max_review = max((int(t["round"] or 1) for t in src.tasks), default=0)
    max_test = max((int(f["round"] or 1) for f in src.findings), default=0)
    return [
        f"- 评审轮次：review {max_review} 轮 · test {max_test} 轮",
        "- （暂无撤销登记：本 run 的撤销记录不在 timeline 里）",
        "- ⚠️ **待收口**：上游的 `revertLine` 来自撤销登记（本轮 `ORPHAN-SCAN.md §5` 的"
        "自报撤销率是**文档级**数字，不是 run 事件）⇒ 要么给 timeline 补"
        "`run.review_reverted`，要么本节永久显式写「暂无撤销登记」—— **禁止静默省略**",
    ]


def _token_section(usage: DbRow | None) -> list[str]:
    """Section 12 -- three distinguishable states, and never a fabricated 0."""
    lines: list[str] = []
    if usage is not None:
        cache_read = int(usage["cache_read_tokens"] or 0)
        cache_write = int(usage["cache_write_tokens"] or 0)
        # ``cache_write == 0`` on every sampled row means "this provider never fills the
        # column", which is the *third* state -- printing 0 would read as "no caching".
        cache_line = f"- cache：{cache_read}（read）"
        if cache_write == 0:
            cache_line += f" · cache_write：{PROVIDER_OMITS}"
        else:
            cache_line += f" · cache_write：{cache_write}"
        lines = [
            f"- in：{int(usage['input_tokens'] or 0) + int(usage['uncached_input_tokens'] or 0)}",
            cache_line,
            f"- out：{int(usage['output_tokens'] or 0)}",
            # ``steps`` is model_calls on purpose -- TrajectoryMetrics.steps is a
            # different unit (events vs model calls) and swapping them would create
            # a second definition of "steps".
            f"- steps：{int(usage['model_calls'] or 0)}",
        ]
    else:
        lines = [
            TokenCell(name, state="no_token_metric").render()
            for name in ("in", "cache", "out", "steps")
        ]
    lines += [
        f"- peak：{NO_TOKEN_METRIC}（不在 `usage_log`；真值需从 checkpoint 的 "
        "`context_usage.used_tokens` 派生 ⇒ **可选增强，不进 MVP**）",
        f"- first（TTFT）：{NO_TOKEN_METRIC}（代码支持但无数据：带 `ttft_ms` 的 payload = 0 行）",
        "- 三态必须可区分：**有值** / **暂无 token 口径** / **该 provider 不回填**；"
        "**禁止用 0 表示「没有数据」**（SPEC 假设 A-12）",
        "- PG 侧**未验证**：真实 PG 的 `usage_log` 为 0 行 ⇒ 上述可得性基于 SQLite 实测，"
        "**不得声称 PG 已证**",
    ]
    return lines


_SECTION_BUILDERS = (
    _overview,
    _phase_coverage,
    _first_runnable,
    _closing_budget,
    _role_results,
    _open_loops,
    _hotspots,
    _frequent_asks,
    _decisions,
    _single_source_scan,
    _review_efficiency,
    None,  # token 节需要 usage，单独处理
)


@dataclass(frozen=True)
class MetricsRollup:
    """An idempotent 12-section snapshot (upstream writes it as ``METRICS.md``)."""

    sections: tuple[tuple[str, tuple[str, ...]], ...]

    def render(self) -> str:
        out = ["# 团队指标（METRICS）", "", "> 由指标聚合自动生成（幂等快照）", ""]
        for title, lines in self.sections:
            out.append(f"## {title}")
            out.append("")
            out.extend(lines)
            out.append("")
        return "\n".join(out).rstrip("\n") + "\n"


def rollup(sources: RollupSources) -> MetricsRollup:
    """Aggregate one run's rows into the 12 sections.

    Idempotent: the same rows always render byte-identical output (no clock read,
    no counters, no ordering by insertion).

    **No ``METRICS`` counter is touched on purpose.** The 12 sections are an on-demand
    snapshot computed from rows (upstream ``renderMetrics`` is a pure function too), so
    there is no hot path to instrument here and **no new bucket is needed** -- which is
    why ``infra/metrics.py`` stays byte-identical. Consequently this module has no
    ``infra/metrics`` import at all: a lazy import of something unused would be noise,
    and the acceptance item ("no module-level ``infra/metrics`` import") holds.
    """
    built: list[tuple[str, tuple[str, ...]]] = []
    for title, builder in zip(SECTION_TITLES, _SECTION_BUILDERS, strict=True):
        if builder is None:
            built.append((title, tuple(_token_section(sources.usage))))
        else:
            built.append((title, tuple(builder(sources))))
    return MetricsRollup(sections=tuple(built))
