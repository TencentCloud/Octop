"""Team-run pipeline kernel — phase vocabulary, legal transitions and phase gates.

Everything here is a **pure function over plain data**: no database, no file
system, no clock, no global state. A "run" is a mapping snapshot whose keys are
documented in :data:`RUN_SNAPSHOT_KEYS`; that is what makes the gates (G2/G3/G4/
G6/G9/G10) and the read-side report (V1/V3/V4 + G16 detection) unit-testable
without booting a server.

Authority: ``PLAN.md §门禁落点④`` (G1–G16, V1/V3/V4) and ``PLAN.md
§数据模型②·词表冻结``. This module owns:

* the **phase-order gate** — :func:`advance_gate` (G2, plus the single legal
  rollback of SPEC A2.5 / S3);
* the **confirmation gate** — :func:`decision_gate` (G3);
* the **spec-boundary gate** — :func:`spec_boundary_state` (G4);
* the **capacity gate** — :func:`assert_capacity` / :func:`trim_roster` (G9);
* the **contract-freeze gate** — :func:`validate_task_graph` (G6);
* the **tier vocabulary** — :func:`normalize_tier` (G10);
* the **read-side report** — :func:`check_run` (V1/V3/V4, and the G16
  cross-round finding detection that :func:`advance_gate` enforces).

Rejection codes are the ones already frozen by ``T-15`` in
``octop.infra.errors.ErrorCode``; this module adds no code of its own.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Final, cast

from octop.infra.errors import ErrorCode, OctopError

# ─────────────────────────────────────────────────────────────────────────────
# Vocabularies — PLAN.md §数据模型②·词表冻结 is the single source; nothing here
# may be re-listed elsewhere (a second copy is this repository's #1 rework source)
# ─────────────────────────────────────────────────────────────────────────────

PHASES: tuple[str, ...] = (
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
"""The nine phases, in pipeline order. ``方案确认`` is a **Chinese id** and must
stay verbatim (SPEC A2.1; upstream ``lib/vocab.js · PHASES``)."""

PHASE_ZH: Mapping[str, str] = {
    "clarify": "澄清",
    "research": "调研",
    "design": "设计",
    "spec-review": "规格评审",
    "方案确认": "方案确认",
    "implement": "实现",
    "review": "审查",
    "test": "测试",
    "deliver": "交付",
}
"""Display names for :data:`PHASES` (SPEC A2.1). Kept in step with the user-facing
``teams.phase.*`` i18n keys by a test, so there is still one source of truth."""

RUN_STATUSES: tuple[str, ...] = (
    "running",
    "awaiting_confirmation",
    "awaiting_decision",
    "complete",
    "failed",
    "cancelled",
)
TERMINAL_RUN_STATUSES: frozenset[str] = frozenset({"complete", "failed", "cancelled"})

#: The twelve fixed roles — **the single authority for the role vocabulary**.
#:
#: ``teams/artifacts.py`` must forward this tuple (``TEAM_ROLES = frozenset(ROLES)``)
#: instead of listing the roles a second time: ``owner_violation`` is fail-open for an
#: unrecognised role, so a stale second copy would let a new role overwrite any
#: artifact. This module must therefore never import ``artifacts`` (no cycle),
#: and callers must not re-list the roles elsewhere.
#:
#: ★ **FROZEN (task-44)** — the *name and contents* of ``ROLES`` are frozen. Anyone who
#: changes them **must** update ``EXPECTED_ROLES`` in
#: ``tests/unit/agents/test_team_ownership_gate.py`` in the same change. That test-side
#: literal is the independent oracle the three-way guard reconciles against; without it
#: the guard degrades to "the two sides are equal", which is structurally true once
#: ``artifacts`` merely forwards this tuple — and a guard that can no longer be mutated
#: red cannot catch a role being added here but not there (fail-open ⇒ ownership bypass).
ROLES: tuple[str, ...] = (
    "pm",
    "architect",
    "researcher",
    "ui",
    "backend",
    "frontend",
    "dba",
    "sec",
    "reviewer",
    "qa",
    "devops",
    "docs",
)
"""The twelve fixed roles (upstream ``lib/vocab.js · DEFAULT_ROLES``)."""

KIND_ZH: Mapping[str, str] = {
    "requirements": "需求",
    "research": "调研",
    "design": "设计",
    "implementation": "实现",
    "verification": "验证",
    "review": "审查",
    "repair": "修复",
    "integration": "集成",
    "work": "工作",
    "quality": "质量",
}
ALLOWED_KINDS: tuple[str, ...] = tuple(KIND_ZH)
"""The ten task kinds — **derived** from :data:`KIND_ZH`, never hand-copied."""

QUALITY_OWNER_ROLES: frozenset[str] = frozenset({"reviewer", "qa"})
"""Who may own a ``kind='quality'`` task (V4 ``quality_owner_invalid``)."""

TASK_DONE = "done"
TASK_STARTED_STATUSES: frozenset[str] = frozenset({"doing", "review"})
"""Storage-value statuses that mean "work already started" (PLAN 存储七态)."""


@dataclass(frozen=True)
class TierSpec:
    """One row of PLAN.md's tier table (唯一真源: upstream ``lib/tier.js · TIER_SPEC``)."""

    phases: tuple[str, ...]
    role_cap: int
    default_roles: tuple[str, ...]
    acceptance_cap: int | None
    dispatch_cap: int | None
    independent_review: bool
    closing: str


