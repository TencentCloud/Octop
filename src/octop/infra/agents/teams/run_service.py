"""TeamRunService — run lifecycle, gate orchestration and the decision gate (plan §T-13).

One run is one project (``projects`` keeps the generic fields, ``team_runs`` is its
1:1 extension row) plus one room thread, a roster, a tier-trimmed phase list and a
task board carried by ``project_tasks``.

What this module owns
---------------------
* **Lifecycle** — :meth:`TeamRunService.create` / :meth:`advance` / :meth:`cancel` /
  :meth:`resume`, and the workspace run directory ``<run_root>/<runId>/``.
* **Gate orchestration** — every gate is a *call* into :mod:`octop.infra.agents.teams.pipeline`
  or :mod:`octop.infra.agents.teams.artifacts`. The rules live there; this file only
  supplies the run snapshot they read and maps their refusals to the plan's codes.
* **Attempts** — ``claim`` / ``report`` go through the ``project_tasks`` repo's
  compare-and-set methods (T-09), so a racing claim is decided by one ``UPDATE``.

What this module deliberately does **not** own
---------------------------------------------
* **The task state machine.** ``status`` is written through
  :class:`octop.infra.projects.service.ProjectService` (``transition_task``), whose
  ``_TASK_TRANSITIONS`` is the single authority. ``project_tasks.report()`` never
  touches ``status``; neither does this file.
* **The attempt/claim columns.** ``attempt`` / ``attempt_id`` / ``claimed_by`` /
  ``claimed_at`` have exactly one writer, ``ProjectTaskRepo.claim``. Nothing here
  writes them through ``update()``, which is what keeps a late writer from
  bypassing the CAS.
* **One-shot execution.** ``mode='one-shot'`` dispatches into the host's ``task``
  subagent channel (PLAN 必答 C): this service records the dispatch and returns the
  channel, it does not run the subgraph — the host does, inside the room turn.

Gate map (PLAN §门禁落点④): G2/G3/G4/G16 → :meth:`advance` (via ``advance_gate``);
G5 → :meth:`assert_startable`; G7 → :meth:`create_repair` / :meth:`create_quality_task`;
G8 → :meth:`report`; G9/G10 → :meth:`create`; G11 → :meth:`complete`;
G12/G13 → :meth:`verdict`; G14 → :meth:`write_artifact`; G15 → :meth:`decide`.

Honest boundary: ``write_artifact`` enforces ownership and the revision CAS on the
**service** channel (the plan's ``PUT …/artifacts/{name}``); the ``write``/``edit``
tool channel is a different, deliberately separate gate (``artifacts.py`` module
docstring). ``bash`` redirection is outside both — unchanged and intended.
"""

from __future__ import annotations

import hashlib
import logging
import os
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from fnmatch import fnmatch
from pathlib import Path, PurePosixPath
from sqlite3 import IntegrityError as SqliteIntegrityError
from typing import TYPE_CHECKING, Any, Protocol

from psycopg import IntegrityError as PsycopgIntegrityError

from octop.infra.agents.teams.artifacts import (
    normalize_owner_role,
    owner_violation,
    owners_of,
)
from octop.infra.agents.teams.learnings import (
    collect_deliver_candidates,
    distill_and_append,
)
from octop.infra.agents.teams.pipeline import (
    DEFAULT_MAX_REVIEW_ROUNDS,
    ROLLBACK_TRANSITIONS,
    TASK_DONE,
    advance_gate,
    allowed_next_phases,
    assert_capacity,
    check_run,
    decision_gate,
    normalize_tier,
    phase_sequence,
    validate_task_graph,
)
from octop.infra.agents.teams.service import TeamService
from octop.infra.db.repos._base import UNSET
from octop.infra.db.repos.project_tasks import ProjectTaskRow, actor_ref
from octop.infra.db.repos.team_runs import RUN_MODES, TeamRunRow
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.gateway.threads import ThreadRegistry
from octop.infra.utils.ulid import new_short_id

if TYPE_CHECKING:
    from octop.infra.agents.manager import AgentManager
    from octop.infra.db.services import SharedServices
    from octop.infra.gateway.gateway import Gateway
    from octop.infra.projects.service import ProjectActor

logger = logging.getLogger(__name__)

#: ``run_root`` value meaning "the host's workspace, workspace-relative ``team/``".
RUN_ROOT_HOST_WORKSPACE = "host_workspace"
#: ``run_root`` prefix for an explicitly chosen absolute backend root.
RUN_ROOT_EXPLICIT_PREFIX = "explicit:"
#: Workspace-relative root a default run directory lives under (PLAN §run 目录结构).
RUN_DIR_PREFIX = "team"
#: ``chat_type`` of a run's room session — run-scoped, never ``dm`` (SPEC B30 ①).
ROOM_CHAT_TYPE = "team-run"

#: The deliver phase — the single phase carrying the learnings hook (T-85B).
DELIVER_PHASE = "deliver"

#: Goal limits (PLAN 边界 Case「空输入 / 非法输入」): refuse, never truncate.
GOAL_MAX_LENGTH = 4000

#: Timeline vocabulary owned by this module (``<subject>.<verb>``, like the project
#: actions next to it). Every state write appends one of these.
TIMELINE_RUN_CREATED = "run.created"
TIMELINE_RUN_PHASE_ADVANCED = "run.phase_advanced"
TIMELINE_RUN_STATUS_CHANGED = "run.status_changed"
TIMELINE_RUN_MEMBER_SKIPPED = "run.member_skipped"
TIMELINE_RUN_TASK_CREATED = "run.task_created"
TIMELINE_RUN_TASK_CLAIMED = "run.task_claimed"
TIMELINE_RUN_TASK_REPORTED = "run.task_reported"
TIMELINE_RUN_TASK_COMPLETED = "run.task_completed"
TIMELINE_RUN_VERDICT = "run.verdict"
TIMELINE_RUN_DECISION_RAISED = "run.decision_raised"
TIMELINE_RUN_DECISION_RESOLVED = "run.decision_resolved"
TIMELINE_RUN_ARTIFACT_WRITTEN = "run.artifact_written"
TIMELINE_RUN_ARCHIVE_FAILED = "run.archive_failed"
TIMELINE_RUN_DISPATCHED = "run.dispatched"

#: Phases that need the user before the run may continue (status mirrors that).
AWAITING_STATUS_BY_PHASE: Mapping[str, str] = {"方案确认": "awaiting_confirmation"}

DispatchChannel = str  # "ask_agent" (persist) | "task" (one-shot)


def run_id_for(now: float | None = None) -> str:
    """The run id / directory name: ``<YYYY-MM-DD-HHMMSS>`` (SPEC R22).

    Second precision on purpose: the id *is* the directory name, and two runs in
    the same second are the plan's duplicate-``runId`` conflict
    (``TEAM_RUN_CONFLICT``), not a case to paper over with a suffix.
    """
    return time.strftime("%Y-%m-%d-%H%M%S", time.localtime(now))


def run_directory(run: TeamRunRow) -> str:
    """Workspace-relative (or absolute) run directory for *run*.

    ``host_workspace`` ⇒ ``team/<runId>``; ``explicit:<abs>`` ⇒ ``<abs>/<runId>``.
    Kept in one place: the API, the middleware and the export all resolve it here.

    The explicit root is **user input**, so it may arrive with either separator style
    (``C:\\x\\team\\`` and ``/srv/runs/`` are both legal). Normalising through
    ``PurePosixPath`` drops trailing separators of *both* kinds and joins in one style;
    hand-written ``rstrip("/")`` only handled the forward slash and spliced ``"/"`` onto
    a trailing ``"\\"`` (T-52: ``C:\\x\\team\\`` produced ``C:\\x\\team\\/<runId>``).
    The result is serialised with ``/``; callers hand it to ``Path``/``BackendWorkspace``
    when they need a native path.
    """
    root = str(run.run_root or RUN_ROOT_HOST_WORKSPACE)
    if root.startswith(RUN_ROOT_EXPLICIT_PREFIX):
        raw = root[len(RUN_ROOT_EXPLICIT_PREFIX) :]
        base = PurePosixPath(raw.replace("\\", "/")).as_posix()
        if base == ".":  # empty root: the run id alone, exactly as before
            return run.run_id
        return f"{base.rstrip('/')}/{run.run_id}"
    return f"{RUN_DIR_PREFIX}/{run.run_id}"


class KbArchiverFactory(Protocol):
    """``(kb_id, artifact_id, *, actor_user_id) -> archiver`` (T-71).

    The actor is part of the contract, not an afterthought: the KB side authorises the
    write by actor, so a factory that cannot be told *who* is archiving cannot be used
    correctly.
    """

    def __call__(self, kb_id: str, artifact_id: str, *, actor_user_id: int) -> Any: ...


