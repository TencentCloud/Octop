"""``TeamRunService``'s plan gate and settle write side (T4).

Covers ``PLAN.md §2.2`` (the verb signatures), ``§3`` (the write matrix) and
``§4`` (A2), plus ``SPEC §3`` R1/R4/R5 and ``SPEC §0`` D2. The rule for this file
is the same one the run-service file states: **a gate is only covered when the
refusal and the pass are both asserted**, and every refusal also asserts that
nothing was written — a gate that rejects after writing is not a gate.

Three properties are pinned structurally rather than by inspection:

* the draft rides **inside** ``threads.pending_decision`` — the test reads the very
  payload the gate reads and checks the draft is a key on it, so a draft stored
  anywhere else makes both the carrier assertion and the "the gate still blocks"
  assertion fail;
* ``:approve`` writes **database rows** and leaves ``TASKS.json`` absent — the
  runtime-only projection stays a projection;
* ``stranded`` **reports without writing**: the rows, the timeline and the file
  tree are compared before and after.

Everything runs on a real SQLite control plane with real repos; only the workspace
is a fake (an in-memory dict, so the run directory is inspectable).
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from octop.config import OctopConfig
from octop.infra.agents.teams import run_service as run_service_module
from octop.infra.agents.teams.run_service import TeamRunService, run_directory
from octop.infra.agents.teams.service import TeamService
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.services import build_shared_services
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.gateway.threads import ThreadRegistry
from octop.infra.utils.paths import PathLayout

TEAM_ID = "ag-team"
MANIFEST = ".octop/manifest.json"
SCOPE = "src/octop/infra/agents/teams/run_service.py"
VERIFY = "uv run --no-sync pytest tests/unit/agents/test_plan_service.py -q"
FILLED_SPEC = (
    "# SPEC\n\n## 边界与禁止项\n\n| 边界 | 处置 |\n| --- | --- |\n| 不新增错误码 | 复用 |\n"
)


class Actor:
    """The slice of a user row ``ProjectActor`` needs."""

    def __init__(self, user_id: int) -> None:
        self.id = user_id
        self.permissions = ["projects", "knowledge_bases"]

    @property
    def is_admin(self) -> bool:
        return False


class FakeWorkspace:
    """``BackendWorkspace`` stand-in: a dict of workspace-relative path → text."""

    def __init__(self, files: dict[str, str] | None = None) -> None:
        self.files: dict[str, str] = dict(files or {})

    def read_text(self, path: str, *, limit: int = 10_000_000) -> str | None:
        return self.files.get(str(path))

    def write_text(self, path: str, content: str, *, force: bool = False) -> None:
        self.files[str(path)] = content

    def exists(self, path: str) -> bool:
        return str(path) in self.files

    def list_dir(self, path: str = ".") -> list[Any]:
        """Direct entries under *path*, in the dict shape the harness returns."""
        prefix = "" if str(path) in {"", "."} else f"{str(path).rstrip('/')}/"
        entries: list[Any] = []
        for name in sorted(self.files):
            if not name.startswith(prefix):
                continue
            if "/" not in name[len(prefix) :]:
                entries.append({"path": name, "is_dir": False})
        return entries


class _StubGateway:
    """Just enough gateway for the room thread: a real registry over the test DB."""

    def __init__(self, services: Any) -> None:
        self.thread_registry = ThreadRegistry(
            session_repo=services.session_repo,
            thread_repo=services.thread_repo,
        )


def manifest() -> str:
    members = [
        {"agent_id": TEAM_ID, "role": "lead"},
        {"agent_id": "ag-arch", "role": "architect"},
        {"agent_id": "ag-be", "role": "backend"},
        {"agent_id": "ag-qa", "role": "qa"},
    ]
    return json.dumps({"members": members, "lead_agent_id": TEAM_ID})


@dataclass
class Harness:
    db: SqlitePool
    services: Any
    service: TeamRunService
    workspace: FakeWorkspace
    user: Actor

    def create_run(self, **fields: Any) -> Any:
        return self.service.create(team_agent_id=TEAM_ID, user=self.user, **fields)

    def add_task(self, run: Any, **fields: Any) -> Any:
        return self.service.create_task(run.run_id, user=self.user, **fields)

    def write(self, run: Any, name: str, content: str) -> None:
        self.workspace.write_text(f"{run_directory(run)}/{name}", content)

    def actions(self, run: Any) -> list[str]:
        return [
            event.action for event in self.services.timeline_repo.list_by_project(run.project_id)
        ]

    def rows(self, run: Any) -> dict[str, tuple[str, int, str | None, int]]:
        return {
            task.id: (task.status, task.attempt, task.attempt_id, task.updated_at)
            for task in self.service.list_tasks(run.run_id)
        }

    def pending(self, run: Any) -> dict[str, Any]:
        payload = self.service.snapshot(run)["pending_decision"]
        assert isinstance(payload, dict), payload
        return payload

    def claim_foreign(self, task_id: str, token: str) -> None:
        """Put another generation's token on the row and move it to ``doing``."""
        claimed = self.service._tasks.claim(
            task_id, claimed_by="backend", expected_attempt_id=None, attempt_id=token
        )
        assert claimed is not None
        self.service._tasks.update(task_id, status="doing")