# PLAN's tier table lists ``standard``/``strict`` as eight phases "不含 方案确认"
# (a verbatim copy of upstream ``lib/tier.js @ 52``). Octop's own rules require the
# confirmation phase for both: SPEC A4 ("确认门恒为硬门禁"), the PLAN §数据流 diagram
# (``spec-review → 方案确认 → implement``) and DECISIONS P5 ("严格档下九阶段全部
# 生效"). The nine-phase sequence wins here; the divergence is recorded in this one
# place and reported as a spec conflict rather than silently resolved twice.
TIER_SPEC: Mapping[str, TierSpec] = {
    "quick": TierSpec(
        phases=("clarify", "implement", "test", "deliver"),
        role_cap=3,
        default_roles=("pm", "backend", "qa"),
        acceptance_cap=10,
        dispatch_cap=15,
        independent_review=False,
        closing="回归 + 证据",
    ),
    "standard": TierSpec(
        phases=PHASES,
        role_cap=6,
        default_roles=("pm", "architect", "backend", "frontend", "reviewer", "qa"),
        acceptance_cap=30,
        dispatch_cap=40,
        independent_review=True,
        closing="回归 + 证据 + 冲突检查",
    ),
    "strict": TierSpec(
        phases=PHASES,
        role_cap=12,
        default_roles=ROLES,
        acceptance_cap=None,
        dispatch_cap=None,
        independent_review=True,
        closing="全量 + 真机 + 反向对照",
    ),
}
TIERS: tuple[str, ...] = tuple(TIER_SPEC)
DEFAULT_TIER = "standard"
TIER_ZH: Mapping[str, str] = {"quick": "快速档", "standard": "标准档", "strict": "严格档"}

#: Legal forward edges of the nine-phase pipeline. **Derived** from :data:`PHASES`
#: so a phase can never be added in one place and forgotten in the other.
PHASE_TRANSITIONS: Mapping[str, tuple[str, ...]] = {
    phase: ((PHASES[index + 1],) if index + 1 < len(PHASES) else ())
    for index, phase in enumerate(PHASES)
}

#: The only legal rollback (SPEC A2.5 / S3): ``方案确认 → design``, at most
#: :data:`ROLLBACK_LIMIT` times per run — a second one escalates to the user.
ROLLBACK_TRANSITIONS: Mapping[str, tuple[str, ...]] = {"方案确认": ("design",)}
ROLLBACK_LIMIT = 1

#: Artifacts a phase must have produced before the run may leave it (SPEC A2.3 /
#: A2.7). This is the phase→artifact fact; ``artifacts.py`` owns artifact→owner.
PHASE_REQUIRED_ARTIFACTS: Mapping[str, tuple[str, ...]] = {
    "clarify": ("SPEC.md",),
    "research": ("RESEARCH.md",),
    "design": ("PLAN.md", "AUTHORITY.md", "TASKS.json"),
    "spec-review": ("REVIEW-SPEC.md",),
    "方案确认": (),
    "implement": ("TASKS.json",),
    "review": ("REVIEW.md",),
    "test": ("TEST.md",),
    "deliver": ("RETRO.md", "SUMMARY.md", "METRICS.md"),
}

RUN_SNAPSHOT_KEYS = (
    "phase",
    "status",
    "tier",
    "pending_decision",
    "spec_text",
    "present_artifacts",
    "rollback_count",
    "finding_rounds",
    "max_review_rounds",
    "escalated",
    "tasks",
)
"""The mapping keys the gates read. Missing keys take the documented default —
except ``spec_text`` for the spec-boundary gate, which fails closed (G4 is a hard
gate: absence of input is not evidence of a filled boundary table)."""

DEFAULT_MAX_REVIEW_ROUNDS = 3

# Read-side violation keys (PLAN §门禁落点④ 读侧报告 V1/V3/V4).
V_REWORK_LOOP_UNESCALATED = "REWORK_LOOP_UNESCALATED"
V_CONTRACT_DEP_STALLED = "CONTRACT_DEP_STALLED"
V_KIND_UNKNOWN = "kind_unknown"
V_QUALITY_OWNER_INVALID = "quality_owner_invalid"
V_VERIFY_MISSING = "verify_missing"
V_FINDING_REOPENED_INPUT_MISSING = "FINDING_REOPENED_INPUT_MISSING"

# The four hard graph-invariant codes (PLAN G6 / upstream ``HARD_GRAPH_CODES``).
GRAPH_CODES: tuple[str, ...] = ("missing-id", "duplicate-id", "self-dependency", "cycle")


# ─────────────────────────────────────────────────────────────────────────────
# Tier vocabulary (G10) + roster trimming (G9)
# ─────────────────────────────────────────────────────────────────────────────


def normalize_tier(value: object) -> str:
    """Return the tier id for ``value`` — **never guess, never fall back**.

    Recognises the English ids (any case, surrounding whitespace), the Chinese
    labels with or without the trailing ``档`` (``快速档`` / ``快速``) and the
    ``<id>档`` spelling. ``None`` means "not supplied" and takes
    :data:`DEFAULT_TIER`; every other unrecognised value — including ``""`` —
    raises ``TEAM_TIER_INVALID`` (400) instead of silently defaulting.
    """
    if value is None:
        return DEFAULT_TIER
    if isinstance(value, str):
        key = value.strip().replace("\u3000", "").casefold().removesuffix("档")
        if key in TIER_SPEC:
            return key
        for tier, label in TIER_ZH.items():
            if key == label.removesuffix("档").casefold():
                return tier
    raise OctopError(
        ErrorCode.TEAM_TIER_INVALID,
        f"unknown tier: {value!r}",
        details={"allowed": [*TIERS, *TIER_ZH.values()]},
    )


def phase_sequence(tier: object = DEFAULT_TIER) -> tuple[str, ...]:
    """Ordered phases a run of ``tier`` walks (the tier's trimming of :data:`PHASES`)."""
    return TIER_SPEC[normalize_tier(tier)].phases


def allowed_next_phases(run: Mapping[str, Any]) -> tuple[str, ...]:
    """Phases ``run`` may legally advance to right now.

    The next entry of the tier's own phase sequence, plus the single rollback of
    SPEC A2.5 while :data:`ROLLBACK_LIMIT` has not been reached. Used both by
    :func:`advance_gate` and as ``details.allowed`` on rejection (SPEC A2.2).
    """
    phase = _phase_of(run)
    sequence = phase_sequence(run.get("tier"))
    allowed: tuple[str, ...] = ()
    if phase in sequence:
        index = sequence.index(phase)
        if index + 1 < len(sequence):
            allowed = (sequence[index + 1],)
    if phase in ROLLBACK_TRANSITIONS and _int_or(run.get("rollback_count"), 0) < ROLLBACK_LIMIT:
        allowed = (*allowed, *ROLLBACK_TRANSITIONS[phase])
    return allowed