def run_root_for(
    raw_path: str,
    *,
    workspace_dir: str,
    run_root_of: Callable[[str], str | None],
) -> str | None:
    """The root ``run_scoped_target`` must be given for *raw_path* — or ``None``.

    This exists because the same root was previously derived twice (the tool-channel
    wiring used the workspace directory, while every test built its own conforming
    root) and both sides stayed green: `run_scoped_target` wants the root that has
    ``<runId>/<file>`` directly under it, i.e. ``team`` for a host run — not the
    workspace itself. Resolving it here makes the wiring and the tests share one
    function, so "the root production uses" and "the root a test asserts" cannot drift.

    Two independent sources, neither self-certifying:

    * **the shape rule is `run_directory`'s** — a candidate run id is the segment right
      above the file name, under either ``<workspace>/<RUN_DIR_PREFIX>`` or the run's
      declared ``explicit:`` root. Deeper nesting therefore resolves to ``None``,
      which is exactly ``run_scoped_target``'s "exactly two parts" rule, not a second
      set of rules;
    * **the run's identity is the database's** — the candidate id is confirmed through
      the injected ``run_root_of(run_id)``, so a path that merely *looks* like a run
      directory is not accepted on its own.

    ``run_root`` is accepted in exactly two shapes: ``host_workspace`` (empty/``None``
    meaning the default) and ``explicit:<abs>`` where the tail is absolute, already
    normalised and free of ``..``. **Any other value returns ``None``** — it is *not*
    treated as the host default, because T-61's gate must not become a legal channel
    to whatever path a caller wrote into that column.

    Relative paths are resolved **lexically** (``workspace_dir / raw_path``, no IO, no
    ``stat``) — the same discipline as ``artifacts.run_scoped_target``.
    """
    text = str(raw_path or "").strip()
    if not text:
        return None
    path = Path(text)
    if not path.is_absolute():
        path = Path(workspace_dir) / text
    path = Path(os.path.normpath(str(path)))
    run_id = path.parent.name
    if not run_id:
        return None
    parent = str(path.parent.parent)
    declared_raw = run_root_of(run_id)
    if declared_raw is None:
        # No such run: the identity is **not** confirmed, and the shape alone never
        # certifies anything -- so there is no root to hand back.
        return None
    declared = str(declared_raw).strip()

    if declared in {"", RUN_ROOT_HOST_WORKSPACE}:
        host_root = str(Path(os.path.normpath(str(Path(workspace_dir) / RUN_DIR_PREFIX))))
        return host_root if parent == host_root else None

    if not declared.startswith(RUN_ROOT_EXPLICIT_PREFIX):
        return None  # unknown shape: never fall back to the host default
    tail = declared[len(RUN_ROOT_EXPLICIT_PREFIX) :].strip().rstrip("/")
    if not tail or not Path(tail).is_absolute() or os.path.normpath(tail) != tail:
        return None  # relative, unnormalised or ".."-bearing: refuse, do not guess
    return tail if parent == tail else None


def revision_of(content: str) -> str:
    """The revision token of an artifact body — its sha256, first 16 hex digits.

    Content-addressed on purpose: the plan's ``PUT`` is a compare-and-set against
    what the writer last read, and a content hash makes "same revision" mean "same
    bytes" without a second counter column that could drift from the file.
    """
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def _in_scope(path: str) -> str:
    return str(path).strip().replace("\\", "/").lstrip("./")


def path_in_scope(path: str, scopes: Sequence[str]) -> bool:
    """Does *path* fall inside any of the task's ``in_scope`` entries (G11)?

    An entry is a file or directory prefix (``src/octop/**``, ``tests/unit/db``);
    a bare directory also covers everything under it. Matching is
    ``fnmatch``-based so globs work on both POSIX and Windows separators.
    """
    target = _in_scope(path)
    if not target:
        return True
    for raw in scopes:
        scope = _in_scope(raw)
        if not scope:
            continue
        if fnmatch(target, scope) or target == scope:
            return True
        directory = scope.rstrip("/*")
        if directory and (target == directory or target.startswith(f"{directory}/")):
            return True
    return False


class _RunActor:
    """Minimal :class:`~octop.infra.projects.service.ProjectActor` for internal writes.

    Service-side transitions (a verdict closing a task, a cancel) are authorized as
    the **run's creator** — who owns the project this run created — so they go
    through ``ProjectService`` with a real actor instead of talking to the repo
    directly. No admin bypass, no second permission model.
    """

    def __init__(self, user_id: int) -> None:
        self.id = user_id
        self.permissions: list[str] = ["projects", "knowledge_bases"]

    @property
    def is_admin(self) -> bool:
        return False


@dataclass(frozen=True)
class DispatchOutcome:
    """What one dispatch did — the two PLAN 必答 C channels, told apart by ``channel``."""

    task_id: str
    channel: DispatchChannel
    thread_id: str | None