@pytest.fixture
def harness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Harness]:
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path / "home"))
    paths = PathLayout(tmp_path / ".octop")
    paths.ensure_root()
    db = SqlitePool(paths.db)
    run_migrations(db)
    services = build_shared_services(db=db, paths=paths, config=OctopConfig())
    user = services.user_repo.create(username="owner", password_hash="h", role="user")
    services.agent_repo.create(agent_id=TEAM_ID, user_id=user, name="Team", kind="team")
    workspace = FakeWorkspace({MANIFEST: manifest()})
    gateway = _StubGateway(services)
    service = TeamRunService(
        services=services,
        gateway=gateway,  # type: ignore[arg-type]
        workspace_for=lambda agent_id: workspace if agent_id == TEAM_ID else None,
        team_service=TeamService(
            services.repos,
            workspace_for=lambda agent_id: workspace if agent_id == TEAM_ID else None,
        ),
    )
    yield Harness(db=db, services=services, service=service, workspace=workspace, user=Actor(user))


def assert_code(err: Any, code: ErrorCode, *, status: int) -> None:
    assert err.value.code is code, (err.value.code, err.value.message)
    assert err.value.status == status


def _task(
    task_id: str,
    *,
    owner: str = "backend",
    deps: tuple[str, ...] = (),
    verify: str = VERIFY,
) -> dict[str, Any]:
    """One draft task carrying the *draft* vocabulary the write side must translate."""
    return {
        "id": task_id,
        "owner": owner,
        "title": f"do {task_id}",
        "kind": "work",
        "spec": f"spec for {task_id}",
        "acceptance": ["accepted"],
        "inScope": [SCOPE],
        "verify": verify,
        "dependsOn": list(deps),
        "status": "pending",
        "attempt": 3,
        "round": 7,
        "verdict": "pass",
    }


def _draft(*tasks: dict[str, Any], roles: tuple[str, ...] = ("lead", "architect", "backend", "qa")):
    return {"roles": list(roles), "tasks": list(tasks)}


# ── :plan (R1) ───────────────────────────────────────────────────────────────


def test_the_draft_lives_inside_the_pending_decision_and_nowhere_else(
    harness: Harness,
) -> None:
    run = harness.create_run(goal="暂存方案", tier="standard")
    payload = harness.service.stage_plan(run.run_id, draft=_draft(_task("T1")), user=harness.user)

    pending = harness.pending(run)
    assert pending["id"] == payload["id"]
    assert pending["status"] == "pending"
    assert pending["kind"] == "plan"
    assert pending["options"] == ["approve", "discard"]
    draft = pending["draft"]
    assert isinstance(draft["updatedAt"], int)
    assert draft["planStatus"] == "staged"
    # normalised to the storage vocabulary, and the draft's own values dropped
    (task,) = draft["tasks"]
    assert task["id"] == "T1"
    assert (task["status"], task["attempt"], task["round"], task["verdict"]) == (
        "todo",
        0,
        1,
        None,
    )
    # zero migration: there is no column a draft could have been parked in
    with harness.db.connect() as conn:
        columns = {str(row["name"]) for row in conn.execute("PRAGMA table_info(threads)")}
    assert "draft" not in columns
    assert "planStatus" not in columns