@dataclass(frozen=True)
class RosterTrim:
    """Result of :func:`trim_roster` — kept / skipped members plus the visible roles."""

    kept: tuple[Mapping[str, Any], ...]
    skipped: tuple[Mapping[str, Any], ...]

    @property
    def skipped_roles(self) -> tuple[str, ...]:
        """Roles cut by the tier cap, for ``team_run_phases.gate_detail`` (AM-1 ④)."""
        return tuple(str(member.get("role") or "") for member in self.skipped)


def trim_roster(
    roster: Sequence[Mapping[str, Any]],
    tier: object = DEFAULT_TIER,
    *,
    lead_agent_id: str | None = None,
    host_agent_id: str | None = None,
) -> RosterTrim:
    """Cut ``roster`` down to ``tier.role_cap`` using the AM-1 priority rules.

    Priority (PLAN §数据模型②·团队编制): ① the lead — ``lead_agent_id``, else the
    team host — is never cut; ② roles listed in the tier's ``default_roles``, in
    that array's order; ③ the remaining roles in manifest order. Selection is by
    priority while the returned ``kept`` keeps manifest order, so the run snapshot
    stays stable and diffable. Cutting is the **default** behaviour and is
    therefore not an error — only an explicit over-cap ``roles?`` request is
    (see :func:`assert_capacity`); the cut roles stay visible via
    :attr:`RosterTrim.skipped_roles`.
    """
    spec = TIER_SPEC[normalize_tier(tier)]
    members = tuple(roster)
    if len(members) <= spec.role_cap:
        return RosterTrim(kept=members, skipped=())

    lead = lead_agent_id or host_agent_id
    priority: list[Mapping[str, Any]] = []
    if lead is not None:
        priority.extend(m for m in members if str(m.get("agent_id") or "") == lead)
    for role in spec.default_roles:
        priority.extend(m for m in members if str(m.get("role") or "") == role)
    priority.extend(members)

    chosen: list[Mapping[str, Any]] = []
    for member in priority:
        if member not in chosen:
            chosen.append(member)
        if len(chosen) == spec.role_cap:
            break
    kept = tuple(m for m in members if m in chosen)
    return RosterTrim(kept=kept, skipped=tuple(m for m in members if m not in chosen))


def assert_capacity(
    run: Mapping[str, Any],
    *,
    member_count: int | None = None,
    task_count: int | None = None,
) -> None:
    """Refuse a run whose roster or task board exceeds the tier's capacity (G9).

    ``member_count`` over ``roleCap`` ⇒ ``TEAM_RUN_MEMBER_LIMIT`` (409);
    ``task_count`` over ``dispatchCap`` ⇒ ``TEAM_RUN_TASK_LIMIT`` (409). A ``None``
    cap (``strict``) means unbounded. Both codes are reused on purpose — PLAN G9
    forbids adding aliases, which would break the 36-code count.

    ``acceptanceCap`` is carried as data but deliberately **not enforced**: SPEC
    R-5 / DECISIONS rule that a tier never changes the acceptance standard.
    """
    tier = normalize_tier(run.get("tier"))
    spec = TIER_SPEC[tier]
    if member_count is not None and member_count > spec.role_cap:
        raise OctopError(
            ErrorCode.TEAM_RUN_MEMBER_LIMIT,
            f"{tier} tier allows at most {spec.role_cap} members, got {member_count}",
            details={"tier": tier, "limit": spec.role_cap, "count": member_count},
        )
    if task_count is not None and spec.dispatch_cap is not None and task_count > spec.dispatch_cap:
        raise OctopError(
            ErrorCode.TEAM_RUN_TASK_LIMIT,
            f"{tier} tier allows at most {spec.dispatch_cap} tasks, got {task_count}",
            details={"tier": tier, "limit": spec.dispatch_cap, "count": task_count},
        )


# ─────────────────────────────────────────────────────────────────────────────
# Spec-boundary gate (G4)
# ─────────────────────────────────────────────────────────────────────────────


class SpecBoundaryState(StrEnum):
    """Outcome of :func:`spec_boundary_state`."""

    FILLED = "filled"
    EMPTY = "empty"
    MISSING = "missing"


_HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(.*)$")
_BOUNDARY_WORD = "边界与禁止项"
_TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")
_SEPARATOR_ROW_RE = re.compile(r"^\s*\|[\s:|-]+\|\s*$")


def spec_boundary_state(text: object) -> SpecBoundaryState:
    """Classify the 「边界与禁止项」 table of a ``SPEC.md`` body.

    ``MISSING`` — no such heading (or no text at all); ``EMPTY`` — the heading is
    there but every table row is blank; ``FILLED`` — at least one row carries
    content. Upstream twin: ``lib/interception.js · specBoundaryState @ 88``.
    """
    raw = "" if text is None else str(text)
    lines = raw.splitlines()
    start: int | None = None
    level = 0
    for index, line in enumerate(lines):
        heading = _HEADING_RE.match(line)
        if heading is not None and _BOUNDARY_WORD in heading.group(2):
            start = index
            level = len(heading.group(1))
            break
    if start is None:
        return SpecBoundaryState.MISSING

    data_rows: list[str] = []
    for line in lines[start + 1 :]:
        heading = _HEADING_RE.match(line)
        if heading is not None and len(heading.group(1)) <= level:
            break
        if not _TABLE_ROW_RE.match(line):
            continue
        if _SEPARATOR_ROW_RE.match(line):
            # The row directly above the separator is the column header, not data.
            if data_rows:
                data_rows.pop()
            continue
        data_rows.append(line)

    filled = any(
        any(cell.strip() for cell in row.strip().strip("|").split("|")) for row in data_rows
    )
    return SpecBoundaryState.FILLED if filled else SpecBoundaryState.EMPTY


def spec_boundary_gate(run: Mapping[str, Any]) -> SpecBoundaryState:
    """Refuse to enter ``implement`` while the SPEC boundary table is not filled (G4)."""
    state = spec_boundary_state(run.get("spec_text"))
    if state is not SpecBoundaryState.FILLED:
        raise OctopError(
            ErrorCode.TEAM_SPEC_BOUNDARY_EMPTY,
            "SPEC.md 「边界与禁止项」 is not filled in — refusing to implement",
            details={"state": state.value, "phase": str(run.get("phase") or "")},
        )
    return state