class TeamRunService:
    """Run lifecycle + gate orchestration over ``team_runs`` and ``project_tasks``.

    Constructed by ``SharedServices.team_run_service()`` with the repos it needs;
    the runtime handles (agent registry, gateway, workspace accessor) are optional
    and injected by the server for dispatch and artifact I/O, so the gate paths stay
    unit-testable without a booted runtime.
    """

    def __init__(
        self,
        *,
        services: SharedServices,
        agent_manager: AgentManager | None = None,
        gateway: Gateway | None = None,
        workspace_for: Callable[[str], Any] | None = None,
        team_service: TeamService | None = None,
        kb_archiver_factory: KbArchiverFactory | None = None,
        host_workspace_for: Callable[[str], Path | None] | None = None,
        learnings_distill: Callable[[str], str] | None = None,
    ) -> None:
        self._services = services
        self._runs = services.team_run_repo
        self._tasks = services.project_task_repo
        self._findings = services.task_finding_repo
        self._timeline = services.timeline_repo
        self._projects = services.project_repo
        self._agent_manager = agent_manager
        self._gateway = gateway
        self._workspace_for = workspace_for
        self._team_service = team_service
        # (kb_id, artifact_id) -> a KnowledgeArchiver-shaped object. Injected, because
        # the archiver lives with the memory wiring and teams/ must not reach into the
        # knowledge domain (AGENTS.md section 5); T-18's ProjectKbArchiver satisfies it.
        self._kb_archiver_factory = kb_archiver_factory
        # The deliver hook (T-85B) writes through ``learnings.distill_and_append``, which
        # takes a **host** path. This service never guesses one: without the accessor
        # there is no write face, so the hook skips instead of inventing a location.
        self._host_workspace_for = host_workspace_for
        # 乙 (deliver-time LLM distillation) rides in as a callback only — the seat for
        # T-96. Default None means 丙-only, exactly as PLAN 2.4(b) registers it; this
        # module never calls a model itself.
        self._learnings_distill = learnings_distill

    # ── wiring (T-17 binds the runtime after boot) ───────────────────────────

    def bind_runtime(
        self,
        *,
        agent_manager: AgentManager | None = None,
        gateway: Gateway | None = None,
        workspace_for: Callable[[str], Any] | None = None,
        kb_archiver_factory: KbArchiverFactory | None = None,
        host_workspace_for: Callable[[str], Path | None] | None = None,
        learnings_distill: Callable[[str], str] | None = None,
    ) -> None:
        """Attach the runtime handles dispatch and artifact I/O need.

        Idempotent: the server calls it once at start; tests call it with fakes.
        Nothing here reaches for a global — an unbound service refuses dispatch
        rather than silently skipping the turn.
        """
        if agent_manager is not None:
            self._agent_manager = agent_manager
        if gateway is not None:
            self._gateway = gateway
        if workspace_for is not None:
            self._workspace_for = workspace_for
        if kb_archiver_factory is not None:
            self._kb_archiver_factory = kb_archiver_factory
        if host_workspace_for is not None:
            self._host_workspace_for = host_workspace_for
        if learnings_distill is not None:
            self._learnings_distill = learnings_distill

    def _workspace_accessor(self) -> Callable[[str], Any] | None:
        """Resolve the accessor for a team agent's workspace.

        An injected ``workspace_for`` wins; without one the harness accessor is used
        when an agent registry is bound. The **manifest** (the roster's sole
        authority) lives in that workspace, so an unbound runtime cannot see any
        members — which is why this falls back rather than silently answering ``()``.
        """
        if self._workspace_for is not None:
            return self._workspace_for
        # Bind to a local: attribute narrowing does not cross into a closure (the
        # attribute could be re-bound later), and the closure then holds a stable
        # reference instead of re-reading a mutable attribute on every call.
        manager = self._agent_manager
        if manager is None:
            return None
        from octop.infra.gateway.process.agent_resolve import harness_workspace_for_agent

        return lambda agent_id: harness_workspace_for_agent(manager, agent_id)

    def _team(self) -> TeamService:
        if self._team_service is None:
            self._team_service = TeamService(
                self._services.repos, workspace_for=self._workspace_accessor()
            )
        return self._team_service

    def _project_service(self) -> Any:
        from octop.infra.projects.service import ProjectService

        return ProjectService(
            self._services, agent_manager=self._agent_manager, gateway=self._gateway
        )

    def _workspace(self, run: TeamRunRow) -> Any | None:
        accessor = self._workspace_accessor()
        if accessor is None:
            return None
        return accessor(run.team_agent_id)

    # ── reads ────────────────────────────────────────────────────────────────

    def require_run(self, run_id: str) -> TeamRunRow:
        row = self._runs.get(run_id)
        if row is None:
            raise OctopError(ErrorCode.TEAM_RUN_NOT_FOUND, f"run {run_id!r} not found")
        return row

    def get_run(self, run_id: str) -> TeamRunRow | None:
        return self._runs.get(run_id)

    def require_task(self, run_id: str, task_id: str) -> ProjectTaskRow:
        """The task, checked to belong to the run's project.

        A task from another project is a **cross-run reference** (PLAN B2), not a
        404: the caller learns that the id exists but is not part of this run.
        """
        run = self.require_run(run_id)
        task = self._tasks.get(task_id)
        if task is None:
            raise OctopError(ErrorCode.PROJECT_TASK_NOT_FOUND, f"task {task_id!r} not found")
        if task.project_id != run.project_id:
            raise OctopError(
                ErrorCode.TEAM_CROSS_RUN_REFERENCE,
                f"task {task_id!r} belongs to run project {task.project_id!r}, not {run_id!r}",
                details={"run_id": run_id, "project_id": task.project_id},
            )
        return task

    def list_tasks(self, run_id: str) -> list[ProjectTaskRow]:
        run = self.require_run(run_id)
        return self._tasks.list_by_project(run.project_id)

    def check(self, run_id: str) -> Any:
        """The read-side report (``/team check``): reports, never blocks."""
        return check_run(self.snapshot(self.require_run(run_id)))

    def present_artifacts(self, run: TeamRunRow) -> tuple[str, ...]:
        """Names present in the run directory, or ``()`` when it cannot be read.

        **Basenames on purpose**: the gates compare against the artifact table's names
        (``SPEC.md``), while the workspace hands back **workspace-relative** paths.

        T-72: the harness returns ``{"path": <workspace-relative>, "is_dir": bool}``
        (``octop_harness.backends.workspace · list_dir``: "Always workspace-relative
        (``skills/demo``), never basename-only"), and this method used to read
        ``entry.name`` — which a dict does not have, so ``getattr`` fell through to
        ``str(entry)`` and produced no usable name at all. The gate then reported a
        written ``SPEC.md`` as missing and the run could never reach ``implement``.
        The shape handling below is the same one ``api/routers/chat/serialize.py`` uses
        (mapping first, attribute fallback), so there is one convention, not two.
        """
        workspace = self._workspace(run)
        if workspace is None:
            return ()
        entries = workspace.list_dir(run_directory(run)) or []
        names: list[str] = []
        for entry in entries:
            if isinstance(entry, Mapping):
                raw_path = entry.get("path")
                is_dir = bool(entry.get("is_dir"))
            else:
                raw_path = getattr(entry, "name", entry)
                is_dir = str(raw_path).endswith("/")
            path = str(raw_path or "").replace("\\", "/").rstrip("/")
            if not path or is_dir:
                continue
            names.append(path.rsplit("/", 1)[-1])
        return tuple(names)

    def snapshot(self, run: TeamRunRow) -> dict[str, Any]:
        """The mapping the pure gates read (``pipeline.RUN_SNAPSHOT_KEYS``).

        ``spec_text`` and ``present_artifacts`` come from the run directory; when no
        workspace is bound they are ``None`` / empty, which makes the spec-boundary
        gate **fail closed** (``MISSING`` ⇒ refuse) exactly as the plan requires —
        absence of input is not evidence of a filled boundary table.
        """
        workspace = self._workspace(run)
        spec_text: str | None = None
        if workspace is not None:
            spec_text = workspace.read_text(f"{run_directory(run)}/SPEC.md")
        return {
            "phase": run.phase,
            "status": run.status,
            "tier": run.tier,
            "max_review_rounds": run.max_review_rounds,
            "pending_decision": self._runs.get_pending_decision(run.run_id),
            "spec_text": spec_text,
            "present_artifacts": self.present_artifacts(run),
            "rollback_count": self._rollback_count(run),
            "finding_rounds": self.finding_rounds(run),
            "escalated": self._escalated(run),
            "tasks": [self._task_view(task) for task in self.list_tasks(run.run_id)],
        }

    def finding_rounds(self, run: TeamRunRow) -> list[dict[str, Any]]:
        """Round-by-round finding titles, the input G16 reads.

        One entry per round: the round's ``verdict`` is the verdict its review task
        recorded, and ``findings`` are the titles raised in that round. Built from
        the rows (``project_task_findings``), never hand-maintained.
        """
        verdict_by_round: dict[int, str] = {}
        rounds: dict[int, list[str]] = {}
        for finding in self._findings.list_by_run(run.run_id):
            rounds.setdefault(finding.round, []).append(finding.title)
        for task in self.list_tasks(run.run_id):
            if task.verdict is not None:
                verdict_by_round.setdefault(task.round, task.verdict)
        return [
            {
                "round": number,
                "verdict": verdict_by_round.get(number, ""),
                "findings": [{"title": title} for title in titles],
            }
            for number, titles in sorted(rounds.items())
        ]

    def _rollback_count(self, run: TeamRunRow) -> int:
        events = self._timeline.list_by_project(run.project_id, limit=None)
        return sum(
            1
            for event in events
            if event.action == TIMELINE_RUN_PHASE_ADVANCED and bool(event.payload.get("rollback"))
        )

    def _escalated(self, run: TeamRunRow) -> bool:
        pending = self._runs.get_pending_decision(run.run_id)
        if isinstance(pending, Mapping) and str(pending.get("kind") or "") == "escalate":
            return True
        return any(
            event.action == TIMELINE_RUN_DECISION_RAISED
            and str(event.payload.get("kind") or "") == "escalate"
            for event in self._timeline.list_by_project(run.project_id, limit=None)
        )

    def _task_view(self, task: ProjectTaskRow) -> dict[str, Any]:
        """One task as the gates see it (keys the pure functions read).

        ``role`` is the role the task is meant for (``assignee_id`` on a ``team``
        assignment) rather than whoever holds the attempt — the read-side
        ``quality_owner_invalid`` warning (V4) is about the intended owner.
        ``verifiedAt`` stays ``None``: nothing in the schema records that a task's
        ``verify`` commands actually ran, so the V4 warning reports that honestly
        instead of the snapshot inventing a timestamp.
        """
        return {
            "id": task.id,
            "dependsOn": list(task.deps),
            "status": task.status,
            "kind": task.kind,
            "verify": list(task.verify),
            "verifiedAt": None,
            "role": (task.assignee_id if task.assignee_type == "team" else "")
            or (task.claimed_by or ""),
            "round": task.round,
            "attempt": task.attempt,
            "attempt_id": task.attempt_id,
            "inScope": list(task.in_scope),
            "phase": task.phase,
        }

    # ── create (G9 / G10 / AM-1 ③) ───────────────────────────────────────────

    def create(
        self,
        *,
        team_agent_id: str,
        user: ProjectActor,
        goal: str,
        mode: str = "one-shot",
        deliverable: str = "code+artifacts",
        tier: object = None,
        run_root: str | None = None,
        roles: Sequence[str] | None = None,
        host_agent_id: str | None = None,
        max_review_rounds: int = DEFAULT_MAX_REVIEW_ROUNDS,
    ) -> TeamRunRow:
        """Create a run: project row, run row, room thread, roster, tier phases.

        Order is deliberate — the goal is validated first, so a refused run leaves
        **nothing** behind (no project, no directory).

        * **G10** — the tier is normalised by ``pipeline.normalize_tier``: an
          unrecognised value is refused, never silently defaulted.
        * **G9** — ``roles`` is an *explicit* roster request, so an over-cap list is a
          ``TEAM_RUN_MEMBER_LIMIT``. The manifest roster is different: it is trimmed
          to the tier's ``roleCap`` and the cut roles are recorded in the first
          phase's ``gate_detail.skipped_roles`` (visible, never silently dropped).
        * The room thread's session key is **run-scoped** (``…:<runId>:team-run``),
          never a user DM key — SPEC B30 ① applies to runs as much as to dispatch.
        """
        text = str(goal or "").strip()
        if not text.strip("\u3000 \t\r\n"):
            raise OctopError(ErrorCode.TEAM_RUN_GOAL_EMPTY, "run goal is empty")
        if len(text) > GOAL_MAX_LENGTH:
            raise OctopError(
                ErrorCode.TEAM_RUN_GOAL_TOO_LONG,
                f"run goal is longer than {GOAL_MAX_LENGTH} characters",
                details={"length": len(text), "limit": GOAL_MAX_LENGTH},
            )
        if mode not in RUN_MODES:
            # No code exists for "unknown mode" and the plan forbids inventing one;
            # the HTTP layer's enum is the user-facing gate (PLAN 边界码 list).
            raise ValueError(f"unknown run mode: {mode!r}")
        resolved_tier = normalize_tier(tier)

        # AM-1 ③: the roster comes from the manifest and is trimmed by the tier.
        # Cutting is the default behaviour; only an explicit over-cap `roles?` is an
        # error (G9). Rules live in pipeline.trim_roster, reached through TeamService.
        team = self._team()
        manifest_roster = team.roster(team_agent_id)
        trim = team.trimmed_roster(team_agent_id, resolved_tier, host_agent_id=host_agent_id)
        if roles is not None:
            assert_capacity({"tier": resolved_tier}, member_count=len(roles))

        project = self._project_service().create_project(
            owner_user=user, name=text[:80] or "team run", goal=text
        )
        run_id = run_id_for()
        if self._runs.get(run_id) is not None:
            raise OctopError(
                ErrorCode.TEAM_RUN_CONFLICT,
                f"run {run_id!r} already exists",
                details={"run_id": run_id},
            )
        run = self._runs.create(
            run_id=run_id,
            team_agent_id=team_agent_id,
            project_id=project.id,
            goal=text,
            created_by=user.id,
            mode=mode,
            deliverable=deliverable,
            tier=resolved_tier,
            run_root=run_root or RUN_ROOT_HOST_WORKSPACE,
            max_review_rounds=max_review_rounds,
        )
        thread_id = self._open_room(run, user=user)
        if thread_id is not None:
            self._runs.set_room_thread(run_id, thread_id)
            run = self.require_run(run_id)

        lead_agent_id = _kept_lead(
            trim.kept,
            host_agent_id=host_agent_id,
            lead_agent_id=manifest_roster.get("lead_agent_id"),
        )
        # ── Roster admission (T-73, A layer) ────────────────────────────────────
        # Decided **before** the ``or ""`` folding below, and the order matters: once
        # folded, "no role configured" and "empty role" are indistinguishable, and that
        # lost distinction is what let a second empty role reach the table and trip
        # ``UNIQUE(run_id, role)`` as a raw IntegrityError.
        # ★ Refuse only "missing role" and "duplicate role". Do **not** add a "role is in
        # the fixed role table" check here: ``lead`` is a legitimate *roster* role while
        # ``normalize_owner_role("lead") == ""`` -- that helper's surface is
        # artifact-write ownership, not the roster, and borrowing it rejected every run
        # with a lead member (measured: 91 tests red).
        seen_roles: set[str] = set()
        for member in trim.kept:
            raw_role = member.get("role")
            role_text = str(raw_role).strip() if raw_role is not None else ""
            if not role_text:
                raise OctopError(
                    ErrorCode.TEAM_ROLE_UNKNOWN,
                    f"member {member.get('agent_id')!r} has no configured role",
                    details={"run_id": run_id, "role": ""},
                )
            if role_text in seen_roles:
                raise OctopError(
                    ErrorCode.PROJECT_MEMBER_INVALID,
                    f"role {role_text!r} appears twice in this run",
                    details={"run_id": run_id, "role": role_text},
                )
            seen_roles.add(role_text)

        for member in trim.kept:
            try:
                self._runs.add_member(
                    run_id,
                    role=str(member.get("role") or ""),
                    agent_id=str(member.get("agent_id") or ""),
                    is_lead=bool(
                        lead_agent_id and str(member.get("agent_id") or "") == lead_agent_id
                    ),
                )
            except (SqliteIntegrityError, PsycopgIntegrityError) as err:
                # ★ Semantic mismatch, and why this code is still right: the table is
                # UNIQUE(run_id, role), so a duplicate cannot be described exactly by any
                # existing code. The closest wording that stays TRUE is
                # PROJECT_MEMBER_INVALID ("That membership change is not allowed") -- it
                # asserts the outcome, not the cause. TEAM_RUN_CONFLICT was rejected: its
                # wording claims a concurrent request, which would be false here.
                # ★ Delete condition: replace it once a code with exact wording exists
                # (or a new one is approved).
                raise OctopError(
                    ErrorCode.PROJECT_MEMBER_INVALID,
                    f"duplicate role for run {run_id}: {member.get('role')!r}",
                    details={"run_id": run_id, "role": str(member.get("role") or "")},
                ) from err

        sequence = phase_sequence(resolved_tier)
        now = int(time.time())
        skipped = list(trim.skipped_roles)
        for seq, phase in enumerate(sequence):
            self._runs.upsert_phase(
                run_id,
                phase,
                seq=seq,
                status="active" if seq == 0 else "pending",
                gate_detail={"skipped_roles": skipped} if seq == 0 else None,
                entered_at=now if seq == 0 else None,
            )
        self._record(
            run,
            TIMELINE_RUN_CREATED,
            {
                "goal": text,
                "mode": mode,
                "tier": resolved_tier,
                "phases": list(sequence),
                "room_thread_id": thread_id,
            },
            actor=actor_ref("user", user.id),
        )
        if skipped:
            self._record(
                run,
                TIMELINE_RUN_MEMBER_SKIPPED,
                {
                    "skipped_roles": skipped,
                    "kept_roles": [str(m.get("role") or "") for m in trim.kept],
                },
                actor=actor_ref("user", user.id),
            )
        return run

    def _open_room(self, run: TeamRunRow, *, user: ProjectActor) -> str | None:
        """Open the room thread for the run, or ``None`` without a booted gateway."""
        if self._gateway is None:
            return None
        session_key = ThreadRegistry.make_key(
            agent_id=run.team_agent_id,
            channel_type=ThreadRegistry.CHANNEL_DASHBOARD,
            channel_subject_id=run.run_id,
            channel_chat_type=ROOM_CHAT_TYPE,
        )
        return self._gateway.thread_registry.create_thread(
            agent_id=run.team_agent_id,
            user_id=user.id,
            channel_type=ThreadRegistry.CHANNEL_DASHBOARD,
            session_key=session_key,
            title=f"专家团 {run.run_id}",
        )

    # ── advance (G2 / G3 / G4 / G16) ─────────────────────────────────────────

    def advance(
        self, run_id: str, *, to_phase: str, user: ProjectActor | None = None
    ) -> TeamRunRow:
        """Move the run to *to_phase* through the pipeline gates (G2/G3/G4/G16).

        Every refusal is a plain call into ``pipeline`` — no rule is re-implemented
        here. What this method adds is the **wiring**: the pure functions have no
        callers of their own, so this is where they become production behaviour.

        * :func:`pipeline.decision_gate` runs for **every** transition, not only for
          ``implement`` (where :func:`pipeline.advance_gate` consults it too). The
          confirmation gate is a hard gate (SPEC A4 / B17), and G16's escalation has
          to stop the run wherever it stands instead of only at the implement edge.
        * on ``TEAM_FINDING_REOPENED`` the plan escalates **to the user** rather than
          dispatching another repair round, so the escalation decision is raised
          *before* the refusal propagates (G16).
        """
        run = self.require_run(run_id)
        snapshot = self.snapshot(run)
        try:
            decision_gate(snapshot)
            advance_gate(snapshot, to_phase)
        except OctopError as err:
            if err.code is ErrorCode.TEAM_FINDING_REOPENED:
                details = dict(err.details or {})
                decision = details.get("decision") or {
                    "kind": "escalate",
                    "reason": "finding_reopened",
                }
                self.raise_decision(
                    run_id,
                    kind=str(decision.get("kind") or "escalate"),
                    reason=str(decision.get("reason") or "finding_reopened"),
                    options=["continue", "stop"],
                    context={"finding": details.get("title"), "rounds": details.get("rounds")},
                )
            raise

        previous = run.phase
        rollback = to_phase in ROLLBACK_TRANSITIONS.get(previous, ())
        updated = self._set_phase(run, to_phase, rollback=rollback, actor=self._actor(user, run))
        if to_phase == DELIVER_PHASE and previous != to_phase:
            # T-85B: the **only** trigger. A phase that truly changed is the run-level
            # marker S-2 counts ("one distillation per run" == one distill_and_append
            # call); a re-entered deliver never reaches here, so the count stays 0.
            self._distill_deliver_learnings(updated)
        return updated

    def _set_phase(
        self,
        run: TeamRunRow,
        to_phase: str,
        *,
        rollback: bool,
        actor: str,
    ) -> TeamRunRow:
        """Persist a phase move: the target becomes ``active``, forward phases pass.

        Exactly one phase is ``active`` at a time: a forward move marks everything
        before the target ``passed``, and a rollback re-opens the phases after the
        target (their ``passed_at`` history is left intact).
        """
        now = int(time.time())
        sequence = phase_sequence(run.tier)
        target_index = sequence.index(to_phase) if to_phase in sequence else -1
        for seq, phase in enumerate(sequence):
            row = self._runs.get_phase(run.run_id, phase)
            status = "pending" if row is None else row.status
            if phase == to_phase:
                status = "active"
            elif target_index >= 0 and seq < target_index and status in {"pending", "active"}:
                status = "passed"
            elif seq > target_index and status == "active":
                status = "pending"
            if row is not None and status == row.status:
                continue
            self._runs.upsert_phase(
                run.run_id,
                phase,
                seq=seq,
                status=status,
                gate_detail=(row.gate_detail if row is not None else {}),
                entered_at=now
                if phase == to_phase
                else (row.entered_at if row is not None else None),
                passed_at=(
                    now
                    if status == "passed" and (row is None or row.passed_at is None)
                    else (row.passed_at if row is not None else None)
                ),
            )
        self._runs.update_phase(run.run_id, to_phase)
        status = AWAITING_STATUS_BY_PHASE.get(to_phase, "running")
        if status != run.status:
            self._runs.update_status(run.run_id, status)
        updated = self.require_run(run.run_id)
        self._record(
            updated,
            TIMELINE_RUN_PHASE_ADVANCED,
            {"from": run.phase, "to": to_phase, "rollback": rollback},
            actor=actor,
        )
        return updated

    def _distill_deliver_learnings(self, run: TeamRunRow) -> None:
        """Deliver hook (T-85B): hand this run's candidates to the one write path.

        ``advance`` calls this **only** when ``deliver`` is entered and the phase truly
        changed, so the count of :func:`learnings.distill_and_append` calls is exactly
        one per run (S-2's counting entity). The candidates come from
        :func:`learnings.collect_deliver_candidates`, whose admission layer (S-1/S-2/S-3)
        runs *before* the write; its dropped reasons are merged into
        ``DistillResult.degraded`` so a conflict still reaches the human-review entry.

        A host workspace that cannot be named means no host write face — the hook skips
        rather than guessing a path (nothing to write to, nothing written), and says so
        on the log: a silent skip is exactly what made this hook look wired while
        production wrote nothing.
        """
        home = self._learnings_home(run)
        if home is None:
            logger.warning(
                "learnings deliver distillation skipped for run %s (team agent %s): "
                "no host workspace",
                run.run_id,
                run.team_agent_id,
            )
            return
        candidates, reasons = collect_deliver_candidates(
            host_workspace=home,
            project_id=run.project_id,
            run_id=run.run_id,
            run_dir=home / run_directory(run),
            distill=self._learnings_distill,
        )
        result = distill_and_append(
            host_workspace=home,
            project_id=run.project_id,
            run_id=run.run_id,
            candidates=candidates,
        )
        degraded = (*reasons, *result.degraded)
        if degraded:
            logger.warning("learnings deliver degraded: %s", list(degraded))

    def _learnings_home(self, run: TeamRunRow) -> Path | None:
        """The run's host workspace (the team host agent's), or ``None`` when unreachable.

        An injected ``host_workspace_for`` wins; without one the **host** path comes from
        a bound agent registry, mirroring :meth:`_workspace_accessor`. The accessor is
        :meth:`AgentManager.resolve_workspace_dir` — the existing "on-disk workspace for
        Octop host FS ops" entry point — because ``distill_and_append`` writes through
        plain host file I/O and therefore needs a host path, not a ``BackendWorkspace``.
        ``persist_if_missing=False`` keeps the lookup read-only: entering ``deliver`` must
        not write config as a side effect.

        A remote / docker backend may have no host path at all (the workspace lives in
        the sandbox or a bucket). That is registered honestly as a degraded skip instead
        of being papered over with a guessed ``~/.octop/agents/<id>`` string.
        """
        agent_id = run.team_agent_id
        if self._host_workspace_for is not None:
            home = self._host_workspace_for(agent_id)
        elif self._agent_manager is None:
            # No runtime at all: unchanged pre-T-85B semantics — no seat, no write face.
            return None
        else:
            try:
                home = self._agent_manager.resolve_workspace_dir(agent_id, persist_if_missing=False)
            except Exception:
                logger.warning(
                    "learnings deliver: host workspace lookup failed for team agent %s",
                    agent_id,
                    exc_info=True,
                )
                return None
        return None if home is None else Path(home)

    def allowed_phases(self, run_id: str) -> tuple[str, ...]:
        """What ``advance`` would accept right now (``details.allowed`` on refusal)."""
        return allowed_next_phases(self.snapshot(self.require_run(run_id)))

    # ── tasks: startable / claim / report (G5 / G8) ──────────────────────────

    def assert_startable(self, run_id: str, task_id: str) -> ProjectTaskRow:
        """G5: every dependency must be ``done``; ``failed``/``cancelled`` never unlock.

        The check reads the board as it is *now*; :meth:`claim` re-checks it inside
        the same compare-and-set the token protects, so a board that moves between
        this call and the write is caught there.
        """
        task = self.require_task(run_id, task_id)
        done = {t.id for t in self.list_tasks(run_id) if t.status == TASK_DONE}
        unmet = tuple(dep for dep in task.deps if dep not in done)
        if unmet:
            raise OctopError(
                ErrorCode.TEAM_TASK_DEPS_UNMET,
                f"task {task_id!r} has unmet dependencies: {list(unmet)}",
                details={"task_id": task_id, "unmet": list(unmet)},
            )
        return task

    def claim(
        self, run_id: str, task_id: str, *, role: str, user: ProjectActor | None = None
    ) -> ProjectTaskRow:
        """Claim a startable task for *role* under a fresh attempt (G5 + B26).

        ``expected_attempt_id`` is the attempt **read before the gate ran** — that
        is what makes the comparison-and-set span the gate window: two callers that
        both saw a startable board cannot both win, the loser's ``UPDATE`` matches
        no row and becomes ``TEAM_TASK_CLAIM_CONFLICT``. Passing a *freshly re-read*
        attempt instead is an explicit transfer, which the plan allows.
        """
        task = self.assert_startable(run_id, task_id)
        claimed = self._tasks.claim(task_id, claimed_by=role, expected_attempt_id=task.attempt_id)
        if claimed is None:
            raise OctopError(
                ErrorCode.TEAM_TASK_CLAIM_CONFLICT,
                f"task {task_id!r} was claimed by someone else",
                details={"task_id": task_id, "role": role},
            )
        run = self.require_run(run_id)
        self._record(
            run,
            TIMELINE_RUN_TASK_CLAIMED,
            {"task_id": task_id, "role": role, "attempt_id": claimed.attempt_id},
            actor=self._actor(user, run),
            task_id=task_id,
        )
        return claimed

    def report(
        self,
        run_id: str,
        task_id: str,
        *,
        attempt_id: str,
        verdict: object = UNSET,
        changed_paths: object = UNSET,
        round: object = UNSET,
        user: ProjectActor | None = None,
    ) -> ProjectTaskRow:
        """Record an attempt's outcome; a stale ``attempt_id`` is refused (G8).

        Deliberately **does not touch ``status``** — the state machine lives in
        ``projects/service.py``; this writes the report columns only (T-09 design
        decision ③).
        """
        self.require_task(run_id, task_id)
        updated = self._tasks.report(
            task_id,
            attempt_id=attempt_id,
            verdict=verdict,
            changed_paths=changed_paths,
            round=round,
        )
        if updated is None:
            raise OctopError(
                ErrorCode.TEAM_ATTEMPT_STALE,
                f"attempt {attempt_id!r} is no longer current for task {task_id!r}",
                details={"task_id": task_id, "attempt_id": attempt_id},
            )
        run = self.require_run(run_id)
        self._record(
            run,
            TIMELINE_RUN_TASK_REPORTED,
            {"task_id": task_id, "attempt_id": attempt_id, "verdict": updated.verdict},
            actor=self._actor(user, run),
            task_id=task_id,
        )
        return updated

    # ── verdict (G12 / G13) ──────────────────────────────────────────────────

    def verdict(
        self,
        run_id: str,
        task_id: str,
        *,
        role: str,
        attempt_id: str,
        verdict: str,
        findings: Sequence[Mapping[str, Any]] = (),
        user: ProjectActor | None = None,
    ) -> ProjectTaskRow:
        """Record a review verdict under the two review gates.

        * **G12** — a ``needs_revision`` / ``reject`` verdict without findings is
          refused: "fix it" with nothing to fix is not a review.
        * **G13** — a ``pass`` on a ``review`` task is refused while the reviewer is
          the role that claimed the most recent implementation attempt in the same
          round: nobody signs off their own work.
        """
        task = self.require_task(run_id, task_id)
        clean = [dict(item) for item in findings]
        if task.kind == "review" and verdict in {"needs_revision", "reject"} and not clean:
            raise OctopError(
                ErrorCode.TEAM_VERDICT_FINDINGS_REQUIRED,
                f"verdict {verdict!r} requires at least one finding",
                details={"task_id": task_id, "verdict": verdict},
            )
        if verdict == "pass" and task.kind == "review":
            reviewer = task.claimed_by or role
            author = self._last_implementer(run_id, task)
            if author is not None and author == reviewer:
                raise OctopError(
                    ErrorCode.TEAM_REVIEW_SELF_AUDIT,
                    f"role {reviewer!r} cannot pass its own work",
                    details={"task_id": task_id, "role": reviewer, "author_role": author},
                )
        run = self.require_run(run_id)
        for item in clean:
            self._findings.insert(
                finding_id=new_short_id(),
                task_id=task_id,
                run_id=run_id,
                round=int(item.get("round") or task.round),
                severity=str(item.get("severity") or "medium"),
                title=str(item.get("title") or ""),
                detail=str(item.get("detail") or ""),
                verdict=verdict,
            )
        updated = self.report(
            run_id,
            task_id,
            attempt_id=attempt_id,
            verdict=verdict,
            user=user,
        )
        self._record(
            run,
            TIMELINE_RUN_VERDICT,
            {"task_id": task_id, "role": role, "verdict": verdict, "findings": len(clean)},
            actor=self._actor(user, run),
            task_id=task_id,
        )
        return updated

    def _last_implementer(self, run_id: str, review_task: ProjectTaskRow) -> str | None:
        """``claimed_by`` of the most recent non-review attempt in the same round."""
        candidates = [
            task
            for task in self.list_tasks(run_id)
            if task.id != review_task.id
            and task.claimed_by
            and task.kind != "review"
            and task.round == review_task.round
        ]
        if not candidates:
            return None
        latest = max(candidates, key=lambda task: (task.claimed_at or 0, task.pk))
        return latest.claimed_by

    # ── start / fail / rework (the PATCH op vocabulary) ─────────────────────

    def start(
        self,
        run_id: str,
        task_id: str,
        *,
        role: str,
        attempt_id: str,
        user: ProjectActor | None = None,
    ) -> ProjectTaskRow:
        """Begin an attempt: the status becomes ``doing`` and ``started_at`` is stamped.

        The attempt token is verified **first** (G8) — a superseded writer must not
        move a task it no longer owns — and only then does the status move, through
        the one state machine. ``started_at`` is what tells ``claimed`` apart from
        ``in_progress`` in the read-side projection (PLAN §状态词表).
        """
        task = self.require_task(run_id, task_id)
        run = self.require_run(run_id)
        actor = user or _RunActor(run.created_by)
        self.report(run_id, task_id, attempt_id=attempt_id, user=user)
        if task.status in {"planning", "todo"}:
            self._project_service().transition_task(
                run.project_id, task_id, user=actor, target="doing"
            )
        stamped = self._tasks.update(task_id, started_at=int(time.time()))
        updated = stamped if stamped is not None else self.require_task(run_id, task_id)
        self._record(
            run,
            TIMELINE_RUN_TASK_REPORTED,
            {"task_id": task_id, "role": role, "started_at": updated.started_at},
            actor=self._actor(user, run),
            task_id=task_id,
        )
        return updated

    def fail(
        self,
        run_id: str,
        task_id: str,
        *,
        role: str,
        attempt_id: str,
        reason: str = "",
        user: ProjectActor | None = None,
    ) -> ProjectTaskRow:
        """Fail an attempt: the task becomes ``blocked`` and the reason is recorded.

        ``blocked`` rather than ``cancelled`` on purpose: dependents stay locked
        (G5 — only ``done`` unlocks) and the work stays visible for a retry.
        """
        task = self.require_task(run_id, task_id)
        run = self.require_run(run_id)
        actor = user or _RunActor(run.created_by)
        self.report(run_id, task_id, attempt_id=attempt_id, verdict="reject", user=user)
        if task.status != "blocked":
            self._project_service().transition_task(
                run.project_id, task_id, user=actor, target="blocked"
            )
        self._record(
            run,
            TIMELINE_RUN_TASK_REPORTED,
            {"task_id": task_id, "role": role, "failed": True, "reason": reason},
            actor=self._actor(user, run),
            task_id=task_id,
        )
        return self.require_task(run_id, task_id)

    def rework(
        self,
        run_id: str,
        task_id: str,
        *,
        role: str,
        attempt_id: str,
        round: int | None = None,
        user: ProjectActor | None = None,
    ) -> ProjectTaskRow:
        """Send reviewed work back for another round (the ``review`` → ``doing`` edge).

        The round advances **explicitly** (omitted ⇒ the next one), which is what
        keeps G7's budget meaningful: the loop counter moves only when a caller asks
        for another round, never as a side effect of creating a task.
        """
        task = self.require_task(run_id, task_id)
        run = self.require_run(run_id)
        actor = user or _RunActor(run.created_by)
        self.report(run_id, task_id, attempt_id=attempt_id, user=user)
        if task.status == "review":
            self._project_service().transition_task(
                run.project_id, task_id, user=actor, target="doing"
            )
        next_round = round if round is not None else task.round + 1
        self._tasks.update(task_id, round=next_round)
        self._record(
            run,
            TIMELINE_RUN_TASK_REPORTED,
            {"task_id": task_id, "role": role, "rework": True, "round": next_round},
            actor=self._actor(user, run),
            task_id=task_id,
        )
        return self.require_task(run_id, task_id)

    # ── complete (G11) ───────────────────────────────────────────────────────

    def complete(
        self,
        run_id: str,
        task_id: str,
        *,
        role: str,
        attempt_id: str,
        changed_paths: Sequence[str] = (),
        user: ProjectActor | None = None,
    ) -> ProjectTaskRow:
        """Finish an attempt, auditing every changed path against ``in_scope`` (G11).

        A path outside the declared scope is a ``TEAM_SCOPE_VIOLATION`` and **nothing
        is written** — the audit runs before the report, so a violation cannot leave
        a half-finished task. Finishing lands the task in ``review`` (a verdict closes
        it), in legal steps through ``ProjectService.transition_task`` — the single
        owner of the state machine.
        """
        task = self.require_task(run_id, task_id)
        scopes = list(task.in_scope)
        outside = [path for path in changed_paths if not path_in_scope(path, scopes)]
        if outside:
            raise OctopError(
                ErrorCode.TEAM_SCOPE_VIOLATION,
                f"task {task_id!r} changed paths outside its scope: {outside}",
                details={"task_id": task_id, "in_scope": scopes, "outside": outside},
            )
        run = self.require_run(run_id)
        actor = user or _RunActor(run.created_by)
        if task.status in {"planning", "todo"}:
            self._project_service().transition_task(
                run.project_id, task_id, user=actor, target="doing"
            )
            task = self.require_task(run_id, task_id)
        if task.status == "doing":
            self._project_service().transition_task(
                run.project_id, task_id, user=actor, target="review"
            )
        updated = self.report(
            run_id,
            task_id,
            attempt_id=attempt_id,
            changed_paths=list(changed_paths),
            user=user,
        )
        self._record(
            run,
            TIMELINE_RUN_TASK_COMPLETED,
            {"task_id": task_id, "role": role, "changed_paths": list(changed_paths)},
            actor=self._actor(user, run),
            task_id=task_id,
        )
        return updated

    # ── task creation (G6 / G7 / G9) ─────────────────────────────────────────

    def create_task(
        self,
        run_id: str,
        *,
        title: str,
        kind: str = "work",
        role: str = "",
        spec: str = "",
        acceptance: Sequence[str] = (),
        in_scope: Sequence[str] = (),
        verify: Sequence[str] = (),
        depends_on: Sequence[str] = (),
        phase: str | None = None,
        round: int | None = None,
        task_id: str | None = None,
        user: ProjectActor | None = None,
    ) -> ProjectTaskRow:
        """Add a task to the board — this entry runs G6 / G7 / G9 before writing.

        G6 (``validate_task_graph``) is **not** this method's private rule: it also
        runs on both of the projects route's writers — the ``deps`` patch
        (``ProjectService.update_task``) and the create verb that takes ``deps``
        (``ProjectService.create_task``). Every writer builds the same board
        (``list_tasks`` *is* ``list_by_project(run.project_id)``) and calls the same
        implementation, so "G6 runs on every write" describes the gate rather than
        one of its callers (T-70).

        G9's task cap runs on the resulting board, and G7 refuses a board that has
        run past its review budget: creating round ``max_review_rounds + 1`` work
        without an escalation decision is the loop the plan refuses to let one more
        repair round paper over. Nothing is written when a gate refuses.
        """
        run = self.require_run(run_id)
        existing = self.list_tasks(run_id)
        if round is None:
            # `round` is the **review cycle**, not a per-task counter: a new task joins
            # the round the board is already in. A new round is opened by asking for
            # one (`create_repair(round=…)`), which is where G7's budget check bites.
            round = max((task.round for task in existing), default=1)
        round = max(1, round)
        if round > run.max_review_rounds and self._runs.get_pending_decision(run_id) is None:
            raise OctopError(
                ErrorCode.TEAM_REWORK_LOOP_LIMIT,
                f"round {round} is past max_review_rounds={run.max_review_rounds} "
                "without an escalation decision",
                details={"round": round, "max_review_rounds": run.max_review_rounds},
            )
        graph = [
            {
                "id": task.id,
                "dependsOn": list(task.deps),
                "status": task.status,
                "kind": task.kind,
                "verify": list(task.verify),
                "role": task.claimed_by or "",
                "round": task.round,
            }
            for task in existing
        ]
        candidate = {
            # Same value the row will get, so the graph is validated against the id the
            # caller asked for -- and a duplicate is refused here, before any insert.
            "id": task_id or new_short_id(),
            "dependsOn": [str(dep) for dep in depends_on],
            "status": "todo",
            "kind": kind,
            "verify": [str(item) for item in verify],
            "role": role,
            "round": round,
        }
        validate_task_graph([*graph, candidate])
        assert_capacity({"tier": run.tier}, task_count=len(graph) + 1)

        actor = user or _RunActor(run.created_by)
        task: ProjectTaskRow = self._project_service().create_task(
            run.project_id,
            user=actor,
            title=title,
            status="todo",
            kind=kind,
            acceptance=[str(item) for item in acceptance],
            in_scope=[str(item) for item in in_scope],
            verify=[str(item) for item in verify],
            deps=[str(dep) for dep in depends_on],
            phase=phase or run.phase,
            description=spec,
            # A run task is owned by a *role*: `team_run_members` resolves it to an
            # agent at dispatch time, and the role is what the ownership/quality
            # gates read.
            assignee_type="team" if role else None,
            assignee_id=role or None,
            task_id=task_id,
        )
        # ``round`` is a patch column, not a creation column (T-09): a task is born
        # in round 1 and moves forward, so the round this call computed is written
        # straight after — one extra UPDATE, and the board never shows round 1 for a
        # task that belongs to round 3.
        if round != task.round:
            refreshed = self._tasks.update(task.id, round=round)
            if refreshed is not None:
                task = refreshed
        self._record(
            run,
            TIMELINE_RUN_TASK_CREATED,
            {"task_id": task.id, "kind": kind, "role": role, "round": round},
            actor=self._actor(user, run),
            task_id=task.id,
        )
        return task

    def create_repair(self, run_id: str, *, title: str, role: str, **fields: Any) -> ProjectTaskRow:
        """A repair task for the next round (G7 applies; ``kind='repair'``)."""
        return self.create_task(run_id, title=title, role=role, kind="repair", **fields)

    def create_quality_task(
        self, run_id: str, *, title: str, role: str, **fields: Any
    ) -> ProjectTaskRow:
        """A quality task owned by a reviewer/qa role (G7 applies; ``kind='quality'``).

        The owner check is the read-side ``quality_owner_invalid`` warning (V4), not
        a block — the plan kept ``kind`` mistakes advisory on purpose.
        """
        return self.create_task(run_id, title=title, role=role, kind="quality", **fields)

    # ── decision gate (G15 / G16) ────────────────────────────────────────────

    def raise_decision(
        self,
        run_id: str,
        *,
        kind: str,
        reason: str,
        options: Sequence[str],
        context: Mapping[str, Any] | None = None,
        actor: str | None = None,
    ) -> dict[str, Any]:
        """Park the run on a decision (G16 escalation, or a host question).

        The decision is stored on the room thread (``threads.pending_decision``),
        which is the one place the gates read: an **unresolved** payload blocks
        advancement, a resolved one does not.
        """
        run = self.require_run(run_id)
        payload = {
            "id": new_short_id(),
            "kind": kind,
            "reason": reason,
            "options": [str(option) for option in options],
            "status": "pending",
            "context": dict(context or {}),
            "created_at": int(time.time()),
        }
        if not self._runs.set_pending_decision(run_id, payload):
            raise OctopError(
                ErrorCode.TEAM_DECISION_PENDING,
                f"run {run_id!r} has no room thread to park a decision on",
                details={"run_id": run_id, "kind": kind},
            )
        self._runs.update_status(run_id, "awaiting_decision")
        self._record(
            run,
            TIMELINE_RUN_DECISION_RAISED,
            {"decision_id": payload["id"], "kind": kind, "reason": reason},
            actor=actor or actor_ref("agent", run.team_agent_id),
        )
        return payload

    def decide(
        self,
        run_id: str,
        *,
        decision_id: str,
        choice: str,
        note: str = "",
        user: ProjectActor | None = None,
    ) -> dict[str, Any]:
        """Resolve the pending decision (G15).

        Two refusals, both from the plan's table: submitting a decision that is not
        pending — including **the same one twice**, because a resolved payload is no
        longer pending — is ``TEAM_DECISION_NOT_PENDING``; a choice outside the
        offered ``options`` is ``TEAM_DECISION_OPTION_INVALID``.
        """
        run = self.require_run(run_id)
        pending = self._runs.get_pending_decision(run_id)
        if pending is None or str(pending.get("status") or "") != "pending":
            raise OctopError(
                ErrorCode.TEAM_DECISION_NOT_PENDING,
                f"run {run_id!r} has no pending decision",
                details={"run_id": run_id, "decision_id": decision_id},
            )
        if str(pending.get("id") or "") != decision_id:
            raise OctopError(
                ErrorCode.TEAM_DECISION_NOT_PENDING,
                f"decision {decision_id!r} is not the pending one",
                details={"run_id": run_id, "decision_id": decision_id},
            )
        options = [str(option) for option in pending.get("options") or []]
        if choice not in options:
            raise OctopError(
                ErrorCode.TEAM_DECISION_OPTION_INVALID,
                f"choice {choice!r} is not one of {options}",
                details={"decision_id": decision_id, "options": options},
            )
        resolved = {
            **pending,
            "status": "resolved",
            "choice": choice,
            "note": note,
            "resolved_by": getattr(user, "id", None),
            "resolved_at": int(time.time()),
        }
        self._runs.set_pending_decision(run_id, resolved)
        if run.status in {"awaiting_decision", "awaiting_confirmation"}:
            self._runs.update_status(run_id, "running")
        self._record(
            run,
            TIMELINE_RUN_DECISION_RESOLVED,
            {"decision_id": decision_id, "choice": choice},
            actor=self._actor(user, run),
        )
        return resolved

    # ── artifacts (G14) ──────────────────────────────────────────────────────

    def read_artifact(self, run_id: str, name: str) -> tuple[str, str]:
        """``(content, revision)`` for one artifact; ``("", "")`` when absent."""
        run = self.require_run(run_id)
        workspace = self._workspace(run)
        if workspace is None:
            return "", ""
        content = workspace.read_text(f"{run_directory(run)}/{name}")
        if content is None:
            return "", ""
        return content, revision_of(content)

    def write_artifact(
        self,
        run_id: str,
        *,
        name: str,
        content: str,
        revision: str,
        role: str,
        user: ProjectActor | None = None,
    ) -> dict[str, Any]:
        """Write a run artifact behind the ownership table and a revision CAS (G14).

        The refusals, in order:

        * ``TEAM_ROLE_UNKNOWN`` (400) — the target **exists** and ``role`` is not in the
          fixed role table. This path's ``role`` is caller-declared, so an unrecognised
          one is an unauthenticated claim rather than a licence: without this gate
          ``normalize_owner_role`` would return ``""`` and the ownership check below
          would fail **open** on a runtime-only artifact. Creating a file is untouched.
        * ``TEAM_ARTIFACT_OWNERSHIP_DENIED`` — ``artifacts.owner_violation`` says
          *this role may not overwrite this file*. Creating a file is allowed (that
          is what lets the first member lay down the skeleton); overwriting one that
          belongs to somebody else is not. Files absent from the table are
          unrestricted, and ``owners == ()`` means runtime-only — nobody overwrites
          those.
        * ``TEAM_ARTIFACT_STALE`` — the caller's ``revision`` is not what is on disk.
          Pass the revision read with the content (``""`` for a file that does not
          exist yet).

        The write itself is the last step: a refused call leaves the file untouched.

        Writing also materialises the artifact's **index row** (``project_artifacts``,
        ``kind='workflow'``) so the panel and the KB archiver have something to point
        at: ``owner_role`` comes from the ownership table (the authority — never
        derived here) and ``phase`` is the run's phase at write time. ``version`` is
        that row's rewrite counter, not this method's ``revision``.
        """
        run = self.require_run(run_id)
        workspace = self._workspace(run)
        if workspace is None:
            raise OctopError(
                ErrorCode.TEAM_RUN_NOT_FOUND,
                f"run {run_id!r} has no workspace bound",
                details={"run_id": run_id},
            )
        path = f"{run_directory(run)}/{name}"
        current = workspace.read_text(path)
        exists = current is not None
        # T-69 / PLAN adjudication (a): an unrecognised role must not read as "no owner
        # ⇒ allow". ``normalize_owner_role`` returns ``""`` for anything off the fixed
        # role table and ``owner_violation`` treats ``""`` as fail-open — but on **this**
        # path ``role`` is *caller-declared* (AM-31: the HTTP face's role is a claim, not
        # an authentication credential), so "unknown" cannot be a licence to overwrite a
        # runtime-only artifact (``STATE.json`` / ``ROSTER.json`` / ``TASKS.json``).
        #
        # The gate sits **before both consumers of ``role``** (``owner_violation`` here
        # and ``_owner_role_for`` at the index row below) — one gate, both forks closed.
        # Creation is deliberately unaffected: ``exists`` false still passes, which is
        # what lets the first member lay down the skeleton.
        if exists and not normalize_owner_role(role):
            raise OctopError(
                ErrorCode.TEAM_ROLE_UNKNOWN,
                f"role {role!r} is not in the fixed role table",
                details={"run_id": run_id, "name": name, "role": role},
            )
        violation = owner_violation(role=role, base=name, exists=exists)
        if violation is not None:
            raise OctopError(
                ErrorCode.TEAM_ARTIFACT_OWNERSHIP_DENIED,
                violation,
                details={"run_id": run_id, "name": name, "role": role},
            )
        current_revision = revision_of(current) if current is not None else ""
        if revision != current_revision:
            raise OctopError(
                ErrorCode.TEAM_ARTIFACT_STALE,
                f"artifact {name!r} moved: expected revision {current_revision!r}",
                details={"run_id": run_id, "name": name, "current": current_revision},
            )
        workspace.write_text(path, content, force=True)
        written = revision_of(content)
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        index_row = self._services.project_artifact_repo.upsert_workflow(
            project_id=run.project_id,
            name=name,
            uri=path,
            size=len(content.encode("utf-8")),
            mime="text/markdown",
            # The row's `hash` is the body digest; `revision` stays the short CAS token
            # (the two are deliberately different things — see the repo docstring).
            file_hash=digest,
            owner_role=_owner_role_for(name, role),
            phase=run.phase,
            created_by=self._actor(user, run),
        )
        project = self._projects.get(run.project_id)
        kb_id = getattr(project, "kb_id", None)
        # The file and its index row are the primary state, so the write is recorded
        # first: whatever happens to the archiving below, the run's log shows the
        # artifact *was* written.
        self._record(
            run,
            TIMELINE_RUN_ARTIFACT_WRITTEN,
            {
                "name": name,
                "role": role,
                "revision": written,
                "artifact_id": index_row.artifact_id,
                "kb_id": str(kb_id) if kb_id else None,
            },
            actor=self._actor(user, run),
        )
        # ── the reference hop: archive the body into the project KB and bind the
        # reference to the row just written (T-18's archiver is the only writer of
        # `kb_document_id`). No rollback: the artifact is already on disk and indexed,
        # and undoing it would leave a worse state than the failed reference. The
        # failure is raised *and* recorded — a caller may only see the 5xx, while the
        # run log has to be able to explain what happened. Retrying is safe: the
        # binder is idempotent.
        if self._kb_archiver_factory is not None and kb_id and user is not None:
            # The KB side authorises this write **by actor** (``require_owner``), so the
            # actor has to be the real one. When it is unknown we skip the hop rather
            # than substitute a default: a guess here is an authorisation decision, not
            # a label. The write itself is already recorded on the timeline above.
            archiver = self._kb_archiver_factory(
                str(kb_id), index_row.artifact_id, actor_user_id=int(user.id)
            )
            try:
                archiver.write_document(project_id=run.project_id, text=content, digest=digest)
            except Exception as err:
                self._record(
                    run,
                    TIMELINE_RUN_ARCHIVE_FAILED,
                    {
                        "name": name,
                        "role": role,
                        "artifact_id": index_row.artifact_id,
                        "kb_id": str(kb_id),
                        "error": str(err),
                    },
                    actor=self._actor(user, run),
                )
                raise
        return {
            "name": name,
            "revision": written,
            "hash": digest,
            # Internal handoff (the HTTP response model does not expose it): the KB
            # archiver binds its document to this row (T-46).
            "artifact_id": index_row.artifact_id,
        }

    # ── dispatch (必答 C: persist → ask_agent, one-shot → task) ──────────────

    async def dispatch_task(
        self,
        run_id: str,
        task_id: str,
        *,
        role: str,
        user: ProjectActor,
        mode: str | None = None,
    ) -> DispatchOutcome:
        """Dispatch a claimed task down the channel its run mode selects.
        * ``persist`` → the **dispatch turn** (``ask_agent``), through
          :func:`octop.infra.projects.dispatch.run_dispatch_turn` — the shared
          **project-dispatch bridge** (PLAN 必答 C), not a room bridge: each dispatch mints
          its own thread on a dispatch-only session key (SPEC B30, see
          ``infra/projects/dispatch.py``), so ``run.room_thread_id`` carries no turn. The
          implementation is self-consistent — what was wrong here is the *name* we gave it.
          Whether the room should host the turn instead is an open product decision
          (tracked as a user decision, ``SUMMARY`` §B6); it is **not** decided here.
          The session key is **run-scoped** (``…:<runId>:team-run``), never the dispatcher's DM
          key (SPEC B30 ①) — that part is unchanged and still holds.
                * ``one-shot`` → the host's ``task`` subagent channel: no room turn is
                  started here, because the subgraph runs inside the host. This method
                  records the dispatch and reports ``channel='task'`` so the two channels are
                  never conflated.

                The two branches are asserted separately: only the persist branch touches
                ``run_dispatch_turn``.
        """
        run = self.require_run(run_id)
        task = self.require_task(run_id, task_id)
        resolved = mode or run.mode
        if resolved not in RUN_MODES:
            raise ValueError(f"unknown run mode: {resolved!r}")
        # The board stores the *role*; dispatch.py runs an *agent*. Resolve it
        # through `team_run_members` so the shared dispatch path keeps its one
        # meaning of `assignee_id` (PLAN 必答 C).
        member = self._runs.get_member(run_id, role) if role else None
        assignee_id = member.agent_id if member is not None else run.team_agent_id
        if resolved == "one-shot":
            self._record(
                run,
                TIMELINE_RUN_DISPATCHED,
                {"task_id": task_id, "role": role, "channel": "task"},
                actor=actor_ref("user", user.id),
                task_id=task_id,
            )
            return DispatchOutcome(task_id=task_id, channel="task", thread_id=None)

        if self._agent_manager is None or self._gateway is None:
            raise OctopError(
                ErrorCode.AGENT_NOT_RUNNING,
                "the agent runtime is not available for a persist dispatch",
            )
        from octop.infra.projects.dispatch import run_dispatch_turn

        project = self._projects.get(run.project_id)
        if project is None:  # pragma: no cover - FK guarantees the row
            raise OctopError(ErrorCode.PROJECT_NOT_FOUND, "run project not found")
        session_key = ThreadRegistry.make_key(
            agent_id=assignee_id,
            channel_type=ThreadRegistry.CHANNEL_DASHBOARD,
            channel_subject_id=run_id,
            channel_chat_type=ROOM_CHAT_TYPE,
        )
        thread_id = await run_dispatch_turn(
            repos=self._services.repos,
            agent_manager=self._agent_manager,
            gateway=self._gateway,
            project=project,
            task=replace(task, assignee_type="agent", assignee_id=assignee_id),
            dispatcher_user_id=user.id,
            session_key=session_key,
        )
        self._record(
            run,
            TIMELINE_RUN_DISPATCHED,
            {"task_id": task_id, "role": role, "channel": "ask_agent", "thread_id": thread_id},
            actor=actor_ref("user", user.id),
            task_id=task_id,
        )
        return DispatchOutcome(task_id=task_id, channel="ask_agent", thread_id=thread_id)

    # ── lifecycle: resume / cancel ───────────────────────────────────────────

    def resume(self, run_id: str, *, user: ProjectActor | None = None) -> TeamRunRow:
        """Return a parked run to ``running`` (a resolved decision, or a nudge)."""
        run = self.require_run(run_id)
        if run.status in {"complete", "failed", "cancelled"}:
            raise OctopError(
                ErrorCode.TEAM_RUN_TERMINAL,
                f"run is {run.status}; a terminal run cannot resume",
                details={"status": run.status},
            )
        self._runs.update_status(run_id, "running")
        updated = self.require_run(run_id)
        self._record(
            updated, TIMELINE_RUN_STATUS_CHANGED, {"to": "running"}, actor=self._actor(user, run)
        )
        return updated

    def cancel(self, run_id: str, *, user: ProjectActor | None = None) -> TeamRunRow:
        """Cancel a run. Terminal: a cancelled run never advances again."""
        run = self.require_run(run_id)
        if run.status in {"complete", "failed", "cancelled"}:
            return run
        self._runs.update_status(run_id, "cancelled")
        updated = self.require_run(run_id)
        self._record(
            updated, TIMELINE_RUN_STATUS_CHANGED, {"to": "cancelled"}, actor=self._actor(user, run)
        )
        return updated

    # ── internals ────────────────────────────────────────────────────────────

    def _actor(self, user: ProjectActor | None, run: TeamRunRow) -> str:
        return actor_ref("user", user.id if user is not None else run.created_by)

    def _record(
        self,
        run: TeamRunRow,
        action: str,
        payload: Mapping[str, Any],
        *,
        actor: str,
        task_id: str | None = None,
    ) -> None:
        """Append a timeline row — every state write in this service goes through here."""
        self._timeline.append(
            project_id=run.project_id,
            actor=actor,
            action=action,
            task_id=task_id,
            payload=dict(payload),
        )