def test_restaging_overwrites_the_one_draft_key_and_reuses_the_decision(
    harness: Harness,
) -> None:
    run = harness.create_run(goal="覆盖", tier="standard")
    first = harness.service.stage_plan(run.run_id, draft=_draft(_task("T1")), user=harness.user)
    second = harness.service.stage_plan(run.run_id, draft=_draft(_task("T2")), user=harness.user)

    assert second["id"] == first["id"]
    pending = harness.pending(run)
    assert [task["id"] for task in pending["draft"]["tasks"]] == ["T2"]
    # one record per stage, both about the same decision — not a second decision
    assert harness.actions(run).count("run.decision_raised") == 2


def test_a_staged_draft_keeps_every_advance_refused(harness: Harness) -> None:
    """The gate is inherited, not rebuilt: ``advance`` itself must refuse."""
    run = harness.create_run(goal="门仍生效", tier="standard")
    harness.write(run, "SPEC.md", FILLED_SPEC)
    harness.service.stage_plan(run.run_id, draft=_draft(_task("T1")), user=harness.user)

    with pytest.raises(OctopError) as err:
        harness.service.advance(run.run_id, to_phase="research", user=harness.user)
    assert_code(err, ErrorCode.TEAM_DECISION_PENDING, status=409)
    assert harness.service.require_run(run.run_id).phase == "clarify"


def test_stage_plan_refuses_an_owner_outside_the_roster_without_writing(
    harness: Harness,
) -> None:
    run = harness.create_run(goal="越权 owner", tier="standard")
    with pytest.raises(OctopError) as err:
        harness.service.stage_plan(
            run.run_id, draft=_draft(_task("T1", owner="frontend")), user=harness.user
        )
    assert_code(err, ErrorCode.TEAM_PLAN_DRAFT_INVALID, status=422)
    assert err.value.details["code"] == "owner-not-in-roles"
    assert harness.service.snapshot(run)["pending_decision"] is None
    assert harness.service.list_tasks(run.run_id) == []


def test_stage_plan_refuses_a_draft_over_the_task_cap_before_any_write(
    harness: Harness,
) -> None:
    """G9 is asked at ``:plan`` too, over the draft's own count (SPEC §3-R3)."""
    run = harness.create_run(goal="容量", tier="quick")  # quick ⇒ dispatch_cap = 15
    over_cap = _draft(*(_task(f"T{i:02d}") for i in range(16)))
    with pytest.raises(OctopError) as err:
        harness.service.stage_plan(run.run_id, draft=over_cap, user=harness.user)
    assert_code(err, ErrorCode.TEAM_RUN_TASK_LIMIT, status=409)
    assert err.value.details == {"tier": "quick", "limit": 15, "count": 16}
    assert harness.service.snapshot(run)["pending_decision"] is None
    assert harness.service.list_tasks(run.run_id) == []


def test_stage_plan_admits_a_draft_exactly_at_the_task_cap(harness: Harness) -> None:
    """The guard is a strict ``>``: the cap itself is legal and still gets staged."""
    run = harness.create_run(goal="容量边界", tier="quick")
    at_cap = _draft(*(_task(f"T{i:02d}") for i in range(15)))
    payload = harness.service.stage_plan(run.run_id, draft=at_cap, user=harness.user)
    assert len(payload["draft"]["tasks"]) == 15
    assert harness.service.list_tasks(run.run_id) == []


def test_every_plan_verb_refuses_a_terminal_run(harness: Harness) -> None:
    run = harness.create_run(goal="终态", tier="quick")
    harness.service.cancel(run.run_id, user=harness.user)

    with pytest.raises(OctopError) as err:
        harness.service.stage_plan(run.run_id, draft=_draft(_task("T1")), user=harness.user)
    assert_code(err, ErrorCode.TEAM_RUN_TERMINAL, status=409)
    for call in (
        lambda: harness.service.approve_plan(run.run_id, user=harness.user),
        lambda: harness.service.discard_plan(run.run_id, user=harness.user),
        lambda: harness.service.settle(run.run_id, user=harness.user),
    ):
        with pytest.raises(OctopError) as refused:
            call()
        assert_code(refused, ErrorCode.TEAM_RUN_TERMINAL, status=409)