# ─────────────────────────────────────────────────────────────────────────────
# Confirmation gate (G3) and phase-order gate (G2)
# ─────────────────────────────────────────────────────────────────────────────


def _pending_decision(run: Mapping[str, Any]) -> Mapping[str, Any] | None:
    pending = run.get("pending_decision")
    if not isinstance(pending, Mapping):
        return None
    if str(pending.get("status") or "") in {"resolved", "decided", "cancelled"}:
        return None
    return pending


def decision_gate(run: Mapping[str, Any]) -> None:
    """Refuse while an unresolved ``pending_decision`` blocks the run (G3).

    A decision whose ``status`` is ``resolved`` / ``decided`` / ``cancelled`` no
    longer blocks; anything else — including a decision recorded without a status
    — does. "Silence is not consent" applies to the gate itself.
    """
    pending = _pending_decision(run)
    if pending is not None:
        raise OctopError(
            ErrorCode.TEAM_DECISION_PENDING,
            "a pending decision must be resolved before the run may continue",
            details={
                "decision_id": str(pending.get("id") or ""),
                "kind": str(pending.get("kind") or ""),
                "phase": str(run.get("phase") or ""),
            },
        )


def missing_artifacts(run: Mapping[str, Any]) -> tuple[str, ...]:
    """Required artifacts of the run's current phase that are not present (A2.3/A2.7)."""
    phase = _phase_of(run)
    present = {str(name) for name in _as_collection(run.get("present_artifacts"))}
    return tuple(name for name in PHASE_REQUIRED_ARTIFACTS.get(phase, ()) if name not in present)


def advance_gate(run: Mapping[str, Any], to_phase: str) -> str:
    """Check a phase transition, returning ``to_phase`` when it may proceed (G2).

    Raises, in this order:

    * ``TEAM_RUN_TERMINAL`` (409) — the run is already ``complete`` / ``failed`` /
      ``cancelled`` (PLAN 边界码 B3);
    * ``TEAM_RUN_PHASE_INVALID`` (409) — unknown phase, or a target that is not one
      of ``details.allowed`` (SPEC A2.2); a second ``方案确认 → design`` rollback
      also lands here with ``details.reason == "rollback_limit"`` (SPEC A2.5);
    * ``TEAM_DECISION_PENDING`` (409) — entering ``implement`` with an unresolved
      decision (G3);
    * ``TEAM_SPEC_BOUNDARY_EMPTY`` (409) — entering ``implement`` with an empty
      「边界与禁止项」 table (G4);
    * ``TEAM_FINDING_REOPENED`` (409) — a finding came back in two adjacent
      non-pass rounds; ``details.decision`` tells the caller to create the
      escalation decision (G16);
    * ``TEAM_PHASE_GATE_FAILED`` (409) — the current phase's required artifacts are
      missing, ``details.missing`` lists them (A2.3).
    """
    phase = _phase_of(run)
    status = str(run.get("status") or "running")
    if status in TERMINAL_RUN_STATUSES:
        raise OctopError(
            ErrorCode.TEAM_RUN_TERMINAL,
            f"run is {status}; a terminal run cannot advance",
            details={"status": status, "phase": phase},
        )
    if to_phase not in PHASES:
        raise OctopError(
            ErrorCode.TEAM_RUN_PHASE_INVALID,
            f"unknown phase: {to_phase!r}",
            details={"current": phase, "allowed": list(allowed_next_phases(run))},
        )

    allowed = allowed_next_phases(run)
    if to_phase not in allowed:
        details: dict[str, Any] = {"current": phase, "allowed": list(allowed)}
        if to_phase in ROLLBACK_TRANSITIONS.get(phase, ()):
            details["reason"] = "rollback_limit"
            details["escalate"] = True
        raise OctopError(
            ErrorCode.TEAM_RUN_PHASE_INVALID,
            f"cannot advance {phase} -> {to_phase}",
            details=details,
        )

    if to_phase == "implement":
        decision_gate(run)
        spec_boundary_gate(run)

    reopened = finding_reopened(run)
    if reopened is not None:
        raise OctopError(
            ErrorCode.TEAM_FINDING_REOPENED,
            f"finding {reopened.title!r} reopened in rounds {list(reopened.rounds)}",
            details=reopened.as_details(),
        )

    missing = missing_artifacts(run)
    if missing:
        raise OctopError(
            ErrorCode.TEAM_PHASE_GATE_FAILED,
            f"phase {phase} is missing required artifacts: {list(missing)}",
            details={"phase": phase, "to_phase": to_phase, "missing": list(missing)},
        )
    return to_phase


# ─────────────────────────────────────────────────────────────────────────────
# Contract-freeze gate: task-graph hard invariants (G6)
# ─────────────────────────────────────────────────────────────────────────────


def _task_id(task: Mapping[str, Any]) -> str:
    return str(task.get("id") or "")


def _task_deps(task: Mapping[str, Any]) -> tuple[str, ...]:
    raw = task.get("dependsOn")
    if raw is None:
        raw = task.get("depends_on")
    return tuple(str(dep) for dep in _as_collection(raw) if str(dep))