def _owner_role_for(name: str, writer_role: str) -> str:
    """The role recorded on the artifact's index row.

    ``ARTIFACT_OWNERS`` (via ``owners_of``) is the authority: a listed artifact with
    a single owner records that owner; with several owners it records the writer when
    the writer is one of them, else the first (the table's order is meaningful). An
    artifact the table does not list — or lists as runtime-only, ``()`` — records the
    writer, because that is the only role we know wrote it.
    """
    owners = owners_of(name)
    if owners:
        return writer_role if writer_role in owners else owners[0]
    return writer_role


def _kept_lead(
    kept: Sequence[Mapping[str, Any]],
    *,
    host_agent_id: str | None,
    lead_agent_id: str | None,
) -> str | None:
    """Which kept member carries ``is_lead`` (PLAN AM-4).

    An explicit ``host_agent_id`` wins; otherwise the manifest's
    ``lead_agent_id``. Neither ⇒ the team host leads directly and no member row is
    marked, which ``TeamRunRepo.lead_member()`` reports as ``None`` on purpose.
    """
    for candidate in (host_agent_id, lead_agent_id):
        if candidate and any(str(member.get("agent_id") or "") == candidate for member in kept):
            return candidate
    return None


#: Everything the module exports for the API layer and the export projector.
__all__ = [
    "AWAITING_STATUS_BY_PHASE",
    "DispatchOutcome",
    "GOAL_MAX_LENGTH",
    "ROOM_CHAT_TYPE",
    "RUN_DIR_PREFIX",
    "RUN_ROOT_EXPLICIT_PREFIX",
    "RUN_ROOT_HOST_WORKSPACE",
    "TIMELINE_RUN_ARCHIVE_FAILED",
    "TIMELINE_RUN_ARTIFACT_WRITTEN",
    "TIMELINE_RUN_CREATED",
    "TIMELINE_RUN_DECISION_RAISED",
    "TIMELINE_RUN_DECISION_RESOLVED",
    "TIMELINE_RUN_DISPATCHED",
    "TIMELINE_RUN_MEMBER_SKIPPED",
    "TIMELINE_RUN_PHASE_ADVANCED",
    "TIMELINE_RUN_STATUS_CHANGED",
    "TIMELINE_RUN_TASK_CLAIMED",
    "TIMELINE_RUN_TASK_COMPLETED",
    "TIMELINE_RUN_TASK_CREATED",
    "TIMELINE_RUN_TASK_REPORTED",
    "TIMELINE_RUN_VERDICT",
    "TeamRunService",
    "path_in_scope",
    "revision_of",
    "run_root_for",
    "run_directory",
    "run_id_for",
]