# ── :approve (R4) ────────────────────────────────────────────────────────────


def test_approve_plan_writes_database_rows_and_translates_the_draft(
    harness: Harness,
) -> None:
    run = harness.create_run(goal="批准", tier="standard")
    harness.service.stage_plan(
        run.run_id,
        draft=_draft(_task("T1", owner="architect"), _task("T2", deps=("T1",))),
        user=harness.user,
    )

    created = harness.service.approve_plan(run.run_id, user=harness.user)

    assert [task.id for task in created] == ["T1", "T2"]
    rows = {task.id: task for task in harness.service.list_tasks(run.run_id)}
    assert set(rows) == {"T1", "T2"}
    first = rows["T1"]
    assert (first.title, first.description, first.kind) == ("do T1", "spec for T1", "work")
    assert first.status == "todo"
    assert first.in_scope == (SCOPE,)  # inScope → in_scope
    assert first.verify == (VERIFY,)  # verify: str → verify[]
    assert first.acceptance == ("accepted",)
    assert (first.assignee_type, first.assignee_id) == ("team", "architect")
    assert first.deps == ()
    assert rows["T2"].deps == ("T1",)  # dependsOn → deps
    # I2 / X-1: the projection is not written — the rows are the truth
    assert not harness.workspace.exists(f"{run_directory(run)}/TASKS.json")
    # the decision is resolved and the draft key is gone
    pending = harness.pending(run)
    assert pending["status"] == "resolved"
    assert "draft" not in pending
    assert isinstance(pending["planApprovedAt"], int)
    # R13: the merge write happens once
    with pytest.raises(OctopError) as err:
        harness.service.approve_plan(run.run_id, user=harness.user)
    assert_code(err, ErrorCode.TEAM_PLAN_DRAFT_MISSING, status=409)
    assert len(harness.service.list_tasks(run.run_id)) == 2


def test_approve_plan_keeps_settled_rows_and_replaces_everything_else(
    harness: Harness,
) -> None:
    run = harness.create_run(goal="合并", tier="standard")
    done = harness.add_task(run, title="已完成", role="backend", in_scope=[SCOPE])
    blocked = harness.add_task(run, title="受阻", role="qa", in_scope=[SCOPE])
    doing = harness.add_task(run, title="进行中", role="backend", in_scope=[SCOPE])
    for task, status in ((done, "done"), (blocked, "blocked"), (doing, "doing")):
        harness.service._tasks.update(task.id, status=status)
    harness.service.stage_plan(
        run.run_id, draft=_draft(_task("T1"), _task("T2")), user=harness.user
    )

    harness.service.approve_plan(run.run_id, user=harness.user)

    board = {task.id: task for task in harness.service.list_tasks(run.run_id)}
    assert set(board) == {done.id, blocked.id, "T1", "T2"}
    assert (board[done.id].status, board[blocked.id].status) == ("done", "blocked")
    assert doing.id not in board
    assert harness.service._tasks.get(doing.id) is None