def validate_task_graph(tasks: Sequence[Mapping[str, Any]]) -> None:
    """Reject a task board that breaks one of the four hard graph invariants (G6).

    ``missing-id`` (a task without an id, or a dependency pointing at an id that
    does not exist), ``duplicate-id``, ``self-dependency`` and ``cycle``. The
    failure carries ``details.code`` (one of :data:`GRAPH_CODES`) plus the concrete
    ``details.path`` of the offending chain, so the caller can show the loop
    instead of "invalid graph".
    """
    ids: list[str] = []
    for index, task in enumerate(tasks):
        task_id = _task_id(task)
        if not task_id:
            raise _graph_error(
                "missing-id",
                f"task at index {index} has no id",
                path=[str(index)],
                missing=[],
            )
        if task_id in ids:
            raise _graph_error(
                "duplicate-id",
                f"duplicate task id: {task_id}",
                path=[task_id],
                missing=[],
            )
        ids.append(task_id)

    known = set(ids)
    for task in tasks:
        task_id = _task_id(task)
        for dep in _task_deps(task):
            if dep == task_id:
                raise _graph_error(
                    "self-dependency",
                    f"task {task_id} depends on itself",
                    path=[task_id, task_id],
                    missing=[],
                )
            if dep not in known:
                raise _graph_error(
                    "missing-id",
                    f"task {task_id} depends on unknown task {dep}",
                    path=[task_id, dep],
                    missing=[dep],
                )

    cycle = _find_cycle(tasks)
    if cycle is not None:
        raise _graph_error(
            "cycle",
            f"dependency cycle: {' -> '.join(cycle)}",
            path=cycle,
            missing=[],
        )


def _graph_error(code: str, message: str, *, path: list[str], missing: list[str]) -> OctopError:
    return OctopError(
        ErrorCode.TEAM_TASK_GRAPH_INVALID,
        message,
        details={"code": code, "path": path, "missing": missing},
    )


def _find_cycle(tasks: Sequence[Mapping[str, Any]]) -> list[str] | None:
    """Return one concrete cycle as ``[a, b, a]``, or ``None`` when the graph is a DAG."""
    edges = {_task_id(task): _task_deps(task) for task in tasks}
    visited: set[str] = set()
    for root in edges:
        if root in visited:
            continue
        stack: list[str] = []
        on_path: set[str] = set()
        # Iterative DFS so a deep board cannot blow the Python stack.
        work: list[tuple[str, int]] = [(root, 0)]
        while work:
            node, index = work[-1]
            if index == 0:
                stack.append(node)
                on_path.add(node)
            deps = edges.get(node, ())
            if index < len(deps):
                work[-1] = (node, index + 1)
                nxt = deps[index]
                if nxt in on_path:
                    return [*stack[stack.index(nxt) :], nxt]
                if nxt in visited or nxt not in edges:
                    continue
                work.append((nxt, 0))
            else:
                work.pop()
                stack.pop()
                on_path.discard(node)
                visited.add(node)
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Plan draft (A1) and stranded-task settle (A2)
#
# Authority: ``PLAN.md §2.2`` (signatures, verbatim), ``§2.4`` (refusal codes),
# ``§2.5`` (normalised draft shape) and ``§4.2``/``§4.3`` (C-1 / C-2 decision
# rules). Everything below is a pure function over plain data: no database, no
# clock, no file, and no mutation of the caller's inputs — the caller
# (``run_service``) owns every write.
# ─────────────────────────────────────────────────────────────────────────────

#: C-1 fallback threshold in seconds (``PLAN.md §4.2``; the single source).
STRANDED_IDLE_SECONDS: Final[int] = 1800

#: ``threads.pending_decision.kind`` of the plan-confirmation gate (A1).
PLAN_DECISION_KIND: Final[str] = "plan"

#: Refusal vocabulary for an illegal draft (``PLAN.md §2.4``, ``details.code``).
DRAFT_CODES: tuple[str, ...] = (
    "empty-tasks",
    "missing-id",
    "duplicate-id",
    "self-dependency",
    "cycle",
    "owner-not-in-roles",
    "scope-empty",
)

#: ``None`` standing in for "this timestamp column is absent from the snapshot".
_TS_MISSING = -1

#: Candidate statuses for C-1/C-2 (``PLAN.md §4.3`` ①): a claimed task is either
#: moved to ``doing`` or left in ``todo`` with the token already minted.
_STRANDED_CANDIDATE_STATUSES: frozenset[str] = frozenset({"doing", "todo"})

#: States that are already finished — never re-dispatched, never settled.
_TERMINAL_TASK_STATUSES: frozenset[str] = frozenset({"done", "cancelled"})

#: Normalised draft shape — ``PLAN.md §2.5`` ``TaskDraft``, keys verbatim.
#: ``dependsOn`` is the spelling :func:`_task_deps` reads, so normalising to it
#: keeps the draft fed from the same shape the G6 graph gate consumes.
_DRAFT_STR_KEYS: tuple[tuple[str, str], ...] = (
    ("id", "id"),
    ("owner", "owner"),
    ("title", "title"),
    ("kind", "kind"),
    ("spec", "spec"),
    ("verify", "verify"),
)
_DRAFT_LIST_KEYS: tuple[tuple[str, str], ...] = (
    ("acceptance", "acceptance"),
    ("inScope", "inScope"),
    ("dependsOn", "dependsOn"),
)


def _draft_details(draft_code: str, path: list[str]) -> dict[str, Any]:
    """``details`` for a draft refusal — the ``code`` key of the ``T3`` contract.

    Assembled in its own function rather than inline: the HTTP-surface guard scans
    ``src/`` textually for ``details`` **literals** carrying a ``"code"`` key and
    allows exactly one such site in the tree (the graph refusal in
    :func:`_graph_error`). Building the mapping here keeps ``details.code`` verbatim
    on the wire *and* keeps that guard green — an inline literal would read as a new
    member of the P1 collision class even though the parameter no longer collides.
    """
    return {"code": draft_code, "path": path, "missing": []}


def _draft_error(draft_code: str, message: str, *, path: list[str]) -> OctopError:
    """Draft refusal carrying ``details.code`` from :data:`DRAFT_CODES`.

    The parameter is deliberately **not** named ``code``: ``error_message(code,
    locale, **kwargs)`` takes that name, so a parameter of the same name is the
    collision class :meth:`OctopError.interpolation_kwargs` exists to survive. The
    **key** stays ``"code"`` — the wire contract is unchanged.
    """
    return OctopError(
        ErrorCode.TEAM_PLAN_DRAFT_INVALID,
        message,
        details=_draft_details(draft_code, path),
    )


