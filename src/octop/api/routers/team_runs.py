"""Expert-team runs — the HTTP face of the run lifecycle (plan §API 面③).

Thin adapter (AGENTS.md §5): validate the request, call the run service, map
``OctopError``. There is no business rule and no SQL here — every gate lives in
``infra/agents/teams``; the service is taken from ``SharedServices``
(``server.services.team_run_service()``) and never imported as a class.

Authorisation follows the platform's existing model: a run is exactly as visible as
its team agent, so every route resolves the run's team row and checks ownership
through ``assert_agent_owner`` — admin bypass included, no second authorisation
model and no extra "loop guard".

``GET /team/runs/{run_id}/metrics`` delegates to ``teams/metrics.py`` (T-30) through
``teams/metrics_sources.load_sources`` (T-47): the loader reads the rows (a router must
not run SQL), the pure ``rollup`` renders the 12 sections, and each section is returned
with the state it can honestly claim (``measured`` / ``proxy`` / ``empty`` /
``partial`` — PLAN AM-26), so an empty section is never mistaken for a measured zero.

``GET …/export/{name}`` delegates to ``teams/export.py`` (T-14): the four read-only
projections (``TASKS.json``/``任务看板.md``/``STATE.json``/``ROSTER.json``) are
rendered from the DB and returned.

``GET/PUT …/artifacts`` combine two real sources: the run directory (content and its
content-addressed ``revision``) and the ``project_artifacts`` **index row**
(``kind='workflow'``) written by ``TeamRunService.write_artifact`` — which supplies
``owner_role`` / ``phase`` / ``version`` / ``hash`` / ``created_at``. An artifact that
has never been written through the service has no index row, so those fields are
``null`` for it: the route reports the absence rather than inventing values.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field

from octop.api.common.agent import assert_agent_owner
from octop.api.deps import current_user, get_server
from octop.infra.agents.teams.artifacts import ARTIFACT_OWNERS
from octop.infra.agents.teams.service import is_team_agent
from octop.infra.errors import ErrorCode, OctopError

router = APIRouter(prefix="/team/runs")

#: The plan's PATCH vocabulary. A value outside it never reaches the service: the
#: HTTP enum is the user-facing gate (`Literal` ⇒ 422, like every other router here).
TaskOp = Literal["claim", "start", "report", "complete", "fail", "rework"]


# ── request models ───────────────────────────────────────────────────────────


class RunCreateBody(BaseModel):
    """``POST /api/team/runs``."""

    team_agent_id: str = Field(description="The team agent that hosts this run.")
    goal: str = Field(description="What the run must achieve (1–4000 characters).")
    mode: Literal["one-shot", "persist"] = Field(
        default="one-shot",
        description=(
            "one-shot: members run as the host's `task` subagents (no room turn). "
            "persist: members are existing expert agents reached through the room."
        ),
    )
    deliverable: str = Field(default="code+artifacts")
    tier: Literal["quick", "standard", "strict"] | None = Field(
        default=None, description="Omitted ⇒ the standard tier."
    )
    roles: list[str] | None = Field(
        default=None,
        description=(
            "Explicit roster override. Omitted ⇒ the team manifest, trimmed to the "
            "tier's role cap (the trimmed roles are recorded, not dropped silently)."
        ),
    )
    host_agent_id: str | None = Field(
        default=None, description="Who chairs the run; omitted ⇒ the team host."
    )
    run_root: str | None = Field(
        default=None,
        description="`host_workspace` (default) or `explicit:<abs>` for a shared root.",
    )
    max_review_rounds: int = Field(default=3, ge=1, le=10)


class TaskCreateBody(BaseModel):
    """``POST /api/team/runs/{run_id}/tasks``."""

    id: str | None = Field(
        default=None,
        description=(
            "Caller-chosen task id (the plan's `id?`). Omitted, the server allocates one. "
            "A duplicate is refused before anything is written (`TEAM_TASK_GRAPH_INVALID`)."
        ),
    )
    title: str
    kind: str = Field(default="work", description="One of the ten task kinds.")
    owner: str = Field(default="", description="The role that owns the task.")
    spec: str = ""
    acceptance: list[str] = Field(default_factory=list)
    inScope: list[str] = Field(default_factory=list, description="File/directory globs.")
    verify: list[str] = Field(default_factory=list, description="Commands that must pass.")
    dependsOn: list[str] = Field(default_factory=list)
    phase: str | None = None
    round: int | None = Field(default=None, ge=1)


class FindingIn(BaseModel):
    title: str
    severity: Literal["low", "medium", "high", "blocker"] = "medium"
    detail: str = ""
    round: int | None = Field(default=None, ge=1)


class TaskPatchBody(BaseModel):
    """``PATCH /api/team/runs/{run_id}/tasks/{task_id}``. One op per call."""

    attemptId: str = Field(
        description=(
            "The attempt the caller holds. A superseded token is refused with "
            "`TEAM_ATTEMPT_STALE`; claim mints the token it returns."
        )
    )
    op: TaskOp
    status: str | None = None
    verdict: Literal["pass", "needs_revision", "reject"] | None = None
    findings: list[FindingIn] = Field(default_factory=list)
    changedPaths: list[str] = Field(
        default_factory=list, description="Audited against the task's `inScope` (G11)."
    )
    role: str = ""
    round: int | None = Field(default=None, ge=1, description="`rework` only.")


class AdvanceBody(BaseModel):
    to_phase: str
    note: str | None = None


class DecisionBody(BaseModel):
    decision_id: str
    choice: str
    note: str | None = None


class ArtifactPutBody(BaseModel):
    content: str
    revision: str = Field(
        default="",
        description=(
            'The revision read with the content; `""` creates the file. A mismatch '
            "is `TEAM_ARTIFACT_STALE` (compare-and-set, G14)."
        ),
    )
    role: str = Field(description="Checked against the artifact ownership table.")


# ── response models ──────────────────────────────────────────────────────────


class PhaseOut(BaseModel):
    phase: str
    seq: int
    status: str = Field(description="pending | active | passed | failed | skipped")
    gate_detail: dict[str, Any] = Field(
        default_factory=dict,
        description="Gate notes, e.g. `skipped_roles` for roles the tier trimmed.",
    )
    entered_at: int | None = None
    passed_at: int | None = None


class MemberOut(BaseModel):
    role: str
    agent_id: str
    is_lead: bool


class RunSummaryOut(BaseModel):
    run_id: str
    project_id: str
    team_agent_id: str
    goal: str
    mode: str
    deliverable: str
    tier: str
    status: str = Field(description="running | awaiting_confirmation | awaiting_decision | …")
    phase: str
    room_thread_id: str | None = None
    max_review_rounds: int
    created_at: int
    updated_at: int
    strandedCount: int = Field(
        default=0,
        description=(
            "Reported stranded tasks right now (idle past the threshold, or claimed by "
            "a previous process generation). Reported, never settled: only an explicit "
            "`POST /{run_id}:settle` writes."
        ),
    )


class RunDetailOut(RunSummaryOut):
    phases: list[PhaseOut] = Field(default_factory=list)
    members: list[MemberOut] = Field(default_factory=list)
    allowed_phases: list[str] = Field(
        default_factory=list, description="What `:advance` would accept right now."
    )
    pending_decision: dict[str, Any] | None = None


class TaskNodeOut(BaseModel):
    id: str
    title: str
    kind: str
    owner: str = Field(description="The role the task belongs to.")
    status: str = Field(description="Storage status: planning | todo | doing | review | …")
    phase: str | None = None
    round: int
    attempt: int
    attemptId: str | None = None
    verdict: str | None = None
    acceptance: list[str] = Field(default_factory=list)
    inScope: list[str] = Field(default_factory=list)
    verify: list[str] = Field(default_factory=list)
    dependsOn: list[str] = Field(default_factory=list)
    changedPaths: list[str] = Field(default_factory=list)


class TaskEdgeOut(BaseModel):
    from_: str = Field(alias="from", serialization_alias="from")
    to: str


class ViolationOut(BaseModel):
    code: str
    detail: str
    task_id: str | None = None


class TaskBoardOut(BaseModel):
    nodes: list[TaskNodeOut]
    edges: list[TaskEdgeOut]
    violations: list[ViolationOut]


class StrandedOut(BaseModel):
    """Count / ids / reasons only — never task bodies or file paths (SPEC §5.3 ⑩)."""

    count: int = 0
    ids: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list, description="`idle` or `epoch`, per id.")

    @classmethod
    def from_items(cls, items: Sequence[Any]) -> StrandedOut:
        return cls(
            count=len(items),
            ids=[str(item.id) for item in items],
            reasons=[str(item.reason) for item in items],
        )


class CheckOut(BaseModel):
    violations: list[str] = Field(
        description="Read-side warning keys (V1/V3/V4 …): reported, never blocking."
    )
    finding_reopened: dict[str, Any] | None = None
    stranded: StrandedOut = Field(
        default_factory=lambda: StrandedOut(),
        description=(
            "Stranded tasks, computed by the route next to the check report. This is a "
            "**field, not a violation key** — `violations` above stays byte-identical, "
            "so a run that predates these rules never turns red. Reports, never blocks."
        ),
    )


class PlanDraft(BaseModel):
    """The staged plan draft, verbatim as it sits on the pending decision payload."""

    roles: list[str] = Field(default_factory=list)
    tasks: list[dict[str, Any]] = Field(default_factory=list)
    updatedAt: int | None = None
    planStatus: str | None = Field(default=None, description="`staged` while unapproved.")
    discarded: dict[str, Any] | None = Field(
        default=None, description="`{at, reason, taskCount}` once `:discard` released the draft."
    )


class PlanDraftBody(BaseModel):
    draft: dict[str, Any] = Field(
        description="`{roles: list[str], tasks: list[dict]}` — validated by the service."
    )


class DiscardBody(BaseModel):
    reason: str = ""


class SettleBody(BaseModel):
    taskIds: list[str] = Field(
        default_factory=list, description="Empty = every reported stranded task."
    )
    reason: str = ""


class PlanDraftOut(BaseModel):
    draft: PlanDraft


class PlanApproveOut(BaseModel):
    tasks: list[TaskNodeOut]
    settledKept: list[str] = Field(description="Settled task ids the merge kept.")


class SettleOut(BaseModel):
    settled: list[str] = Field(description="Task ids returned to the board; `[]` = no write.")


class ArtifactItemOut(BaseModel):
    name: str
    present: bool = Field(description="Whether the file exists in the run directory now.")
    owners: list[str] | None = Field(
        default=None,
        description=(
            "Roles allowed to overwrite this file (the ownership table, the live "
            "authority). `[]` = runtime-only, nobody overwrites; `null` = unrestricted."
        ),
    )
    revision: str | None = Field(
        default=None,
        description="Content hash of the file on disk; `null` when it is absent.",
    )
    owner_role: str | None = Field(
        default=None,
        description=(
            "Owning role, from the `project_artifacts` index row. `null` until the "
            "artifact has been written through the service (no row yet); `owners` "
            "above is the live authority for overwrite checks either way."
        ),
    )
    phase: str | None = Field(
        default=None, description="The run phase that produced it (`null` before the index row)."
    )
    version: int | None = Field(
        default=None,
        description=(
            "Index-row rewrite counter (starts at 1, +1 per rewrite). **Not** `revision`: "
            "`revision` is the file body's content hash used as the CAS token."
        ),
    )
    hash: str | None = Field(
        default=None, description="Body hash recorded on the index row (`null` before it exists)."
    )
    created_at: int | None = Field(
        default=None, description="When the index row was created (`null` before it exists)."
    )


class ArtifactOut(BaseModel):
    name: str
    content: str
    revision: str = Field(description='Content-addressed; `""` when the file is absent.')


class ArtifactWriteOut(BaseModel):
    name: str
    revision: str
    hash: str


class ArtifactListOut(BaseModel):
    items: list[ArtifactItemOut]


class DecisionOut(BaseModel):
    decision_id: str
    status: str
    choice: str | None = None
    kind: str | None = None


class FeedEntryOut(BaseModel):
    action: str
    actor: str
    at: int
    task_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class RunStateOut(BaseModel):
    """``GET …/state?section=`` — one section per call (progressive loading)."""

    section: str
    run: RunSummaryOut
    phases: list[PhaseOut] = Field(default_factory=list)
    members: list[MemberOut] = Field(default_factory=list)
    tasks: list[TaskNodeOut] = Field(default_factory=list)
    artifacts: list[ArtifactItemOut] = Field(default_factory=list)
    feed: list[FeedEntryOut] = Field(default_factory=list)
    check: CheckOut | None = None


class MetricSectionOut(BaseModel):
    title: str
    lines: list[str] = Field(description="The section body, exactly as the rollup renders it.")
    state: str = Field(
        description=(
            "measured | proxy | empty | partial — what this section's value is worth. "
            "`empty` means the event family does not exist yet (PLAN AM-26), never "
            "'nothing happened'."
        )
    )
    note: str = Field(default="", description="Why the section is in that state.")


class MetricsOut(BaseModel):
    sections: list[MetricSectionOut] = Field(description="The 12 sections, in plan order.")
    rendered: str = Field(
        description="The same snapshot as `METRICS.md` — byte-identical for the same rows."
    )


class ExportOut(BaseModel):
    name: str = Field(description="The projection that was asked for.")
    content: str = Field(description="Its exact bytes — re-exporting the same state is identical.")
    files: list[str] = Field(
        default_factory=list, description="Every projection the export pass refreshed."
    )


class DispatchOut(BaseModel):
    task_id: str
    channel: str = Field(description="ask_agent (persist, room turn) | task (one-shot).")
    thread_id: str | None = None


# ── helpers ──────────────────────────────────────────────────────────────────


def _service(server: Any) -> Any:
    """The run service, built lazily by ``SharedServices`` (never imported here)."""
    return server.services.team_run_service()


def _team_row(server: Any, team_agent_id: str) -> Any:
    assert server.app_runtime is not None
    row = server.app_runtime.agent_registry.get_row(team_agent_id)
    if row is None or not is_team_agent(row):
        raise OctopError(ErrorCode.TEAM_NOT_FOUND, f"team {team_agent_id!r} not found")
    return row


def _require_owned_run(server: Any, user: Any, run_id: str) -> Any:
    run = _service(server).require_run(run_id)
    assert_agent_owner(_team_row(server, run.team_agent_id), user)
    return run


def _run_out(run: Any) -> RunSummaryOut:
    return RunSummaryOut(
        run_id=run.run_id,
        project_id=run.project_id,
        team_agent_id=run.team_agent_id,
        goal=run.goal,
        mode=run.mode,
        deliverable=run.deliverable,
        tier=run.tier,
        status=run.status,
        phase=run.phase,
        room_thread_id=run.room_thread_id,
        max_review_rounds=run.max_review_rounds,
        created_at=run.created_at,
        updated_at=run.updated_at,
    )


def _phase_out(row: Any) -> PhaseOut:
    return PhaseOut(
        phase=row.phase,
        seq=row.seq,
        status=row.status,
        gate_detail=dict(row.gate_detail or {}),
        entered_at=row.entered_at,
        passed_at=row.passed_at,
    )


def _member_out(row: Any) -> MemberOut:
    return MemberOut(role=row.role, agent_id=row.agent_id, is_lead=row.is_lead)


def _task_out(row: Any) -> TaskNodeOut:
    return TaskNodeOut(
        id=row.id,
        title=row.title,
        kind=row.kind,
        owner=(row.assignee_id if row.assignee_type == "team" else "") or (row.claimed_by or ""),
        status=row.status,
        phase=row.phase,
        round=row.round,
        attempt=row.attempt,
        attemptId=row.attempt_id,
        verdict=row.verdict,
        acceptance=list(row.acceptance),
        inScope=list(row.in_scope),
        verify=list(row.verify),
        dependsOn=list(row.deps),
        changedPaths=list(row.changed_paths),
    )


def _edges(nodes: list[TaskNodeOut]) -> list[TaskEdgeOut]:
    return [
        TaskEdgeOut.model_validate({"from": dep, "to": node.id})
        for node in nodes
        for dep in node.dependsOn
    ]


def _artifact_items(service: Any, run: Any, rows: Sequence[Any] = ()) -> list[ArtifactItemOut]:
    """The ownership table ∪ what is present in the run dir ∪ the workflow index rows."""
    present = set(service.present_artifacts(run))
    indexed = {row.name: row for row in rows}
    names = sorted(set(ARTIFACT_OWNERS) | present | set(indexed))
    items: list[ArtifactItemOut] = []
    for name in names:
        owners = ARTIFACT_OWNERS.get(name)
        row = indexed.get(name)
        revision = None
        if name in present:
            revision = service.read_artifact(run.run_id, name)[1]
        items.append(
            ArtifactItemOut(
                name=name,
                present=name in present,
                owners=list(owners) if owners is not None else None,
                revision=revision,
                owner_role=getattr(row, "owner_role", None),
                phase=getattr(row, "phase", None),
                version=getattr(row, "version", None),
                hash=getattr(row, "hash", None),
                created_at=getattr(row, "created_at", None),
            )
        )
    return items


def _workflow_rows(server: Any, run: Any) -> list[Any]:
    """The run project's workflow index rows (read via SharedServices — no SQL here)."""
    return list(server.services.project_artifact_repo.list_workflow(project_id=run.project_id))