def test_approve_plan_refuses_on_the_merged_board_before_any_write(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """G9 is asked about ``settled ∪ draft``, and its refusal precedes every write."""
    run = harness.create_run(goal="容量", tier="standard")
    kept = harness.add_task(run, title="保留", role="backend", in_scope=[SCOPE])
    harness.service._tasks.update(kept.id, status="done")
    harness.service.stage_plan(
        run.run_id, draft=_draft(_task("T1"), _task("T2")), user=harness.user
    )

    seen: list[int] = []
    real = run_service_module.assert_capacity

    def _cap(
        snapshot: Mapping[str, Any],
        *,
        task_count: int | None = None,
        member_count: int | None = None,
    ) -> None:
        if task_count is not None:
            seen.append(task_count)
            raise OctopError(ErrorCode.TEAM_RUN_TASK_LIMIT, "merged board over cap", details={})
        real(snapshot, member_count=member_count)

    monkeypatch.setattr(run_service_module, "assert_capacity", _cap)

    with pytest.raises(OctopError) as err:
        harness.service.approve_plan(run.run_id, user=harness.user)
    assert_code(err, ErrorCode.TEAM_RUN_TASK_LIMIT, status=409)
    assert seen == [3]  # one settled + two draft
    assert {task.id for task in harness.service.list_tasks(run.run_id)} == {kept.id}
    assert not harness.workspace.exists(f"{run_directory(run)}/TASKS.json")
    assert "draft" in harness.pending(run)  # still staged: a refusal writes nothing


# ── :discard (R5) ────────────────────────────────────────────────────────────


def test_discard_plan_cancels_the_draft_for_this_run_and_refuses_twice(
    harness: Harness,
) -> None:
    run = harness.create_run(goal="丢弃", tier="standard")
    harness.write(run, "SPEC.md", FILLED_SPEC)
    harness.service.stage_plan(
        run.run_id, draft=_draft(_task("T1"), _task("T2")), user=harness.user
    )

    payload = harness.service.discard_plan(run.run_id, reason="范围变了", user=harness.user)

    assert payload["status"] == "cancelled"
    assert payload["discarded"]["reason"] == "范围变了"
    assert payload["discarded"]["taskCount"] == 2
    assert isinstance(payload["discarded"]["at"], int)
    assert "draft" not in harness.pending(run)
    assert harness.service.list_tasks(run.run_id) == []
    assert not harness.workspace.exists(f"{run_directory(run)}/TASKS.json")
    # the gate is released: resume unparks, then the phase edge opens again
    harness.service.resume(run.run_id, user=harness.user)
    advanced = harness.service.advance(run.run_id, to_phase="research", user=harness.user)
    assert advanced.phase == "research"
    # a second discard has nothing to cancel
    with pytest.raises(OctopError) as err:
        harness.service.discard_plan(run.run_id, user=harness.user)
    assert_code(err, ErrorCode.TEAM_PLAN_DRAFT_MISSING, status=409)


# ── A2: report only, then settle ─────────────────────────────────────────────


def test_stranded_reports_without_writing_anything(harness: Harness) -> None:
    harness.service.bind_runtime()
    run = harness.create_run(goal="只报不动", tier="standard")
    task = harness.add_task(run, title="被占住", role="backend", in_scope=[SCOPE])
    harness.claim_foreign(task.id, "previousboot.0001")
    rows_before = harness.rows(run)
    actions_before = harness.actions(run)

    items = harness.service.stranded(run.run_id)

    assert [item.id for item in items] == [task.id]
    assert items[0].reason == "epoch"
    assert items[0].epochMismatch is True
    assert items[0].owner == "backend"
    assert rows_before == harness.rows(run)
    assert actions_before == harness.actions(run)


def test_settle_rearms_only_the_selected_stranded_rows(harness: Harness) -> None:
    harness.service.bind_runtime()
    run = harness.create_run(goal="清算", tier="standard")
    first = harness.add_task(run, title="搁浅一", role="backend", in_scope=[SCOPE])
    second = harness.add_task(run, title="搁浅二", role="qa", in_scope=[SCOPE])
    harness.claim_foreign(first.id, "previousboot.0001")
    harness.claim_foreign(second.id, "previousboot.0002")
    attempts = {first.id: harness.service._tasks.get(first.id).attempt, second.id: None}
    attempts[second.id] = harness.service._tasks.get(second.id).attempt

    settled = harness.service.settle(run.run_id, task_ids=[first.id], reason="重启")

    assert settled == [first.id]
    rearmed = harness.service._tasks.get(first.id)
    assert rearmed.status == "todo"
    assert rearmed.attempt == attempts[first.id] + 1
    assert rearmed.attempt_id != "previousboot.0001"
    assert harness.service._tasks.report(first.id, attempt_id="previousboot.0001") is None
    # the row that was not selected is untouched
    untouched = harness.service._tasks.get(second.id)
    assert (untouched.status, untouched.attempt, untouched.attempt_id) == (
        "doing",
        attempts[second.id],
        "previousboot.0002",
    )
    # nothing is stranded twice: the re-armed row carries this generation's token
    assert [item.id for item in harness.service.stranded(run.run_id)] == [second.id]


def test_settle_writes_nothing_when_nothing_is_stranded(harness: Harness) -> None:
    run = harness.create_run(goal="无搁浅", tier="standard")
    task = harness.add_task(run, title="从未派发", role="backend", in_scope=[SCOPE])
    rows_before = harness.rows(run)
    actions_before = harness.actions(run)

    assert harness.service.stranded(run.run_id) == ()
    assert harness.service.settle(run.run_id) == []
    # I6: no "nothing to settle" refusal code, and I7: no write at all
    assert rows_before == harness.rows(run)
    assert actions_before == harness.actions(run)
    assert harness.service._tasks.get(task.id).attempt == 0


def test_approve_plan_refuses_a_dangling_dependency_as_a_draft_refusal(
    harness: Harness,
) -> None:
    """★ B9: superseding an unsettled task can orphan a dependency, and that refusal
    is a **draft** refusal — 422 ``TEAM_PLAN_DRAFT_INVALID`` with ``details.code ==
    "missing-id"`` — not the graph gate's 409, and it precedes every write."""
    run = harness.create_run(goal="悬空依赖", tier="standard")
    superseded = harness.add_task(run, title="将被取代", role="backend", in_scope=[SCOPE])
    settled = harness.add_task(run, title="已结算", role="backend", in_scope=[SCOPE])
    # The settled row keeps a dependency on the row the draft supersedes — that is the
    # only way a dangling edge can appear *after* the draft itself validated clean.
    harness.service._tasks.update(settled.id, status="done", deps=[superseded.id])
    harness.service.stage_plan(run.run_id, draft=_draft(_task("T9")), user=harness.user)

    rows_before = harness.rows(run)
    actions_before = harness.actions(run)

    with pytest.raises(OctopError) as err:
        harness.service.approve_plan(run.run_id, user=harness.user)

    assert_code(err, ErrorCode.TEAM_PLAN_DRAFT_INVALID, status=422)
    assert err.value.details["code"] == "missing-id"
    assert err.value.details["path"] == [settled.id, superseded.id]
    assert harness.rows(run) == rows_before  # refused before the merge write
    assert harness.actions(run) == actions_before
    assert "draft" in harness.pending(run)


def test_settle_persists_the_stranded_provenance_it_computed(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """★ I5 lands: the three keys ``settle_tasks`` derives are persisted, not dropped.

    ``settle`` writes the very drafts ``settle_tasks`` returned into the payload of
    the one ``run.task_settled`` timeline row. A ``settle`` that consumed only ``id``
    / ``status`` would leave ``strandedAt`` / ``strandedFrom`` / ``note`` computed but
    unlanded — this assertion is what turns that red.
    """
    harness.service.bind_runtime()
    run = harness.create_run(goal="落盘同源", tier="standard")
    task = harness.add_task(run, title="搁浅", role="backend", in_scope=[SCOPE])
    harness.claim_foreign(task.id, "previousboot.0001")
    attempt_before = harness.service._tasks.get(task.id).attempt

    recorded: list[dict[str, Any]] = []
    real_record = harness.service._record

    def _spy(
        run_row: Any,
        action: str,
        payload: Mapping[str, Any],
        *,
        actor: str,
        task_id: str | None = None,
    ) -> None:
        if action == run_service_module.TIMELINE_RUN_TASK_SETTLED:
            recorded.append(dict(payload))
        real_record(run_row, action, payload, actor=actor, task_id=task_id)

    monkeypatch.setattr(harness.service, "_record", _spy)

    assert harness.service.settle(run.run_id, reason="重启") == [task.id]

    assert len(recorded) == 1
    payload = recorded[0]
    assert payload["task_ids"] == [task.id]
    assert payload["reason"] == "重启"
    (record,) = payload["tasks"]
    assert record["id"] == task.id
    assert record["strandedFrom"] == "doing"
    assert record["note"] == "重启"
    assert isinstance(record["strandedAt"], int) and record["strandedAt"] > 0
    row = harness.service._tasks.get(task.id)
    assert (row.status, row.attempt) == ("todo", attempt_before + 1)
