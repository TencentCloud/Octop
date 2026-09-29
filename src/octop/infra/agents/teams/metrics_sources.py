"""Load the rows METRICS rolls up, and label what each section can honestly say.

``teams/metrics.py`` (T-30) is a **pure** function over ``RollupSources``; this module
is the missing half — the part that reads the database. It exists so the HTTP layer can
stay thin (a router must not run SQL) while ``/metrics`` finally has a production entry.

The rows are handed over as **mappings** because the rollup reads them by storage key
(``at``/``action``/``payload`` for events, ``round``/``verdict``/``kind``/``status`` for
tasks and findings, the ``usage_log`` columns for the token section). The repo rows are
dataclasses, so ``asdict`` is the bridge — no second schema is defined here.

**The token section's boundary (lead ruling, PLAN AM-26 follow-up).** The cost of a
run is read from its **room thread**: that is where a run's conversation happens, and
the persist dispatch channel runs its turns there on a run-scoped session key. Turns
that go through the **one-shot `task` channel do not land in that thread** — they run
inside the host — so they are **not counted**. That boundary is stated in the section's
own note as well, because an unstated gap reads as "no consumption" when the truth is
"that channel is not metered here".

**Section states (PLAN · AM-26).** Five event families the upstream metrics need do not
exist in the timeline vocabulary (``first-runnable`` / ``freeze`` / ``error:*`` / ``ask``
/ ``scan:single-source``), so several sections cannot carry a true value. Every section
is therefore labelled ``measured`` / ``proxy`` / ``empty`` / ``partial`` — an empty
section must never be silently indistinguishable from a section nobody registered, which
is the same discipline as the token section's three states.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict
from typing import Any

from octop.infra.agents.teams.metrics import SECTION_TITLES, RollupSources

#: What each section's value is worth right now, keyed by the rollup's own title.
#: Transcribed from ``PLAN.md · AM-26`` (the 12-row table) — **not** a second definition
#: of the sections; the titles come from ``metrics.SECTION_TITLES``.
SECTION_STATES: Mapping[str, str] = {
    "总览": "measured",
    "阶段覆盖": "measured",
    "首产物（首个可运行产物耗时）": "proxy",
    "收尾预算（实现期 = 首产物→冻结 · 收尾 = 冻结→交付）": "proxy",
    "角色结果（pass=交付 / rework=返工件 / fail=失败）": "measured",
    "未闭环（不计入返工率，但必须可见）": "measured",
    "高频卡点（error / 返工，去重）": "empty",
    "用户高频提问（ask，去重）": "empty",
    "决策记录（decision，去重）": "measured",
    "单源化总扫（见一个，扫全部）": "empty",
    "评审效率（轮次 / 撤销率）": "partial",
    "token 成本与上下文峰值": "measured",
}

#: One line per section saying *why* it is where it is (AM-26's 「现态」 column).
SECTION_NOTES: Mapping[str, str] = {
    "首产物（首个可运行产物耗时）": "暂无 first-runnable 事件，暂用 run.artifact_written 代理",
    "收尾预算（实现期 = 首产物→冻结 · 收尾 = 冻结→交付）": "暂无 freeze 事件，按交付时间代理",
    "高频卡点（error / 返工，去重）": "暂无 error:* 事件族 —— 空态不等于没有卡点",
    "用户高频提问（ask，去重）": "暂无 ask 事件族 —— 空态不等于没有提问",
    "单源化总扫（见一个，扫全部）": "暂无 scan:single-source 事件族 —— 空态不等于没有可扫的",
    "评审效率（轮次 / 撤销率）": "轮次为真值；撤销率暂无 revert 事件（显式空态）",
    "token 成本与上下文峰值": (
        "usage_log 三态：有值 / 暂无 token 口径 / 该 provider 不回填；"
        "**本节的成本 = run 房间线程，one-shot `task` 通道的 turn 不在内**"
    ),
}


def section_states() -> list[dict[str, str]]:
    """The 12 sections with their honest state and a one-line reason.

    Returned in the rollup's own order so a caller can pair the two lists positionally
    without re-deriving the section list (which would be a second definition).
    """
    return [
        {
            "title": title,
            "state": SECTION_STATES.get(title, "measured"),
            "note": SECTION_NOTES.get(title, ""),
        }
        for title in SECTION_TITLES
    ]


def _rows(rows: Any) -> list[Mapping[str, Any]]:
    """Repo rows (dataclasses) as mappings — the shape the rollup reads by key."""
    return [asdict(row) for row in rows]


def _usage_for(services: Any, run: Any) -> dict[str, int] | None:
    """The run's token row, or ``None`` when there is no usage at all.

    ``None`` is a **state**, not a zero: ``thread_totals`` answers all-zeros for a
    thread with no rows, and passing that on would print ``in: 0`` — which the plan
    forbids ("0 must never mean no data"). So a run with no recorded turns reports
    ``no_token_metric`` instead.
    """
    thread_id = getattr(run, "room_thread_id", None)
    if not thread_id:
        return None
    totals = services.usage_repo.thread_totals(agent_id=run.team_agent_id, thread_id=thread_id)
    return totals if int(totals.get("turns") or 0) > 0 else None


def load_sources(*, services: Any, run: Any) -> RollupSources:
    """Read one run's rows into the rollup's input.

    Sources: the run's ``timeline_events`` (T-13 guarantees every state write appends
    one), the run project's tasks, the run's findings, and the room thread's token
    totals. No aggregate is computed here — this only pipes rows, so the 12 sections
    keep exactly one definition (``metrics.py``).
    """
    usage = _usage_for(services, run)
    sources = RollupSources(
        events=_rows(services.timeline_repo.list_by_project(run.project_id)),
        tasks=_rows(services.project_task_repo.list_by_project(run.project_id)),
        findings=_rows(services.task_finding_repo.list_by_run(run.run_id)),
    )
    sources.usage = usage
    return sources


__all__ = ["SECTION_NOTES", "SECTION_STATES", "load_sources", "section_states"]