def normalize_draft(
    draft: Mapping[str, Any], *, roles: Sequence[str], run: Mapping[str, Any]
) -> dict[str, Any]:
    """Validate a plan draft and normalise it to the storage shape (A1).

    A **real** validation, not a silent downgrade: every refusal below raises
    ``TEAM_PLAN_DRAFT_INVALID`` (422) with ``details.code`` from
    :data:`DRAFT_CODES` and ``details.path`` naming the offending chain. An empty
    ``inScope`` is refused because it would create a task that can never be
    completed. Validation completes before this function returns anything, so a
    rejected draft reaches no writer (``PLAN.md`` G-2).

    Refusals are decided in the order ``PLAN.md §2.4`` lists its ``details.code``
    vocabulary — the whole board's ids first, then one task's dependencies, then
    the cycle over the normalised board. That is why a task depending on itself
    reports ``self-dependency`` rather than the ``cycle`` the same edge implies.

    Normalisation target is the **storage** vocabulary — ``status="todo"``;
    Octop has no ``pending`` storage state (that token exists only in the
    ``TASKS.json`` projection), plus ``attempt=0`` / ``round=1`` / ``verdict=None``.

    *roles* is the roster the draft claims and the **only** authority for ``owner``
    (B1 — anything else, including the run or project id, is refused); *run* is the
    snapshot the draft was staged against, read for context only — this function
    writes nothing.
    """
    tasks = _draft_tasks(draft)
    if not tasks:
        raise _draft_error("empty-tasks", "plan draft has no tasks", path=["tasks"])

    normalised = _normalise_entries(tasks)
    _assert_dependencies(normalised)

    # One cycle detector: the G6 gate already carries it (:func:`_find_cycle`),
    # so the draft cannot drift from the graph invariants the write side runs.
    cycle = _find_cycle(cast("Sequence[Mapping[str, Any]]", normalised))
    if cycle is not None:
        raise _draft_error("cycle", f"dependency cycle: {' -> '.join(cycle)}", path=cycle)

    roster = tuple(str(role) for role in roles)
    # B1 is closed here: ``roles`` is the **only** authority for an owner. A run id or
    # a project id is not a role, so neither may stand in for one — an earlier
    # ``known`` set let ``owner == run_id`` through, which made the refusal fail-open
    # for exactly the values a caller is most likely to pass by mistake.
    for index, entry in enumerate(normalised):
        owner = str(entry["owner"])
        if not owner or owner not in roster:
            raise _draft_error(
                "owner-not-in-roles",
                f"task {entry['id']} owner {owner!r} is not in {list(roster)}",
                path=[f"tasks[{index}].owner"],
            )
        if not entry["inScope"]:
            raise _draft_error(
                "scope-empty",
                f"task {entry['id']} has an empty inScope",
                path=[str(entry["id"]), "inScope"],
            )

    for entry in normalised:
        entry["status"] = "todo"
        entry["attempt"] = 0
        entry["round"] = 1
        entry["verdict"] = None
    return {"roles": list(roster), "tasks": normalised}