# ── routes ───────────────────────────────────────────────────────────────────


@router.post(
    "",
    response_model=RunDetailOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create an expert-team run",
    description=(
        "Creates the run's project, the run row, a run-scoped room thread, the roster "
        "and the tier's phases in one call. The goal is validated first, so a refused "
        "request leaves nothing behind.\n\n"
        "**Run ids are second-precision** (`<YYYY-MM-DD-HHMMSS>`, the run directory "
        "name). Two runs created in the same second therefore conflict — retrying a "
        "second later is the fix; that is the `409 TEAM_RUN_CONFLICT` this route can "
        "return."
    ),
)
async def create_run(
    body: RunCreateBody,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> RunDetailOut:
    assert_agent_owner(_team_row(server, body.team_agent_id), user)
    run = _service(server).create(
        team_agent_id=body.team_agent_id,
        user=user,
        goal=body.goal,
        mode=body.mode,
        deliverable=body.deliverable,
        tier=body.tier,
        roles=body.roles,
        host_agent_id=body.host_agent_id,
        run_root=body.run_root,
        max_review_rounds=body.max_review_rounds,
    )
    return _detail(server, run)


@router.get(
    "",
    response_model=list[RunSummaryOut],
    summary="List expert-team runs",
    description=(
        "Runs of the teams this user owns. With `team_id`, that team's runs only "
        "(ownership of the team is still checked)."
    ),
)
async def list_runs(
    team_id: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> list[RunSummaryOut]:
    runs = server.services.team_run_repo
    if team_id is not None:
        assert_agent_owner(_team_row(server, team_id), user)
        return [_run_out(row) for row in runs.list(team_agent_id=team_id, status=status_filter)]
    rows = runs.list(status=status_filter)
    visible: list[RunSummaryOut] = []
    for row in rows:
        try:
            assert_agent_owner(_team_row(server, row.team_agent_id), user)
        except OctopError:
            continue
        visible.append(_run_out(row))
    return visible


@router.get(
    "/{run_id}",
    response_model=RunDetailOut,
    summary="Run detail",
    description="The run row plus its phases, roster, allowed next phases and pending decision.",
)
async def get_run(
    run_id: str,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> RunDetailOut:
    return _detail(server, _require_owned_run(server, user, run_id))


@router.get(
    "/{run_id}/state",
    response_model=RunStateOut,
    summary="Run state, one section at a time",
    description=(
        "Progressive sections: `summary` (default), `people`, `feed`, `artifacts`, "
        "`tasks`, `check`. Only the requested section is filled; the rest stay empty "
        "arrays so a client can render incrementally without a fat payload."
    ),
)
async def get_state(
    run_id: str,
    section: Literal["summary", "people", "feed", "artifacts", "tasks", "check"] = Query(
        default="summary"
    ),
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> RunStateOut:
    run = _require_owned_run(server, user, run_id)
    service = _service(server)
    out = RunStateOut(section=section, run=_run_out(run))
    if section == "people":
        out.phases = [_phase_out(row) for row in server.services.team_run_repo.list_phases(run_id)]
        out.members = [
            _member_out(row) for row in server.services.team_run_repo.list_members(run_id)
        ]
    elif section == "feed":
        out.feed = [
            FeedEntryOut(
                action=event.action,
                actor=event.actor,
                at=event.at,
                task_id=event.task_id,
                payload=dict(event.payload or {}),
            )
            for event in reversed(
                server.services.timeline_repo.list_by_project(run.project_id, limit=50)
            )
        ]
    elif section == "artifacts":
        out.artifacts = _artifact_items(service, run, _workflow_rows(server, run))
    elif section == "tasks":
        out.tasks = [_task_out(row) for row in service.list_tasks(run_id)]
    elif section == "check":
        report = service.check(run_id)
        out.check = CheckOut(
            violations=list(report.violations),
            finding_reopened=(
                report.finding_reopened.as_details() if report.finding_reopened else None
            ),
            # The same field the `/check` route adds: one `CheckOut` shape, one meaning
            # (reported, never blocking, never a violation key).
            stranded=StrandedOut.from_items(service.stranded(run_id)),
        )
    return out


@router.post(
    "/{run_id}:advance",
    response_model=RunDetailOut,
    summary="Advance the run to the next phase",
    description=(
        "Goes through the pipeline gates: phase order, the confirmation gate, the "
        "SPEC boundary table and the reopened-finding gate. A refusal is a 409 whose "
        "`details.allowed` lists what would have been accepted; a reopened finding "
        "also parks an escalation decision on the run."
    ),
)
async def advance_run(
    run_id: str,
    body: AdvanceBody,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> RunDetailOut:
    _require_owned_run(server, user, run_id)
    run = _service(server).advance(run_id, to_phase=body.to_phase, user=user)
    return _detail(server, run)


@router.get(
    "/{run_id}/tasks",
    response_model=TaskBoardOut,
    summary="Task board: nodes, edges and read-side violations",
    description="`violations` are advisory (kind/verify warnings); they never block.",
)
async def list_tasks(
    run_id: str,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> TaskBoardOut:
    _require_owned_run(server, user, run_id)
    service = _service(server)
    nodes = [_task_out(row) for row in service.list_tasks(run_id)]
    report = service.check(run_id)
    violations = [
        ViolationOut(code=code, detail=str(code), task_id=None) for code in report.violations
    ]
    return TaskBoardOut(nodes=nodes, edges=_edges(nodes), violations=violations)


@router.post(
    "/{run_id}/tasks",
    response_model=TaskNodeOut,
    status_code=status.HTTP_201_CREATED,
    summary="Add a task to the run board",
    description=(
        "The single task-creation entry: the dependency graph is validated on every "
        "write, the tier's task cap is enforced, and creating work past the review "
        "budget without an escalation decision is refused (409 `TEAM_REWORK_LOOP_LIMIT`)."
    ),
)
async def create_task(
    run_id: str,
    body: TaskCreateBody,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> TaskNodeOut:
    _require_owned_run(server, user, run_id)
    task = _service(server).create_task(
        run_id,
        task_id=body.id,
        title=body.title,
        kind=body.kind,
        role=body.owner,
        spec=body.spec,
        acceptance=body.acceptance,
        in_scope=body.inScope,
        verify=body.verify,
        depends_on=body.dependsOn,
        phase=body.phase,
        round=body.round,
        user=user,
    )
    return _task_out(task)


@router.post(
    "/{run_id}:plan",
    response_model=PlanDraftOut,
    summary="Stage a plan draft on the run's decision gate",
    description=(
        "Validates the draft first (owners inside `roles`, dependency graph, `inScope`, "
        "caps), so an invalid draft writes nothing and answers 422 "
        "`TEAM_PLAN_DRAFT_INVALID` — a draft over the tier's task cap answers 409 "
        "`TEAM_RUN_TASK_LIMIT` instead, judged on the draft's own task count. A valid "
        "draft is parked **inside** the pending "
        "decision, which keeps `:advance` refused (409 `TEAM_DECISION_PENDING`) until it "
        "is approved or discarded. Re-staging overwrites: one draft, last write wins."
    ),
)
async def stage_plan_route(
    run_id: str,
    body: PlanDraftBody,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> PlanDraftOut:
    _require_owned_run(server, user, run_id)
    payload = _service(server).stage_plan(run_id, draft=body.draft, user=user)
    return PlanDraftOut(draft=PlanDraft.model_validate(payload.get("draft") or {}))


@router.post(
    "/{run_id}:approve",
    response_model=PlanApproveOut,
    summary="Approve the staged plan draft and write its tasks",
    description=(
        "One merge write: the settled tasks (`done` / `blocked` / `cancelled`) are kept "
        "verbatim and every other existing task is replaced by the draft. Both sides of "
        "the merge are judged before the first write, so a refusal leaves the board "
        "untouched. No draft staged (or the same call twice) is 409 "
        "`TEAM_PLAN_DRAFT_MISSING`. `TASKS.json` is a projection and is not written here."
    ),
)
async def approve_plan_route(
    run_id: str,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> PlanApproveOut:
    _require_owned_run(server, user, run_id)
    service = _service(server)
    created = service.approve_plan(run_id, user=user)
    created_ids = {task.id for task in created}
    # The service returns the draft rows only; what the merge *kept* is the settled
    # remainder of the board once the write landed (T4 interface note).
    settled_kept = [task.id for task in service.list_tasks(run_id) if task.id not in created_ids]
    return PlanApproveOut(tasks=[_task_out(task) for task in created], settledKept=settled_kept)


@router.post(
    "/{run_id}:discard",
    response_model=PlanDraftOut,
    summary="Discard the staged plan draft",
    description=(
        "Run-level, the only scope Octop has. The pending decision is cancelled "
        "(`discarded: {at, reason, taskCount}`) and the `draft` key is removed; "
        "`team_runs.status` is left alone, so unparking stays `:resume`'s call. No draft "
        "staged — including a repeated discard — is 409 `TEAM_PLAN_DRAFT_MISSING`."
    ),
)
async def discard_plan_route(
    run_id: str,
    body: DiscardBody,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> PlanDraftOut:
    _require_owned_run(server, user, run_id)
    payload = _service(server).discard_plan(run_id, reason=body.reason, user=user)
    return PlanDraftOut(draft=PlanDraft(discarded=payload.get("discarded")))


@router.post(
    "/{run_id}:settle",
    response_model=SettleOut,
    summary="Settle reported stranded tasks back onto the board",
    description=(
        "The only stranded write: each selected task returns to `todo` as a fresh "
        "attempt (`attempt + 1`, rotated `attemptId`), which is what leaves a previous "
        "holder's token stale (409 `TEAM_ATTEMPT_STALE`). Nothing stranded or nothing "
        "selected writes nothing and is an empty list, not an error."
    ),
)
async def settle_run(
    run_id: str,
    body: SettleBody,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> SettleOut:
    _require_owned_run(server, user, run_id)
    settled = _service(server).settle(run_id, task_ids=body.taskIds, reason=body.reason, user=user)
    return SettleOut(settled=[str(task_id) for task_id in settled])


@router.patch(
    "/{run_id}/tasks/{task_id}",
    response_model=TaskNodeOut,
    summary="Task op: claim / start / report / complete / fail / rework",
    description=(
        "One op per call, all guarded by `attemptId`:\n\n"
        "* `claim` — refuses unmet dependencies (G5) and a lost race "
        "(`TEAM_TASK_CLAIM_CONFLICT`); returns the new attempt token.\n"
        "* `start` — stamps `started_at`, moves the task to `doing`.\n"
        "* `report` — progress write; omit `verdict` for a plain report. With a "
        "`verdict` it is a **review judgement** and goes through the same two review "
        "gates as any other writer: `needs_revision`/`reject` require at least one "
        "`findings` entry (G12, `TEAM_VERDICT_FINDINGS_REQUIRED`) and a `pass` on a "
        "review task is refused while the reviewer is the round's implementer "
        "(G13, `TEAM_REVIEW_SELF_AUDIT`); the `findings` are persisted. A superseded "
        "token is `TEAM_ATTEMPT_STALE` (G8).\n"
        "* `complete` — audits `changedPaths` against `inScope` (G11) before writing.\n"
        "* `fail` — blocks the task (dependents stay locked).\n"
        "* `rework` — the `review → doing` edge, opening the next round.\n\n"
        "A verdict is only ever written through that one path — `report` with a "
        "`verdict` is the same code as a review verdict, never a second, ungated one."
    ),
)
async def patch_task(
    run_id: str,
    task_id: str,
    body: TaskPatchBody,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> TaskNodeOut:
    _require_owned_run(server, user, run_id)
    service = _service(server)
    if body.op == "claim":
        task = service.claim(run_id, task_id, role=body.role, user=user)
    elif body.op == "start":
        task = service.start(run_id, task_id, role=body.role, attempt_id=body.attemptId, user=user)
    elif body.op == "report":
        if body.verdict is None:
            # A plain progress report — unchanged, and deliberately so: only a
            # *verdict* is a review judgement.
            task = service.report(
                run_id,
                task_id,
                attempt_id=body.attemptId,
                verdict=None,
                changed_paths=body.changedPaths,
                user=user,
            )
        else:
            # T-68: a verdict goes through its single implementation. Before this,
            # the route called ``report()`` — the inner writer ``verdict()`` itself
            # uses — which meant G12 (findings required) and G13 (no self-audit)
            # were **never enforced over HTTP**, and the request's ``findings`` were
            # dropped on the floor (``report()`` has no such parameter), so the
            # premise behind ``TEAM_FINDING_REOPENED`` could never be built.
            task = service.verdict(
                run_id,
                task_id,
                role=body.role,
                attempt_id=body.attemptId,
                verdict=body.verdict,
                findings=[item.model_dump() for item in body.findings],
                user=user,
            )
    elif body.op == "complete":
        task = service.complete(
            run_id,
            task_id,
            role=body.role,
            attempt_id=body.attemptId,
            changed_paths=body.changedPaths,
            user=user,
        )
    elif body.op == "fail":
        task = service.fail(run_id, task_id, role=body.role, attempt_id=body.attemptId, user=user)
    else:
        task = service.rework(
            run_id,
            task_id,
            role=body.role,
            attempt_id=body.attemptId,
            round=body.round,
            user=user,
        )
    return _task_out(task)


@router.post(
    "/{run_id}/tasks/{task_id}:dispatch",
    response_model=DispatchOut,
    summary="Dispatch a task down the run's channel",
    description=(
        "`persist` runs a real room turn (`ask_agent`) on a **run-scoped** session key; "
        "`one-shot` hands the work to the host's `task` subagents and starts no room "
        "turn. The channel is reported back so the two are never conflated.\n\n"
        "This route is not in the plan's route table — it is the HTTP entry for the two "
        "channels PLAN 必答 C requires; the lead can move it if a later card owns it."
    ),
)
async def dispatch_task(
    run_id: str,
    task_id: str,
    body: TaskPatchBody | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> DispatchOut:
    _require_owned_run(server, user, run_id)
    role = body.role if body is not None else ""
    outcome = await _service(server).dispatch_task(run_id, task_id, role=role, user=user)
    return DispatchOut(
        task_id=outcome.task_id, channel=outcome.channel, thread_id=outcome.thread_id
    )


@router.get(
    "/{run_id}/metrics",
    response_model=MetricsOut,
    summary="Run metrics (the 12-section snapshot)",
    description=(
        "Aggregates the run's timeline, task board, findings and room usage into the "
        "plan's 12 sections. Idempotent: the same rows always render byte-identically.\n\n"
        "**Every section carries its state.** Five event families the upstream metrics "
        "want (`first-runnable`, `freeze`, `error:*`, `ask`, `scan:single-source`) are "
        "not in the timeline vocabulary yet (PLAN AM-26), so those sections are marked "
        '`empty`/`proxy` on purpose: an empty section must never read as "nothing '
        'happened" when the truth is "nobody recorded it". The token section keeps '
        "its own three states (value / no token metric / provider omits).\n\n"
        "**Token cost is the run's room thread.** Turns executed through the one-shot "
        "`task` channel run inside the host and are **not** counted here — the boundary "
        "is stated in the section note too, so an unmetered channel cannot read as "
        '"no consumption".'
    ),
)
async def get_metrics(
    run_id: str,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> MetricsOut:
    run = _require_owned_run(server, user, run_id)
    from octop.infra.agents.teams.metrics import rollup
    from octop.infra.agents.teams.metrics_sources import load_sources, section_states

    states = {item["title"]: item for item in section_states()}
    snapshot = rollup(load_sources(services=server.services, run=run))
    sections = [
        MetricSectionOut(
            title=title,
            lines=list(lines),
            state=states.get(title, {}).get("state", "measured"),
            note=states.get(title, {}).get("note", ""),
        )
        for title, lines in snapshot.sections
    ]
    return MetricsOut(sections=sections, rendered=snapshot.render())


@router.get(
    "/{run_id}/export/{name}",
    response_model=ExportOut,
    summary="Export one of the four run projections",
    description=(
        "Renders `TASKS.json`, `任务看板.md`, `STATE.json` and `ROSTER.json` from the "
        "database **one way only** (nothing is ever read back from these files) and "
        "returns the requested one. The projector also writes all four into the run "
        "directory — that materialisation is its contract, which is why this GET has a "
        "side effect. The upstream status tokens (`pending`/`claimed`/`in_progress`/…) "
        "appear in `TASKS.json` only; storage statuses everywhere else."
    ),
)
async def export_run_route(
    run_id: str,
    name: Literal["TASKS.json", "任务看板.md", "STATE.json", "ROSTER.json"],
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> ExportOut:
    _require_owned_run(server, user, run_id)
    from octop.infra.agents.teams.export import export_run

    files = await export_run(_service(server), run_id)
    return ExportOut(name=name, content=str(files[name]), files=sorted(files))


@router.get(
    "/{run_id}/check",
    response_model=CheckOut,
    summary="Read-side check (reports, never blocks)",
    description=(
        "V1/V3/V4 warnings plus the reopened-finding report. `advance` enforces the "
        "blocking half; this endpoint is how the panel stays honest about runs that "
        "predate the current rules.\n\n"
        "`stranded` is a **response field computed here**, not a violation key: "
        "`violations` is byte-identical to what it was before the field existed, so an "
        "old run never turns red — this endpoint reports, never blocks, and never writes."
    ),
)
async def check_run(
    run_id: str,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> CheckOut:
    _require_owned_run(server, user, run_id)
    service = _service(server)
    report = service.check(run_id)
    return CheckOut(
        violations=list(report.violations),
        finding_reopened=(
            report.finding_reopened.as_details() if report.finding_reopened else None
        ),
        stranded=StrandedOut.from_items(service.stranded(run_id)),
    )


@router.get(
    "/{run_id}/artifacts",
    response_model=ArtifactListOut,
    summary="Run artifacts: what exists, who may overwrite it",
    description=(
        "Every name in the ownership table plus whatever is present in the run "
        "directory. `owners: []` means runtime-only (no role may overwrite it).\n\n"
        "`owner_role` / `phase` / `version` / `hash` / `created_at` come from the "
        "`project_artifacts` index row (`kind='workflow'`) that `PUT …/artifacts/{name}` "
        "writes. An artifact never written through the service has no row yet, so those "
        "fields stay `null` for it — the absence is reported, never guessed."
    ),
)
async def list_artifacts(
    run_id: str,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> ArtifactListOut:
    run = _require_owned_run(server, user, run_id)
    return ArtifactListOut(
        items=_artifact_items(_service(server), run, _workflow_rows(server, run))
    )


@router.get(
    "/{run_id}/artifacts/{name}",
    response_model=ArtifactOut,
    summary="Read one artifact and its revision",
    description="`revision` is what a `PUT` must send back (content-addressed CAS).",
)
async def get_artifact(
    run_id: str,
    name: str,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> ArtifactOut:
    _require_owned_run(server, user, run_id)
    content, revision = _service(server).read_artifact(run_id, name)
    return ArtifactOut(name=name, content=content, revision=revision)


@router.put(
    "/{run_id}/artifacts/{name}",
    response_model=ArtifactWriteOut,
    summary="Write one artifact (ownership + revision CAS)",
    description=(
        "Two refusals: the role is not allowed to overwrite this file "
        "(`TEAM_ARTIFACT_OWNERSHIP_DENIED`), or `revision` is not what is on disk "
        "(`TEAM_ARTIFACT_STALE`). Creating a file is allowed — that is what lets the "
        "run skeleton land. The write is the last step, so a refusal changes nothing."
    ),
)
async def put_artifact(
    run_id: str,
    name: str,
    body: ArtifactPutBody,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> ArtifactWriteOut:
    _require_owned_run(server, user, run_id)
    written = _service(server).write_artifact(
        run_id, name=name, content=body.content, revision=body.revision, role=body.role, user=user
    )
    return ArtifactWriteOut(
        name=str(written["name"]), revision=str(written["revision"]), hash=str(written["hash"])
    )


@router.post(
    "/{run_id}/decision",
    response_model=DecisionOut,
    summary="Resolve the run's pending decision",
    description=(
        "Submitting a decision that is not pending — including the same one twice — is "
        "`TEAM_DECISION_NOT_PENDING`; a choice outside the offered options is "
        "`TEAM_DECISION_OPTION_INVALID`."
    ),
)
async def decide_run(
    run_id: str,
    body: DecisionBody,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> DecisionOut:
    _require_owned_run(server, user, run_id)
    resolved = _service(server).decide(
        run_id, decision_id=body.decision_id, choice=body.choice, note=body.note or "", user=user
    )
    return DecisionOut(
        decision_id=str(resolved.get("id") or body.decision_id),
        status=str(resolved.get("status") or "resolved"),
        choice=str(resolved.get("choice") or body.choice),
        kind=str(resolved.get("kind") or "") or None,
    )


@router.post(
    "/{run_id}:resume",
    response_model=RunSummaryOut,
    summary="Resume a parked run",
    description=(
        "Only from a non-terminal state; a finished run is `TEAM_RUN_TERMINAL`. The "
        "response adds `strandedCount` — reported, **not** settled: only an explicit "
        "`POST /{run_id}:settle` returns a stranded task to the board."
    ),
)
async def resume_run(
    run_id: str,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> RunSummaryOut:
    _require_owned_run(server, user, run_id)
    service = _service(server)
    out = _run_out(service.resume(run_id, user=user))
    out.strandedCount = len(service.stranded(run_id))
    return out


@router.post(
    "/{run_id}:cancel",
    response_model=RunSummaryOut,
    summary="Cancel a run",
    description="Terminal: a cancelled run never advances again. Idempotent.",
)
async def cancel_run(
    run_id: str,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> RunSummaryOut:
    _require_owned_run(server, user, run_id)
    return _run_out(_service(server).cancel(run_id, user=user))


def _detail(server: Any, run: Any) -> RunDetailOut:
    """Run row + the reads a caller needs to render it (no business logic)."""
    service = _service(server)
    runs = server.services.team_run_repo
    summary = _run_out(run)
    return RunDetailOut(
        **summary.model_dump(),
        phases=[_phase_out(row) for row in runs.list_phases(run.run_id)],
        members=[_member_out(row) for row in runs.list_members(run.run_id)],
        allowed_phases=list(service.allowed_phases(run.run_id)),
        pending_decision=runs.get_pending_decision(run.run_id),
    )


__all__ = ["router"]