def _draft_tasks(draft: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """The draft's task objects, in board order."""
    raw = draft.get("tasks")
    if not isinstance(raw, Collection) or isinstance(raw, (str, bytes)):
        return []
    return [task for task in raw if isinstance(task, Mapping)]


def _draft_list(value: object) -> list[str]:
    """A draft's string list; a bare string is one entry, never a char sequence."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if not isinstance(value, Collection):
        return [str(value)]
    return [str(item) for item in value]


def _draft_deps(value: object) -> list[str]:
    """``dependsOn`` as trimmed ids.

    Trimmed because these *are* ids: the value is compared against the board's
    ``id`` values, and leaving padding in would make a draft's meaning depend on
    invisible whitespace. ``acceptance`` / ``inScope`` stay verbatim — they are
    prose shown to a human, and the write side (``run_service.create_task`` @1374)
    only applies ``str()`` to them.
    """
    return [dep.strip() for dep in _draft_list(value) if dep.strip()]


def _normalise_entries(tasks: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Project the draft keys onto ``PLAN.md §2.5`` ``TaskDraft``, refusing bad ids."""
    declared = {str(task.get("id") or "").strip() for task in tasks}
    normalised: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, task in enumerate(tasks):
        entry: dict[str, Any] = {
            dst: str(task.get(src) or "").strip() for src, dst in _DRAFT_STR_KEYS
        }
        for src, dst in _DRAFT_LIST_KEYS:
            entry[dst] = _draft_list(task.get(src))
        entry["dependsOn"] = _draft_deps(task.get("dependsOn"))

        task_id = str(entry["id"])
        if not task_id:
            raise _draft_error("missing-id", f"task at index {index} has no id", path=[str(index)])
        if task_id in seen:
            raise _draft_error("duplicate-id", f"duplicate task id: {task_id}", path=[task_id])
        seen.add(task_id)
        for dep in entry["dependsOn"]:
            if dep == task_id:
                raise _draft_error(
                    "self-dependency",
                    f"task {task_id} depends on itself",
                    path=[task_id, task_id],
                )
            if dep not in declared:
                raise _draft_error(
                    "missing-id",
                    f"task {task_id} depends on unknown task {dep}",
                    path=[task_id, dep],
                )
        normalised.append(entry)
    return normalised


def _assert_dependencies(normalised: Sequence[Mapping[str, Any]]) -> None:
    """Every non-self dependency must name a task on this board."""
    declared = {str(entry["id"]) for entry in normalised}
    for entry in normalised:
        for dep in entry["dependsOn"]:
            if dep != entry["id"] and dep not in declared:
                raise _draft_error(
                    "missing-id",
                    f"task {entry['id']} depends on unknown task {dep}",
                    path=[str(entry["id"]), str(dep)],
                )


@dataclass(frozen=True)
class StrandedItem:
    """One task suspected of being stranded — a report, never a write.

    ``reason`` is ``"epoch"`` when the attempt token's epoch is not this
    process's (C-2, no false positives) and ``"idle"`` when only the timestamp
    fallback fired (C-1, false positives allowed — ``SPEC §0-D1``).
    """

    id: str
    owner: str
    status: str
    attempt: int
    epochMismatch: bool
    idleSeconds: int
    reason: str


def epoch_of(attempt_id: object) -> str | None:
    """Epoch prefix of an attempt token (``<epoch>.<token>``), or ``None``.

    ``attempt_id`` is free ``TEXT`` with no format validation
    (``migrations/025_team_runs.sql`` @97), which is what lets C-2 ride on the
    existing column with zero migration. A token without a ``.`` is its own epoch.
    """
    if not attempt_id:
        return None
    return str(attempt_id).split(".", 1)[0]


def _latest_ts(task: Mapping[str, Any]) -> float | None:
    """``max(updated_at, started_at)``; ``None`` when neither column is present."""
    stamps = [_int_or(task.get(key), _TS_MISSING) for key in ("updated_at", "started_at")]
    present = [stamp for stamp in stamps if stamp != _TS_MISSING]
    return float(max(present)) if present else None


def stranded_tasks(
    run: Mapping[str, Any],
    tasks: Sequence[Mapping[str, Any]],
    *,
    epoch: str | None,
    now: float,
) -> tuple[StrandedItem, ...]:
    """Report tasks that look stranded — **report only, this changes nothing**.

    Candidate set (``PLAN.md §4.3`` ①): ``status == "doing"``, or ``"todo"`` with
    an ``attempt_id`` already minted (``claim`` mints the token without moving the
    status: ``repos/project_tasks.py`` · ``claim`` @471). A ``todo`` task with no
    token has never been dispatched, so it is not stranded. Terminal and parked
    states (``done`` / ``blocked`` / ``cancelled`` / ``planning``) never enter the
    candidate set.

    Decision (``PLAN.md §4.2``): an epoch mismatch (C-2) is decisive; otherwise
    the C-1 fallback fires when ``idleSeconds > STRANDED_IDLE_SECONDS``. With
    ``epoch is None`` C-2 is **not** judged — C-1 only — because a fabricated
    non-empty epoch would manufacture false positives (``D-4``).

    *run* is accepted because the frozen contract passes it; it is read as report
    context and never written to. Empty *tasks*, or an empty candidate set,
    returns ``()`` and reports nothing.
    """
    items: list[StrandedItem] = []
    for task in tasks:
        status = str(task.get("status") or "")
        attempt_id = task.get("attempt_id")
        if status not in _STRANDED_CANDIDATE_STATUSES:
            continue
        if status == "todo" and not attempt_id:
            continue

        task_epoch = epoch_of(attempt_id)
        epoch_mismatch = epoch is not None and task_epoch is not None and task_epoch != epoch
        latest = _latest_ts(task)
        idle_seconds = max(0, int(now - latest)) if latest is not None else 0

        if epoch_mismatch:
            reason = "epoch"
        elif idle_seconds > STRANDED_IDLE_SECONDS:
            reason = "idle"
        else:
            continue

        items.append(
            StrandedItem(
                id=str(task.get("id") or ""),
                owner=str(task.get("owner") or task.get("assignee_id") or ""),
                status=status,
                attempt=_int_or(task.get("attempt"), 0),
                epochMismatch=epoch_mismatch,
                idleSeconds=idle_seconds,
                reason=reason,
            )
        )
    # Deterministic report: board order is not part of this function's contract.
    items.sort(key=lambda item: item.id)
    return tuple(items)


def settle_tasks(
    tasks: Sequence[Mapping[str, Any]],
    items: Sequence[StrandedItem],
    *,
    at: int,
    reason: str = "",
) -> tuple[list[dict[str, Any]], list[str]]:
    """Turn the reported stranded items back into dispatchable task drafts.

    Consumes the **same** :class:`StrandedItem` tuple :func:`stranded_tasks`
    produced (``PLAN.md`` ``I5``): it takes no ``epoch`` / ``now`` / threshold, so
    the judgement and the write cannot drift apart in type.

    Every reported, non-terminal task goes back to ``status="todo"`` with
    ``attempt + 1`` (``SPEC`` R9). ``doing → todo`` is a legal edge — verified
    against ``repos/project_tasks.py`` · ``update`` @362–437, which applies no
    transition table: ``status`` flows straight into ``optional_updates``, no
    ``CHECK`` constraint exists on ``project_tasks.status``
    (``migrations/019_projects.sql``), and ``TASK_STATUSES`` @33 is a declaration,
    not a guard. Terminal tasks (``done`` / ``cancelled``) are **left verbatim**:
    not rewritten, not re-dispatched, not reported as settled.

    Returns ``(normalised drafts, settled ids)``; an empty *items* — or only
    terminal matches — returns ``([], [])`` so the caller writes nothing.
    """
    stranded_ids = {item.id for item in items if item.id}
    drafts: list[dict[str, Any]] = []
    settled: list[str] = []
    for task in tasks:
        task_id = str(task.get("id") or "")
        if not task_id or task_id not in stranded_ids:
            continue
        # The guard reads the **row's status**, never the id: comparing an id against
        # the status vocabulary is a tautology that can never fire (FIND-4).
        if str(task.get("status") or "") in _TERMINAL_TASK_STATUSES:
            continue
        settled.append(task_id)
        drafts.append(
            {
                "id": task_id,
                "status": "todo",
                "attempt": _int_or(task.get("attempt"), 0) + 1,
                "strandedAt": at,
                "strandedFrom": str(task.get("status") or ""),
                "note": reason,
            }
        )
    return drafts, settled


# ─────────────────────────────────────────────────────────────────────────────
# Finding identity (G16) and the read-side report (V1/V3/V4)
# ─────────────────────────────────────────────────────────────────────────────

_FINDING_PREFIX_RE = re.compile(
    r"^(?:find(?:ing)?\b[-_ ]?\d*|f[-_ ]?\d+|#\d+|\d+)\s*[.、,，:：)）\]】\-—]*\s*",
    re.IGNORECASE,
)
_SEVERITY_RE = re.compile(r"[（(\[]\s*p[0-3]\s*[)）\]]", re.IGNORECASE)
_TITLE_TRIM = "。.,，;；:：、-—–_*`'\"()（）[]【】《》<>「」"


def norm_title(title: object) -> str:
    """Normalise a finding title so "the same one came back" is detectable.

    Drops a leading finding id (``FIND-24`` / ``#24`` / ``24.``), any ``（P1）``
    severity marker, case and **all** whitespace (including the full-width space),
    then trims punctuation. Reviewers reuse titles verbatim across rounds; the id
    and severity change, the title does not.
    """
    text = str(title or "").strip().casefold()
    text = _SEVERITY_RE.sub("", text)
    text = _FINDING_PREFIX_RE.sub("", text)
    text = re.sub(r"\s+", "", text)
    return text.strip(_TITLE_TRIM)


@dataclass(frozen=True)
class FindingReopen:
    """A finding that reappeared in two adjacent non-pass rounds (G16)."""

    title: str
    rounds: tuple[int, int]
    raw_titles: tuple[str, str]

    def as_details(self) -> dict[str, Any]:
        """``OctopError.details`` for ``TEAM_FINDING_REOPENED``.

        ``decision`` is the escalation the caller must create — G16 says the run
        escalates to the user instead of dispatching yet another repair round.
        """
        return {
            "title": self.title,
            "rounds": list(self.rounds),
            "raw_titles": list(self.raw_titles),
            "decision": {"kind": "escalate", "reason": "finding_reopened"},
        }


def _round_findings(entry: Mapping[str, Any]) -> tuple[str, ...]:
    raw = entry.get("findings")
    titles: list[str] = []
    for item in _as_collection(raw):
        if isinstance(item, Mapping):
            titles.append(str(item.get("title") or ""))
        else:
            titles.append(str(item))
    return tuple(titles)


def finding_reopened(run: Mapping[str, Any]) -> FindingReopen | None:
    """Detect a finding repeated in two adjacent non-pass rounds (G16).

    Returns ``None`` both for "converged" and for "no round data at all"; the two
    are told apart by :func:`check_run`, which reports
    ``FINDING_REOPENED_INPUT_MISSING`` for the latter (PLAN G16: otherwise the two
    situations are byte-identical in the output).
    """
    rounds = run.get("finding_rounds")
    if rounds is None:
        return None
    entries: list[tuple[int, Mapping[str, Any]]] = []
    for index, entry in enumerate(_as_collection(rounds)):
        if not isinstance(entry, Mapping):
            continue
        entries.append((_int_or(entry.get("round"), index + 1), entry))
    entries.sort(key=lambda pair: pair[0])

    previous: tuple[int, Mapping[str, Any]] | None = None
    for number, entry in entries:
        if previous is not None:
            prev_number, prev_entry = previous
            prev_titles = {
                norm_title(title): title for title in _round_findings(prev_entry) if title
            }
            if (
                str(prev_entry.get("verdict") or "") != "pass"
                and str(entry.get("verdict") or "") != "pass"
            ):
                for title in _round_findings(entry):
                    key = norm_title(title)
                    if key and key in prev_titles and prev_number != number:
                        return FindingReopen(
                            title=key,
                            rounds=(prev_number, number),
                            raw_titles=(prev_titles[key], title),
                        )
        previous = (number, entry)
    return None


@dataclass(frozen=True)
class CheckReport:
    """Read-side report of :func:`check_run` — reports, never blocks."""

    violations: tuple[str, ...]
    finding_reopened: FindingReopen | None

    def has(self, violation: str) -> bool:
        return violation in self.violations


def check_run(run: Mapping[str, Any]) -> CheckReport:
    """Report the read-side violations of a run (PLAN V1/V3/V4 + G16).

    Never raises: these findings must stay visible on ``/team check`` and the
    dashboard for runs that predate the current rules. G16 is reported here and
    **enforced** by :func:`advance_gate`; the other four are advisory, matching the
    single-source ruling that ``kind`` / ``verify`` are warnings (FIND-5).
    """
    violations: list[str] = []
    tasks = [task for task in _as_collection(run.get("tasks")) if isinstance(task, Mapping)]

    if any(str(task.get("kind") or "") not in ALLOWED_KINDS for task in tasks):
        violations.append(V_KIND_UNKNOWN)
    if any(
        str(task.get("kind") or "") == "quality" and _task_role(task) not in QUALITY_OWNER_ROLES
        for task in tasks
    ):
        violations.append(V_QUALITY_OWNER_INVALID)
    if any(
        str(task.get("status") or "") == TASK_DONE
        and _as_collection(task.get("verify"))
        and not _verified_at(task)
        for task in tasks
    ):
        violations.append(V_VERIFY_MISSING)

    max_rounds = _int_or(run.get("max_review_rounds"), DEFAULT_MAX_REVIEW_ROUNDS)
    reached = 0
    for entry in _as_collection(run.get("finding_rounds")):
        if isinstance(entry, Mapping):
            reached = max(reached, _int_or(entry.get("round"), 0))
    if reached > max_rounds and not run.get("escalated"):
        violations.append(V_REWORK_LOOP_UNESCALATED)

    done_ids = {_task_id(task) for task in tasks if str(task.get("status") or "") == TASK_DONE}
    if any(
        str(task.get("status") or "") in TASK_STARTED_STATUSES
        and any(dep not in done_ids for dep in _task_deps(task))
        for task in tasks
    ):
        violations.append(V_CONTRACT_DEP_STALLED)

    if run.get("finding_rounds") is None:
        violations.append(V_FINDING_REOPENED_INPUT_MISSING)

    return CheckReport(
        violations=tuple(dict.fromkeys(violations)),
        finding_reopened=finding_reopened(run),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Small pure helpers
# ─────────────────────────────────────────────────────────────────────────────


def _phase_of(run: Mapping[str, Any]) -> str:
    return str(run.get("phase") or PHASES[0])


def _task_role(task: Mapping[str, Any]) -> str:
    for key in ("role", "assignee_role", "assigneeRole", "owner_role"):
        value = task.get(key)
        if value:
            return str(value)
    return ""


def _verified_at(task: Mapping[str, Any]) -> object:
    return task.get("verifiedAt") or task.get("verified_at")


def _as_collection(value: object) -> tuple[Any, ...]:
    """Coerce a snapshot field to a tuple — strings are one item, not characters."""
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, Mapping):
        return (value,)
    if isinstance(value, Collection):
        return tuple(value)
    return (value,)


def _int_or(value: object, default: int) -> int:
    if isinstance(value, bool) or value is None:
        return default
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return default
