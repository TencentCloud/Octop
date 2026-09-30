"""TeamRunService — every gate, both sides (PLAN §门禁落点④ G2–G16).    assert run_root_for("team/R1/X.md", workspace_dir=ws, run_root_of=declared("explicit:")) is None

The rule for this file: **a gate is only covered when the refusal and the pass are
both asserted**. "It did not raise" is not evidence; each refusal case also checks
that nothing was written, because a gate that rejects *after* writing is not a gate.

Everything runs on a real SQLite control plane with real repos; only two things are
fakes — the workspace (an in-memory dict, so the run directory is inspectable) and,
in the dispatch test, the agent turn (`run_dispatch_turn` is stubbed: this machine
has no provider, so no real turn can run — that half stays unverified and is called
out where it matters).
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from octop.config import OctopConfig
from octop.infra.agents.manager import AgentManager
from octop.infra.agents.teams import learnings as L
from octop.infra.agents.teams import run_service as run_service_module
from octop.infra.agents.teams.pipeline import ROLES
from octop.infra.agents.teams.run_service import (
    ROOM_CHAT_TYPE,
    TIMELINE_RUN_ARCHIVE_FAILED,
    TIMELINE_RUN_ARTIFACT_WRITTEN,
    TIMELINE_RUN_CREATED,
    TIMELINE_RUN_DECISION_RAISED,
    TIMELINE_RUN_DECISION_RESOLVED,
    TIMELINE_RUN_PHASE_ADVANCED,
    TIMELINE_RUN_TASK_CLAIMED,
    TIMELINE_RUN_TASK_COMPLETED,
    TIMELINE_RUN_TASK_CREATED,
    TeamRunService,
    path_in_scope,
    run_directory,
    run_id_for,
    run_root_for,
)
from octop.infra.agents.teams.service import TeamService
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.services import build_shared_services
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.gateway.threads import ThreadRegistry
from octop.infra.utils.paths import PathLayout

TEAM_ID = "ag-team"
MANIFEST = ".octop/manifest.json"


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
        """**Same shape as the harness**: workspace-relative ``{"path", "is_dir"}``.

        T-72: the real ``BackendWorkspace.list_dir`` is documented as "Always
        workspace-relative (``skills/demo``), never basename-only" — a basename-only
        fake is precisely what hid the ``present_artifacts`` shape bug.
        """
        prefix = "" if str(path) in {"", "."} else str(path).rstrip("/") + "/"
        entries: list[Any] = []
        for name in sorted(self.files):
            if not name.startswith(prefix):
                continue
            rest = name[len(prefix) :]
            if "/" not in rest:
                entries.append({"path": name, "is_dir": False})
        return entries


class _StubGateway:
    """Just enough gateway for the room thread: a real registry over the test DB."""

    def __init__(self, services: Any) -> None:
        self.thread_registry = ThreadRegistry(
            session_repo=services.session_repo,
            thread_repo=services.thread_repo,
        )


@dataclass
class Harness:
    services: Any
    service: TeamRunService
    workspace: FakeWorkspace
    user: Actor
    gateway: _StubGateway
    dispatches: list[dict[str, Any]] = field(default_factory=list)
    host: Path | None = None

    def create_run(self, **fields: Any) -> Any:
        return self.service.create(team_agent_id=TEAM_ID, user=self.user, **fields)

    def write(self, run: Any, name: str, content: str) -> None:
        self.workspace.write_text(f"{run_directory(run)}/{name}", content)

    def actions(self, run: Any) -> list[str]:
        return [
            event.action for event in self.services.timeline_repo.list_by_project(run.project_id)
        ]

    def add_task(self, run: Any, **fields: Any) -> Any:
        return self.service.create_task(run.run_id, user=self.user, **fields)


def manifest(members: list[tuple[str, str]], lead: str | None = None) -> str:
    payload: dict[str, Any] = {"members": [{"agent_id": a, "role": r} for a, r in members]}
    if lead is not None:
        payload["lead_agent_id"] = lead
    return json.dumps(payload)


DEFAULT_MEMBERS = [
    (TEAM_ID, "lead"),
    ("ag-arch", "architect"),
    ("ag-be", "backend"),
    ("ag-qa", "qa"),
]

FILLED_SPEC = (
    "# SPEC\n\n## 边界与禁止项\n\n| 边界 | 处置 |\n| --- | --- |\n| 不新增错误码 | 复用 |\n"
)


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
    workspace = FakeWorkspace({MANIFEST: manifest(DEFAULT_MEMBERS, lead=TEAM_ID), "other.txt": "x"})
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
    yield Harness(
        services=services,
        service=service,
        workspace=workspace,
        user=Actor(user),
        gateway=gateway,
    )


@pytest.fixture
def deliver_harness(harness: Harness, tmp_path: Path) -> Harness:
    """``harness`` + the run's **host** workspace — T-85B's deliver hook writes there.

    ``bind_runtime`` is the documented way to attach a runtime handle after boot, so the
    fixture reuses the whole harness instead of building a second service.
    """
    host = tmp_path / "host"
    host.mkdir()
    harness.service.bind_runtime(
        host_workspace_for=lambda agent_id: host if agent_id == TEAM_ID else None
    )
    harness.host = host
    return harness


def assert_code(err: Any, code: ErrorCode, *, status: int | None = None) -> None:
    assert err.value.code is code, (err.value.code, err.value.message)
    if status is not None:
        assert err.value.status == status


# ── pure helpers ─────────────────────────────────────────────────────────────


def test_run_directory_resolves_both_run_roots() -> None:
    host = SimpleNamespace(run_id="2026-01-02-030405", run_root="host_workspace")
    explicit = SimpleNamespace(run_id="2026-01-02-030405", run_root="explicit:/srv/runs")
    assert run_directory(host) == "team/2026-01-02-030405"  # type: ignore[arg-type]
    assert run_directory(explicit) == "/srv/runs/2026-01-02-030405"  # type: ignore[arg-type]


def test_path_in_scope_matches_prefixes_and_globs() -> None:
    scopes = ["tests/**", "src/octop/infra/db"]
    assert path_in_scope("tests/unit/db/test_x.py", scopes)
    assert path_in_scope("src/octop/infra/db/repos/team_runs.py", scopes)
    assert not path_in_scope("src/octop/infra/agents/teams/run_service.py", scopes)


# ── create: tier phases, roster trim (AM-1 ③), goal limits, conflict ─────────


def test_create_quick_tier_writes_four_phases_in_sequence_order(harness: Harness) -> None:
    run = harness.create_run(goal="做个看板", tier="快速档")

    assert run.tier == "quick"
    phases = harness.services.team_run_repo.list_phases(run.run_id)
    assert [p.phase for p in phases] == ["clarify", "implement", "test", "deliver"]
    assert [p.seq for p in phases] == [0, 1, 2, 3]
    assert [p.status for p in phases] == ["active", "pending", "pending", "pending"]
    assert TIMELINE_RUN_CREATED in harness.actions(run)


def test_create_trims_the_manifest_roster_and_keeps_skipped_roles_visible(
    harness: Harness,
) -> None:
    """AM-1 ③: cutting is the default behaviour — visible, and never a 409."""
    harness.workspace.files[MANIFEST] = manifest(
        [
            (TEAM_ID, "lead"),
            ("ag-arch", "architect"),
            ("ag-be", "backend"),
            ("ag-qa", "qa"),
            ("ag-fe", "frontend"),
        ],
        lead=TEAM_ID,
    )

    run = harness.create_run(goal="五个人的活", tier="quick")

    members = harness.services.team_run_repo.list_members(run.run_id)
    # Priority is lead → tier defaultRoles → manifest order; `kept` keeps manifest
    # order so the snapshot stays diffable.
    assert [m.role for m in members] == ["lead", "backend", "qa"]
    lead = harness.services.team_run_repo.lead_member(run.run_id)
    assert lead is not None and lead.agent_id == TEAM_ID
    first = harness.services.team_run_repo.get_phase(run.run_id, "clarify")
    assert first is not None
    assert first.gate_detail["skipped_roles"] == ["architect", "frontend"]


def test_create_with_an_explicit_over_cap_roster_is_a_member_limit(harness: Harness) -> None:
    """G9: only an explicit over-cap `roles?` is refused (quick caps at 3)."""
    with pytest.raises(OctopError) as err:
        harness.create_run(goal="x", tier="quick", roles=["pm", "backend", "qa", "reviewer"])
    assert_code(err, ErrorCode.TEAM_RUN_MEMBER_LIMIT, status=409)
    assert harness.services.project_repo.list_for_user(harness.user.id) == []


def test_create_refuses_empty_and_oversized_goals_without_leaving_anything(
    harness: Harness,
) -> None:
    with pytest.raises(OctopError) as empty:
        harness.create_run(goal="  \u3000 ")
    assert_code(empty, ErrorCode.TEAM_RUN_GOAL_EMPTY, status=400)

    with pytest.raises(OctopError) as long:
        harness.create_run(goal="目" * 4001)
    assert_code(long, ErrorCode.TEAM_RUN_GOAL_TOO_LONG, status=400)

    assert harness.services.project_repo.list_for_user(harness.user.id) == []
    assert harness.actions(SimpleNamespace(project_id="nope")) == []


def test_create_refuses_an_unknown_tier_instead_of_defaulting(harness: Harness) -> None:
    """G10: unrecognised tier ⇒ 400, never a silent fall back to standard."""
    with pytest.raises(OctopError) as err:
        harness.create_run(goal="x", tier="quickk")
    assert_code(err, ErrorCode.TEAM_TIER_INVALID, status=400)


def test_create_twice_in_the_same_second_is_a_run_conflict(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "octop.infra.agents.teams.run_service.run_id_for", lambda now=None: "2026-01-02-030405"
    )
    harness.create_run(goal="first")
    with pytest.raises(OctopError) as err:
        harness.create_run(goal="second")
    assert_code(err, ErrorCode.TEAM_RUN_CONFLICT, status=409)
    assert len(harness.services.team_run_repo.list()) == 1


def test_create_opens_a_run_scoped_room_session(harness: Harness) -> None:
    """SPEC B30 ①: the room session key is run-scoped, never a user DM key."""
    run = harness.create_run(goal="房间")
    assert run.room_thread_id is not None
    thread = harness.services.thread_repo.get(run.room_thread_id)
    assert thread is not None
    assert thread.session_key == f"{TEAM_ID}:dashboard:{run.run_id}:{ROOM_CHAT_TYPE}"
    assert not thread.session_key.endswith(":dm")


# ── advance: G2 phase order ──────────────────────────────────────────────────


def test_advance_rejects_a_phase_jump_and_allows_the_next_one(harness: Harness) -> None:
    run = harness.create_run(goal="跳阶", tier="quick")
    with pytest.raises(OctopError) as err:
        harness.service.advance(run.run_id, to_phase="deliver", user=harness.user)
    assert_code(err, ErrorCode.TEAM_RUN_PHASE_INVALID, status=409)
    assert err.value.details["allowed"] == ["implement"]

    harness.write(run, "SPEC.md", FILLED_SPEC)
    moved = harness.service.advance(run.run_id, to_phase="implement", user=harness.user)
    assert moved.phase == "implement"
    assert TIMELINE_RUN_PHASE_ADVANCED in harness.actions(run)


def test_advance_refuses_while_the_phase_artifact_is_missing(harness: Harness) -> None:
    """The artifact gate reads the *current* phase: clarify owns SPEC.md."""
    run = harness.create_run(goal="缺工件", tier="standard")
    with pytest.raises(OctopError) as err:
        harness.service.advance(run.run_id, to_phase="research", user=harness.user)
    assert_code(err, ErrorCode.TEAM_PHASE_GATE_FAILED, status=409)
    assert err.value.details["missing"] == ["SPEC.md"]

    harness.write(run, "SPEC.md", FILLED_SPEC)
    assert harness.service.advance(run.run_id, to_phase="research", user=harness.user).phase == (
        "research"
    )


# ── advance: G3 decision gate / G4 spec boundary ─────────────────────────────


def test_advance_refuses_implement_while_a_decision_is_pending(harness: Harness) -> None:
    run = harness.create_run(goal="等拍板", tier="quick")
    harness.write(run, "SPEC.md", FILLED_SPEC)
    decision = harness.service.raise_decision(
        run.run_id, kind="confirm", reason="scope", options=["go", "stop"]
    )

    with pytest.raises(OctopError) as err:
        harness.service.advance(run.run_id, to_phase="implement", user=harness.user)
    assert_code(err, ErrorCode.TEAM_DECISION_PENDING, status=409)
    assert err.value.details["decision_id"] == decision["id"]

    harness.service.decide(run.run_id, decision_id=decision["id"], choice="go", user=harness.user)
    assert harness.service.advance(run.run_id, to_phase="implement", user=harness.user).phase == (
        "implement"
    )


def test_a_pending_decision_blocks_every_advance_not_just_implement(harness: Harness) -> None:
    """Wiring proof for G3: the gate is reached through ``advance()``, not merely called.

    ``decision_gate`` is a pure function — asserting on it directly would only prove
    the function is right, not that the product path consults it. This drives the
    real entry point (``advance``) at a **non-implement** edge, where only the
    explicit wiring in ``advance()`` can refuse: ``advance_gate`` alone would let
    ``clarify -> research`` through.
    """
    run = harness.create_run(goal="待决", tier="standard")
    harness.service.raise_decision(
        run.run_id, kind="confirm", reason="scope", options=["go", "stop"]
    )
    harness.write(run, "SPEC.md", FILLED_SPEC)

    with pytest.raises(OctopError) as err:
        harness.service.advance(run.run_id, to_phase="research", user=harness.user)
    assert_code(err, ErrorCode.TEAM_DECISION_PENDING, status=409)
    assert harness.service.require_run(run.run_id).phase == "clarify"


def test_the_lazy_shared_services_entry_point_is_live(tmp_path: Path) -> None:
    """``SharedServices.team_run_service()`` must construct and work, not ImportError.

    The lazy import in ``db/services.py`` is the production wiring point; it is only
    "wired" if a run can actually be created through it. This goes through that
    method — never through a direct import of the class.

    ★ roster-guard batch: the roster is read from the manifest, so this entry point is
    only live when it gets the resolver boot passes in (``server.py`` hands over
    ``AgentManager.team_workspace_for``). This case supplies one and asserts the run
    really lands; the **unbound** call is refused by design and is pinned by
    ``test_the_unbound_lazy_entry_point_refuses_an_unresolvable_roster``.
    """
    paths = PathLayout(tmp_path / ".octop2")
    paths.ensure_root()
    db = SqlitePool(paths.db)
    run_migrations(db)
    services = build_shared_services(db=db, paths=paths, config=OctopConfig())
    user_id = services.user_repo.create(username="owner2", password_hash="h", role="user")
    services.agent_repo.create(agent_id=TEAM_ID, user_id=user_id, name="Team", kind="team")
    workspace = FakeWorkspace({MANIFEST: manifest([(TEAM_ID, "lead")])})

    service = services.team_run_service(
        workspace_for=lambda agent_id: workspace if agent_id == TEAM_ID else None
    )
    assert isinstance(service, TeamRunService)
    run = service.create(team_agent_id=TEAM_ID, user=Actor(user_id), goal="惰性接线", tier="quick")
    assert services.team_run_repo.get(run.run_id) is not None
    assert [p.phase for p in services.team_run_repo.list_phases(run.run_id)] == [
        "clarify",
        "implement",
        "test",
        "deliver",
    ]
    # Same seam, roster side: the manifest became a member row (A1's unit-side twin).
    assert len(services.team_run_repo.list_members(run.run_id)) == 1


def test_advance_fails_closed_when_the_spec_is_missing_entirely(harness: Harness) -> None:
    """G4 wiring, the fail-closed side: **no input is not evidence of a filled table**.

    ``spec_boundary_state`` is only a pure function until ``advance()`` reaches it.
    Two shapes of "missing" are driven through the real entry point: no ``SPEC.md``
    at all, and a ``SPEC.md`` without the 「边界与禁止项」 heading. Both must be
    refused — reading silence as consent is exactly what SPEC A2.3 forbids.
    """
    run = harness.create_run(goal="无规格", tier="quick")

    with pytest.raises(OctopError) as absent:
        harness.service.advance(run.run_id, to_phase="implement", user=harness.user)
    assert_code(absent, ErrorCode.TEAM_SPEC_BOUNDARY_EMPTY, status=409)
    assert absent.value.details["state"] == "missing"

    harness.write(run, "SPEC.md", "# SPEC\n\n没有边界章节\n")
    with pytest.raises(OctopError) as headingless:
        harness.service.advance(run.run_id, to_phase="implement", user=harness.user)
    assert_code(headingless, ErrorCode.TEAM_SPEC_BOUNDARY_EMPTY, status=409)

    # …and the filled table is the pass side of the very same call site.
    harness.write(run, "SPEC.md", FILLED_SPEC)
    assert harness.service.advance(run.run_id, to_phase="implement", user=harness.user).phase == (
        "implement"
    )


def test_advance_refuses_implement_with_an_empty_boundary_table(harness: Harness) -> None:
    """G4 fails closed: an empty table is refused, a filled one passes."""
    run = harness.create_run(goal="边界空", tier="quick")
    harness.write(
        run, "SPEC.md", "# SPEC\n\n## 边界与禁止项\n\n| a | b |\n| --- | --- |\n|  |  |\n"
    )
    with pytest.raises(OctopError) as err:
        harness.service.advance(run.run_id, to_phase="implement", user=harness.user)
    assert_code(err, ErrorCode.TEAM_SPEC_BOUNDARY_EMPTY, status=409)
    assert err.value.details["state"] == "empty"

    harness.write(run, "SPEC.md", FILLED_SPEC)
    assert harness.service.advance(run.run_id, to_phase="implement", user=harness.user)


# ── G5 dependency gate, G6 graph ─────────────────────────────────────────────


def test_claim_refuses_unmet_dependencies_and_allows_after_done(harness: Harness) -> None:
    run = harness.create_run(goal="依赖", tier="quick")
    first = harness.add_task(run, title="be-1", role="backend")
    second = harness.add_task(run, title="be-2", role="backend", depends_on=[first.id])

    with pytest.raises(OctopError) as err:
        harness.service.claim(run.run_id, second.id, role="backend", user=harness.user)
    assert_code(err, ErrorCode.TEAM_TASK_DEPS_UNMET, status=409)
    assert err.value.details["unmet"] == [first.id]
    assert harness.services.project_task_repo.get(second.id).attempt_id is None  # untouched

    harness.services.project_task_repo.update(first.id, status="done")
    claimed = harness.service.claim(run.run_id, second.id, role="backend", user=harness.user)
    assert claimed.claimed_by == "backend"
    assert TIMELINE_RUN_TASK_CLAIMED in harness.actions(run)


def test_a_failed_dependency_never_unlocks_the_dependent(harness: Harness) -> None:
    run = harness.create_run(goal="失败不解锁", tier="quick")
    first = harness.add_task(run, title="be-1", role="backend")
    second = harness.add_task(run, title="be-2", role="backend", depends_on=[first.id])
    harness.services.project_task_repo.update(first.id, status="blocked")

    with pytest.raises(OctopError) as err:
        harness.service.claim(run.run_id, second.id, role="backend", user=harness.user)
    assert_code(err, ErrorCode.TEAM_TASK_DEPS_UNMET, status=409)


def _member_rows(harness: Harness) -> int:
    """Rows in ``team_run_members`` — counted at the table, not through the service."""
    with harness.services.repos.db.connect() as conn:
        return int(tuple(conn.execute("SELECT COUNT(*) FROM team_run_members").fetchone())[0])


def test_a_usable_roster_lands_member_rows(harness: Harness) -> None:
    """The control for the two refusals below: the counter **can** move.

    Kept in its own test on purpose: a run id is a timestamp (``YYYY-MM-DD-HHMMSS``), so
    two ``create`` calls in the same second collide with ``TEAM_RUN_CONFLICT`` -- each
    test may build exactly one run.
    """
    run = harness.create_run(goal="基线", tier="quick")
    assert _member_rows(harness) > 0, f"expected member rows for {run.run_id!r}"


def test_a_member_without_a_role_is_refused_before_any_member_row(
    harness: Harness,
) -> None:
    """T-73 A layer: no configured role ⇒ refuse at the admission face, write no rows.

    The zero is meaningful because its sibling test proves the counter moves -- without
    that control, "0 rows" could equally mean "no run was ever built".
    """
    harness.workspace.files[MANIFEST] = manifest([(TEAM_ID, "lead"), ("ag-no-role", "")])
    with pytest.raises(OctopError) as err:
        harness.create_run(goal="缺角色", tier="quick")
    assert err.value.code is ErrorCode.TEAM_ROLE_UNKNOWN
    assert err.value.status == 400
    assert _member_rows(harness) == 0


def test_a_duplicate_roster_role_is_refused_before_any_member_row(
    harness: Harness,
) -> None:
    """S-2 (user-approved): the same role twice in one run ⇒ refused at admission.

    Same code as the B layer, because it is the same proposition ("that membership change
    is not allowed"); only the layer that notices differs.
    """
    harness.workspace.files[MANIFEST] = manifest([(TEAM_ID, "backend"), ("ag-two", "backend")])
    with pytest.raises(OctopError) as dup:
        harness.create_run(goal="重复角色", tier="quick")
    assert dup.value.code is ErrorCode.PROJECT_MEMBER_INVALID
    assert dup.value.status == 400
    assert _member_rows(harness) == 0


def test_a_duplicate_member_role_is_refused_by_the_service_not_by_the_database(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T-73 B layer: the constraint violation must surface as a code, never as a raw error.

    The table is ``UNIQUE(run_id, role)``, so a duplicate is caught by the *database*
    when it slips past the admission face. That must still be a mapped :class:`OctopError`
    (the wording-true code ``PROJECT_MEMBER_INVALID``, see the comment at the raise site),
    not an ``IntegrityError`` escaping as a 500. The integrity error is injected at the
    repository boundary on purpose: it proves the *conversion*, which is what the layer
    exists for -- asserting the DB's own behaviour would prove sqlite instead.
    """
    from sqlite3 import IntegrityError as SqliteIntegrityError

    def _boom(*args: Any, **kwargs: Any) -> Any:
        raise SqliteIntegrityError(
            "UNIQUE constraint failed: team_run_members.run_id, team_run_members.role"
        )

    monkeypatch.setattr(harness.service._runs, "add_member", _boom)
    with pytest.raises(OctopError) as err:
        harness.create_run(goal="重复角色", tier="quick")
    assert err.value.code is ErrorCode.PROJECT_MEMBER_INVALID
    assert err.value.status == 400
    assert not isinstance(err.value, SqliteIntegrityError)


def test_a_caller_chosen_task_id_round_trips_and_a_duplicate_never_reaches_the_db(
    harness: Harness,
) -> None:
    """The plan's `id?`, end to end through the service -- and *two* proofs for a duplicate.

    Round trip first: "accepted but replaced by a server-generated id" would look
    identical to success from the outside, and that silent swap is exactly the shape of
    the three earlier `role` / `depends_on` / `findings` cases. So the id is asserted on
    the returned row *and* on a fresh read.

    Duplicate: `TEAM_TASK_GRAPH_INVALID` alone is not evidence -- if the row reached the
    database first, the UNIQUE constraint would raise a different error after having
    written (and the HTTP layer would answer 5xx). Hence both probes:
    ``create`` must not be called at all, and the board must be unchanged. Asserting the
    code only would let "inserted, then rejected" pass as green.
    """
    run = harness.create_run(goal="自定义 id", tier="quick")
    chosen = "task-chosen-1"

    created = harness.add_task(run, title="命名任务", role="backend", task_id=chosen)
    assert created.id == chosen
    assert harness.services.project_task_repo.get(chosen) is not None

    calls: list[str] = []
    real_create = harness.services.project_task_repo.create

    def _probe(*args: Any, **kwargs: Any) -> Any:
        calls.append(str(kwargs.get("task_id")))
        return real_create(*args, **kwargs)

    harness.services.project_task_repo.create = _probe  # type: ignore[method-assign]
    try:
        with pytest.raises(OctopError) as err:
            harness.add_task(run, title="撞 id", role="backend", task_id=chosen)
    finally:
        harness.services.project_task_repo.create = real_create  # type: ignore[method-assign]

    assert err.value.code is ErrorCode.TEAM_TASK_GRAPH_INVALID
    assert err.value.details.get("code") == "duplicate-id"
    assert calls == [], "the refused task must never reach the repository"
    assert [row.id for row in harness.service.list_tasks(run.run_id)] == [chosen]


def test_omitting_the_id_keeps_the_allocated_one(harness: Harness) -> None:
    """Reverse control: no `id` ⇒ the server allocates, exactly as before."""
    run = harness.create_run(goal="默认 id", tier="quick")
    first = harness.add_task(run, title="A", role="backend")
    second = harness.add_task(run, title="B", role="backend")
    assert first.id and second.id and first.id != second.id


def test_create_task_rejects_a_missing_dependency(harness: Harness) -> None:
    """G6 runs on every task write, not only on reads."""
    run = harness.create_run(goal="图", tier="quick")
    with pytest.raises(OctopError) as err:
        harness.add_task(run, title="broken", depends_on=["nope"])
    assert_code(err, ErrorCode.TEAM_TASK_GRAPH_INVALID, status=409)
    assert err.value.details["code"] == "missing-id"
    assert harness.service.list_tasks(run.run_id) == []


# ── G7 rework loop limit ─────────────────────────────────────────────────────


def test_create_quality_task_past_the_round_budget_is_refused(harness: Harness) -> None:
    run = harness.create_run(goal="轮次", tier="quick")
    with pytest.raises(OctopError) as err:
        harness.service.create_quality_task(
            run.run_id, title="round 4", role="qa", round=run.max_review_rounds + 1
        )
    assert_code(err, ErrorCode.TEAM_REWORK_LOOP_LIMIT, status=409)
    assert harness.service.list_tasks(run.run_id) == []

    # Fail loud, not silent: an escalation decision unlocks the same call.
    harness.service.raise_decision(
        run.run_id, kind="escalate", reason="loop", options=["continue", "stop"]
    )
    created = harness.service.create_quality_task(
        run.run_id, title="round 4", role="qa", round=run.max_review_rounds + 1
    )
    assert created.kind == "quality"


# ── G8 stale attempt on report ───────────────────────────────────────────────


def test_report_refuses_a_superseded_attempt_and_accepts_the_current_one(
    harness: Harness,
) -> None:
    run = harness.create_run(goal="迟到写", tier="quick")
    task = harness.add_task(run, title="be", role="backend")
    claimed = harness.service.claim(run.run_id, task.id, role="backend", user=harness.user)
    assert claimed.attempt_id

    with pytest.raises(OctopError) as err:
        harness.service.report(
            run.run_id, task.id, attempt_id="att-from-last-round", verdict="pass"
        )
    assert_code(err, ErrorCode.TEAM_ATTEMPT_STALE, status=409)
    assert harness.services.project_task_repo.get(task.id).verdict is None

    # Transfer: a new claim mints a new token, and the new token is accepted.
    current = harness.services.project_task_repo.get(task.id)
    assert current is not None
    moved = harness.services.project_task_repo.claim(
        task.id, claimed_by="qa", expected_attempt_id=current.attempt_id
    )
    assert moved is not None and moved.attempt_id != claimed.attempt_id
    assert harness.service.report(run.run_id, task.id, attempt_id=moved.attempt_id, verdict="pass")


def test_a_lost_claim_race_is_mapped_to_a_claim_conflict(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """B26 wiring: the CAS returns ``None`` and this layer owns the 409.

    The repo-level half (two callers gating on the same attempt, one wins) is
    asserted where the CAS lives (``tests/unit/db/test_repo_projects.py``); what is
    asserted here is that ``advance``-side callers see ``TEAM_TASK_CLAIM_CONFLICT``
    rather than a silent success.
    """
    run = harness.create_run(goal="抢", tier="quick")
    task = harness.add_task(run, title="be", role="backend")
    monkeypatch.setattr(
        harness.service._tasks,
        "claim",
        lambda *a, **kw: None,  # simulate the loser
    )

    with pytest.raises(OctopError) as err:
        harness.service.claim(run.run_id, task.id, role="backend", user=harness.user)
    assert_code(err, ErrorCode.TEAM_TASK_CLAIM_CONFLICT, status=409)


# ── G11 scope audit on complete ──────────────────────────────────────────────


def test_complete_refuses_paths_outside_the_declared_scope(harness: Harness) -> None:
    run = harness.create_run(goal="越界", tier="quick")
    task = harness.add_task(run, title="写测试", role="qa", in_scope=["tests/**"])
    claimed = harness.service.claim(run.run_id, task.id, role="qa", user=harness.user)

    with pytest.raises(OctopError) as err:
        harness.service.complete(
            run.run_id,
            task.id,
            role="qa",
            attempt_id=claimed.attempt_id or "",
            changed_paths=["src/octop/secret.py"],
            user=harness.user,
        )
    assert_code(err, ErrorCode.TEAM_SCOPE_VIOLATION, status=409)
    assert err.value.details["outside"] == ["src/octop/secret.py"]
    assert harness.services.project_task_repo.get(task.id).changed_paths == ()

    done = harness.service.complete(
        run.run_id,
        task.id,
        role="qa",
        attempt_id=claimed.attempt_id or "",
        changed_paths=["tests/unit/db/test_x.py"],
        user=harness.user,
    )
    assert done.changed_paths == ("tests/unit/db/test_x.py",)
    assert done.status == "review"
    assert TIMELINE_RUN_TASK_COMPLETED in harness.actions(run)


# ── G12 verdict needs findings / G13 reviewer independence ───────────────────


def test_verdict_needs_findings_and_accepts_them(harness: Harness) -> None:
    run = harness.create_run(goal="判词", tier="quick")
    review = harness.add_task(run, title="审", role="reviewer", kind="review")
    claimed = harness.service.claim(run.run_id, review.id, role="reviewer", user=harness.user)

    with pytest.raises(OctopError) as err:
        harness.service.verdict(
            run.run_id,
            review.id,
            role="reviewer",
            attempt_id=claimed.attempt_id or "",
            verdict="needs_revision",
            user=harness.user,
        )
    assert_code(err, ErrorCode.TEAM_VERDICT_FINDINGS_REQUIRED, status=409)

    updated = harness.service.verdict(
        run.run_id,
        review.id,
        role="reviewer",
        attempt_id=claimed.attempt_id or "",
        verdict="needs_revision",
        findings=[{"title": "FIND-1 缺少回归", "severity": "high"}],
        user=harness.user,
    )
    assert updated.verdict == "needs_revision"
    findings = harness.services.task_finding_repo.list_by_task(review.id)
    assert [f.title for f in findings] == ["FIND-1 缺少回归"]


def test_reviewer_cannot_pass_its_own_implementation(harness: Harness) -> None:
    """G13: `review.attempt_id` is cross-checked against the last implementer."""
    run = harness.create_run(goal="自审", tier="quick")
    work = harness.add_task(run, title="实现", role="backend")
    harness.service.claim(run.run_id, work.id, role="backend", user=harness.user)
    review = harness.add_task(run, title="审", role="backend", kind="review")
    claimed = harness.service.claim(run.run_id, review.id, role="backend", user=harness.user)

    with pytest.raises(OctopError) as err:
        harness.service.verdict(
            run.run_id,
            review.id,
            role="backend",
            attempt_id=claimed.attempt_id or "",
            verdict="pass",
            user=harness.user,
        )
    assert_code(err, ErrorCode.TEAM_REVIEW_SELF_AUDIT, status=409)

    # An independent reviewer needs the attempt *itself* to be theirs: the review
    # task is transferred, which mints a new attempt under the new role.
    transferred = harness.services.project_task_repo.claim(
        review.id, claimed_by="reviewer", expected_attempt_id=claimed.attempt_id
    )
    assert transferred is not None and transferred.attempt_id != claimed.attempt_id
    passed = harness.service.verdict(
        run.run_id,
        review.id,
        role="reviewer",
        attempt_id=transferred.attempt_id or "",
        verdict="pass",
        user=harness.user,
    )
    assert passed.verdict == "pass"


# ── G14 artifact ownership + revision CAS ────────────────────────────────────


def test_write_artifact_creates_then_guards_ownership_and_revision(harness: Harness) -> None:
    run = harness.create_run(goal="工件", tier="quick")

    created = harness.service.write_artifact(
        run.run_id, name="SPEC.md", content="# SPEC v1", revision="", role="pm", user=harness.user
    )
    assert created["revision"] == harness.service.read_artifact(run.run_id, "SPEC.md")[1]

    # Ownership: backend may not overwrite the pm-owned SPEC.md.
    with pytest.raises(OctopError) as denied:
        harness.service.write_artifact(
            run.run_id,
            name="SPEC.md",
            content="# hijack",
            revision=created["revision"],
            role="backend",
            user=harness.user,
        )
    assert_code(denied, ErrorCode.TEAM_ARTIFACT_OWNERSHIP_DENIED, status=409)
    assert harness.workspace.files[f"{run_directory(run)}/SPEC.md"] == "# SPEC v1"

    # Runtime-only files (`owners == ()`): creation is the skeleton's business, but
    # no role may overwrite one that already exists.
    harness.write(run, "STATE.json", "{}")
    with pytest.raises(OctopError) as runtime_only:
        harness.service.write_artifact(
            run.run_id, name="STATE.json", content="{}", revision="", role="pm", user=harness.user
        )
    assert_code(runtime_only, ErrorCode.TEAM_ARTIFACT_OWNERSHIP_DENIED, status=409)

    # Revision CAS: the pm may overwrite with the revision it read, not a stale one.
    with pytest.raises(OctopError) as stale:
        harness.service.write_artifact(
            run.run_id,
            name="SPEC.md",
            content="# SPEC v3",
            revision="deadbeefdeadbeef",
            role="pm",
            user=harness.user,
        )
    assert_code(stale, ErrorCode.TEAM_ARTIFACT_STALE, status=409)

    second = harness.service.write_artifact(
        run.run_id,
        name="SPEC.md",
        content="# SPEC v2",
        revision=created["revision"],
        role="pm",
        user=harness.user,
    )
    assert second["revision"] != created["revision"]
    assert TIMELINE_RUN_ARTIFACT_WRITTEN in harness.actions(run)


def test_write_artifact_materialises_the_workflow_index_row(harness: Harness) -> None:
    """T-45: writing a file also writes its `kind='workflow'` row — the fields get values."""
    run = harness.create_run(goal="索引行", tier="quick")
    first = harness.service.write_artifact(
        run.run_id, name="SPEC.md", content="# v1", revision="", role="pm", user=harness.user
    )

    rows = harness.services.project_artifact_repo.list_workflow(project_id=run.project_id)
    assert [row.name for row in rows] == ["SPEC.md"]
    row = rows[0]
    assert row.kind == "workflow"
    assert row.owner_role == "pm"  # from ARTIFACT_OWNERS, not derived in the repo
    assert row.phase == run.phase
    assert (row.version, row.hash) == (1, first["hash"])
    assert row.artifact_id == first["artifact_id"]  # internal handoff for the KB archiver

    second = harness.service.write_artifact(
        run.run_id,
        name="SPEC.md",
        content="# v2",
        revision=first["revision"],
        role="pm",
        user=harness.user,
    )
    updated = harness.services.project_artifact_repo.get_workflow(
        project_id=run.project_id, name="SPEC.md"
    )
    assert updated is not None
    assert updated.artifact_id == row.artifact_id  # same row, bumped in place
    assert updated.version == 2  # the row's rewrite counter...
    assert updated.hash == second["hash"] != first["hash"]  # ...not the body's revision
    assert second["revision"] != first["revision"]


def test_a_failed_archive_is_recorded_and_does_not_undo_the_artifact(
    harness: Harness,
) -> None:
    """The reference hop may fail; the artifact stays, and the run log says so.

    Silence would read as "nothing was archived" when the fact is "archiving failed",
    so the failure is both raised and written to the timeline — and the primary state
    (file + index row) is deliberately not rolled back.
    """
    run = harness.create_run(goal="归档失败", tier="quick")
    harness.services.project_repo.set_kb_id(run.project_id, "kb-1")

    class _Boom:
        def write_document(self, **kwargs: Any) -> str:
            raise RuntimeError("kb down")

    harness.service.bind_runtime(
        kb_archiver_factory=lambda kb_id, artifact_id, *, actor_user_id: _Boom()
    )

    with pytest.raises(RuntimeError, match="kb down"):
        harness.service.write_artifact(
            run.run_id, name="SPEC.md", content="# v1", revision="", role="pm", user=harness.user
        )

    # Primary state survives: the file and its index row are still there.
    assert harness.workspace.files[f"{run_directory(run)}/SPEC.md"] == "# v1"
    row = harness.services.project_artifact_repo.get_workflow(
        project_id=run.project_id, name="SPEC.md"
    )
    assert row is not None and row.kb_document_id is None
    # Both events are in the log: the write happened, the archive did not.
    actions = harness.actions(run)
    assert TIMELINE_RUN_ARTIFACT_WRITTEN in actions
    assert TIMELINE_RUN_ARCHIVE_FAILED in actions


def test_unlisted_artifacts_are_not_restricted(harness: Harness) -> None:
    """The ownership table lists *some* files; the rest (TASK.md, RUN.log.md) are free."""
    run = harness.create_run(goal="自由", tier="quick")
    written = harness.service.write_artifact(
        run.run_id, name="TASK.md", content="目标", revision="", role="backend", user=harness.user
    )
    assert written["name"] == "TASK.md"


# ── G15 decision gate ────────────────────────────────────────────────────────


def test_decide_is_idempotent_and_rejects_an_unknown_option(harness: Harness) -> None:
    run = harness.create_run(goal="决策", tier="quick")
    decision = harness.service.raise_decision(
        run.run_id, kind="confirm", reason="scope", options=["go", "stop"]
    )

    with pytest.raises(OctopError) as bad:
        harness.service.decide(
            run.run_id, decision_id=decision["id"], choice="maybe", user=harness.user
        )
    assert_code(bad, ErrorCode.TEAM_DECISION_OPTION_INVALID, status=400)

    resolved = harness.service.decide(
        run.run_id, decision_id=decision["id"], choice="go", note="ok", user=harness.user
    )
    assert resolved["status"] == "resolved"
    assert harness.service.require_run(run.run_id).status == "running"
    assert TIMELINE_RUN_DECISION_RESOLVED in harness.actions(run)

    with pytest.raises(OctopError) as twice:
        harness.service.decide(
            run.run_id, decision_id=decision["id"], choice="go", user=harness.user
        )
    assert_code(twice, ErrorCode.TEAM_DECISION_NOT_PENDING, status=409)


# ── G16 finding reopened ⇒ block + escalate ──────────────────────────────────


def test_a_reopened_finding_blocks_advance_and_raises_an_escalation(
    harness: Harness,
) -> None:
    run = harness.create_run(goal="重开", tier="quick")
    harness.write(run, "SPEC.md", FILLED_SPEC)
    harness.service.advance(run.run_id, to_phase="implement", user=harness.user)

    review = harness.add_task(run, title="审", role="reviewer", kind="review", round=1)
    harness.services.task_finding_repo.insert(
        finding_id="f-1",
        task_id=review.id,
        run_id=run.run_id,
        round=1,
        severity="high",
        title="FIND-24 标题",
    )
    harness.services.project_task_repo.report(review.id, attempt_id="", verdict="needs_revision")
    harness.services.project_task_repo.update(review.id, round=2)
    harness.services.task_finding_repo.insert(
        finding_id="f-2",
        task_id=review.id,
        run_id=run.run_id,
        round=2,
        severity="high",
        title="FIND-24 标题",
    )
    harness.services.project_task_repo.report(review.id, attempt_id="", verdict="needs_revision")

    with pytest.raises(OctopError) as err:
        harness.service.advance(run.run_id, to_phase="test", user=harness.user)
    assert_code(err, ErrorCode.TEAM_FINDING_REOPENED, status=409)

    pending = harness.services.team_run_repo.get_pending_decision(run.run_id)
    assert pending is not None and pending["kind"] == "escalate"
    assert TIMELINE_RUN_DECISION_RAISED in harness.actions(run)
    assert harness.service.require_run(run.run_id).status == "awaiting_decision"


# ── dispatch: the two 必答 C channels ────────────────────────────────────────


async def test_dispatch_persist_runs_the_room_turn_and_one_shot_does_not(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """persist → ``ask_agent`` (room turn); one-shot → ``task`` (host subgraph)."""
    calls: list[dict[str, Any]] = []

    async def fake_dispatch(**kwargs: Any) -> str:
        calls.append(kwargs)
        return "thr-dispatch"

    monkeypatch.setattr("octop.infra.projects.dispatch.run_dispatch_turn", fake_dispatch)
    harness.service.bind_runtime(agent_manager=SimpleNamespace())  # type: ignore[arg-type]
    # Run ids are second-precision by design (SPEC R22), so two runs in one test
    # second would be the duplicate-`runId` conflict rather than two runs.
    ids = iter(["2026-01-01-000001", "2026-01-01-000002", "2026-01-01-000003"])
    monkeypatch.setattr(
        "octop.infra.agents.teams.run_service.run_id_for", lambda now=None: next(ids)
    )

    persist = harness.create_run(goal="p", tier="quick", mode="persist")
    p_task = harness.add_task(persist, title="干活", role="backend")
    outcome = await harness.service.dispatch_task(
        persist.run_id, p_task.id, role="backend", user=harness.user
    )
    assert outcome.channel == "ask_agent"
    assert outcome.thread_id == "thr-dispatch"
    assert len(calls) == 1
    # The board stores the role; the turn runs the agent `team_run_members` resolves.
    assert calls[0]["task"].assignee_id == "ag-be"
    # SPEC B30 ①: the run's dispatch key is run-scoped and never a DM key.
    assert calls[0]["session_key"] == f"ag-be:dashboard:{persist.run_id}:{ROOM_CHAT_TYPE}"
    assert not calls[0]["session_key"].endswith(":dm")

    one_shot = harness.create_run(goal="o", tier="quick", mode="one-shot")
    o_task = harness.add_task(one_shot, title="子代理", role="backend")
    outcome = await harness.service.dispatch_task(
        one_shot.run_id, o_task.id, role="backend", user=harness.user
    )
    assert outcome.channel == "task"
    assert outcome.thread_id is None
    assert len(calls) == 1  # the one-shot branch never touches the room turn
    assert harness.actions(one_shot).count("run.dispatched") == 1


async def test_persist_dispatch_without_a_runtime_is_not_running(harness: Harness) -> None:
    run = harness.create_run(goal="无运行时", tier="quick", mode="persist")
    task = harness.add_task(run, title="干活", role="backend")
    with pytest.raises(OctopError) as err:
        await harness.service.dispatch_task(run.run_id, task.id, role="backend", user=harness.user)
    assert_code(err, ErrorCode.AGENT_NOT_RUNNING, status=409)


# ── lifecycle + timeline discipline ──────────────────────────────────────────


def test_cancel_is_terminal_and_resume_refuses_a_terminal_run(harness: Harness) -> None:
    run = harness.create_run(goal="取消", tier="quick")
    cancelled = harness.service.cancel(run.run_id, user=harness.user)
    assert cancelled.status == "cancelled"

    with pytest.raises(OctopError) as err:
        harness.service.resume(run.run_id, user=harness.user)
    assert_code(err, ErrorCode.TEAM_RUN_TERMINAL, status=409)
    with pytest.raises(OctopError) as advance:
        harness.service.advance(run.run_id, to_phase="implement", user=harness.user)
    assert_code(advance, ErrorCode.TEAM_RUN_TERMINAL, status=409)


def test_every_task_state_write_appends_a_timeline_event(harness: Harness) -> None:
    run = harness.create_run(goal="时间线", tier="quick")
    task = harness.add_task(run, title="be", role="backend")
    claimed = harness.service.claim(run.run_id, task.id, role="backend", user=harness.user)
    harness.service.complete(
        run.run_id,
        task.id,
        role="backend",
        attempt_id=claimed.attempt_id or "",
        changed_paths=[],
        user=harness.user,
    )

    actions = harness.actions(run)
    for expected in (
        TIMELINE_RUN_CREATED,
        TIMELINE_RUN_TASK_CREATED,
        TIMELINE_RUN_TASK_CLAIMED,
        TIMELINE_RUN_TASK_COMPLETED,
    ):
        assert expected in actions, (expected, actions)
    assert actions.count(TIMELINE_RUN_CREATED) == 1


def test_run_root_for_resolves_both_forms_and_refuses_unknown_shapes() -> None:
    """T-61: the root the gate is given, from the one function wiring and tests share.

    `run_root_for` must hand `run_scoped_target` the root that has `<runId>/<file>`
    directly under it, accept relative **and** absolute targets, and return `None`
    for a `run_root` value it does not recognise (never fall back to the host root —
    that is what keeps the gate from becoming a channel to a caller-chosen path).
    """
    ws = "/tmp/ws-t61"
    runs = {"2026-01-02-030405": "host_workspace", "2026-01-02-030406": "explicit:/srv/runs"}

    def run_root_of(run_id: str) -> str | None:
        return runs.get(run_id)

    # host: both forms resolve to <ws>/team
    assert (
        run_root_for("team/2026-01-02-030405/STATE.json", workspace_dir=ws, run_root_of=run_root_of)
        == f"{ws}/team"
    )
    assert (
        run_root_for(
            f"{ws}/team/2026-01-02-030405/STATE.json", workspace_dir=ws, run_root_of=run_root_of
        )
        == f"{ws}/team"
    )
    # explicit: the declared absolute root, reached through the DB-confirmed id
    assert (
        run_root_for(
            "/srv/runs/2026-01-02-030406/SPEC.md", workspace_dir=ws, run_root_of=run_root_of
        )
        == "/srv/runs"
    )
    # unknown run id / non-team directory / deeper nesting / empty ⇒ None (fail-open)
    assert (
        run_root_for("team/2099-01-01-000000/X.md", workspace_dir=ws, run_root_of=run_root_of)
        is None
    )
    assert run_root_for("docs/readme.md", workspace_dir=ws, run_root_of=run_root_of) is None
    assert (
        run_root_for(
            "team/2026-01-02-030405/sub/SPEC.md", workspace_dir=ws, run_root_of=run_root_of
        )
        is None
    )
    assert run_root_for("", workspace_dir=ws, run_root_of=run_root_of) is None


def test_the_wiring_body_has_no_local_root_derivation() -> None:
    """**Absence**, not presence: what the fix removed must not creep back in.

    Asserting that ``run_root_for(`` appears in the source only proves a call exists --
    a second, local derivation could be re-added right next to it and that assertion
    would still pass. So the wiring's function body is read as an AST and checked for
    the very shapes the fix deleted (``is_absolute`` / ``relative_to`` / ``normpath`` /
    ``os.path.join`` / ``resolve``), plus "exactly one top-level return, and it is the
    shared call". Assertions about something *not* happening have to name what would
    make it happen; the caller-count gate (T-68) is the same shape.
    """
    import ast

    from octop.infra.agents import manager as manager_module

    tree = ast.parse(Path(manager_module.__file__).read_text())
    fn = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_team_root_for"
    )
    banned = {"is_absolute", "relative_to", "normpath", "join", "abspath", "resolve"}
    attrs = {node.attr for node in ast.walk(fn) if isinstance(node, ast.Attribute)}
    assert not (banned & attrs), f"local root derivation is back: {sorted(banned & attrs)}"
    returns = [node for node in fn.body if isinstance(node, ast.Return)]
    assert len(returns) == 1, "the wiring must have exactly one exit"
    value = returns[0].value
    assert isinstance(value, ast.Call), "the only exit must be the shared call"
    assert getattr(value.func, "id", "") == "run_root_for"


def test_the_gate_refuses_both_path_forms_and_allows_a_non_team_directory() -> None:
    """T-61 acceptance ②③④, driven through the gate's own decision chain.

    The chain is exactly the middleware's (``run_root_for`` -> ``run_scoped_target`` ->
    ``owner_violation``), so a change in any link shows up here. **Absolute comes
    first**: before the fix, the wiring handed over the workspace directory, so the
    absolute form matched nothing and was *allowed* -- that is the direct evidence that
    this card changed production behaviour.
    """
    ws = "/tmp/ws-t61"
    declared = {"R1": "host_workspace", "R2": "explicit:/srv/runs"}

    def denial(raw_path: str, *, role: str = "pm", exists: bool = True) -> str | None:
        """Driven through the **middleware entry**, not the primitives.

        The lesson of this card is "between the layers": a green `run_root_for` proves
        nothing about the gate. So the middleware is constructed exactly as the manager
        constructs it and asked for its verdict.
        """
        from functools import partial

        from langgraph.prebuilt.tool_node import ToolCallRequest

        from octop.infra.agents.middleware.team_artifact_ownership import (
            OwnershipGateDeps,
            TeamArtifactOwnershipMiddleware,
        )

        gate = TeamArtifactOwnershipMiddleware(
            deps=OwnershipGateDeps(
                team_root_for=partial(
                    run_root_for,
                    workspace_dir=ws,
                    run_root_of=lambda run_id: declared.get(run_id),
                ),
                run_status_for=lambda run_id: "running",
                role_for=lambda run_id: role,
                exists_for=lambda path: exists,
            )
        )
        request = ToolCallRequest(
            tool_call={"name": "write_file", "args": {"file_path": raw_path}, "id": "c1"},
            tool=None,
            state={},
            runtime=None,
        )
        return gate._violation(request)

    # ③ absolute, runtime-only file in a host run ⇒ refused (was allowed before the fix)
    assert denial(f"{ws}/team/R1/STATE.json") is not None
    # ② the same file, relative ⇒ refused. The root was already right; what was missing
    # is that the *path* handed to `run_scoped_target` must be in the same form as the
    # root, so the middleware resolves it lexically against the root's parent first.
    assert denial("team/R1/STATE.json") is not None
    assert denial("./team/R1/STATE.json") is not None

    # explicit runs are covered too (they used to bypass the gate entirely)
    assert denial("/srv/runs/R2/ROSTER.json") is not None
    # ④ a non-team directory, both forms ⇒ allowed
    assert denial("docs/readme.md") is None
    assert denial(f"{ws}/docs/readme.md") is None


def test_the_tool_channel_wiring_calls_the_shared_root_function() -> None:
    """The wiring half of T-61: `manager.py` must resolve the root through the shared
    function, and must no longer carry the local "absolute only" rule.

    Asserted against the module's own source on purpose -- the point of the fix is
    *which function the wiring calls*, and a source assertion is what makes a revert
    (back to a locally derived root) fail loudly.
    """
    from octop.infra.agents import manager as manager_module

    source = Path(manager_module.__file__).read_text()
    assert "run_root_for(" in source
    assert "if not target.is_absolute():" not in source
    assert "_run_root = Path(str(harness_workspace))" not in source
    # and the shared function itself is still where the docstring says it lives
    assert "def run_root_for(" in Path(run_root_for.__code__.co_filename).read_text()


def test_run_root_for_refuses_a_run_root_it_does_not_recognise() -> None:
    """The `run_root` column is caller-supplied: only its two legal shapes are trusted."""
    ws = "/tmp/ws-t61"

    def declared(value: str):
        return lambda run_id: value

    # host default: empty and the literal are both the host branch
    assert run_root_for("team/R1/X.md", workspace_dir=ws, run_root_of=declared("")) == f"{ws}/team"
    assert (
        run_root_for("team/R1/X.md", workspace_dir=ws, run_root_of=declared("host_workspace"))
        == f"{ws}/team"
    )
    # unknown shapes ⇒ None, never the host branch

    assert (
        run_root_for("team/R1/X.md", workspace_dir=ws, run_root_of=declared("weird_root")) is None
    )
    assert (
        run_root_for("team/R1/X.md", workspace_dir=ws, run_root_of=declared("explicit:rel/path"))
        is None
    )
    assert (
        run_root_for("team/R1/X.md", workspace_dir=ws, run_root_of=declared("explicit:/a/../b"))
        is None
    )
    # a legal explicit root still only matches its own tree
    explicit = declared("explicit:/srv/runs")
    assert run_root_for("/srv/runs/R1/X.md", workspace_dir=ws, run_root_of=explicit) == "/srv/runs"
    assert run_root_for("/elsewhere/R1/X.md", workspace_dir=ws, run_root_of=explicit) is None


def test_run_id_is_the_directory_name_shape() -> None:
    """SPEC R22: the id is `<YYYY-MM-DD-HHMMSS>` — no suffix, no colon."""
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}-\d{6}", run_id_for())
    assert "reviewer" in ROLES


# ── T-85B: the deliver learnings hook (S-1 / S-2 / S-3) ──────────────────────


def _advance_to_test(harness: Harness) -> Any:
    """Walk a quick run to ``test`` (the phase before ``deliver``) with its artifacts."""
    run = harness.create_run(goal="沉淀经验", tier="quick")
    harness.write(run, "SPEC.md", FILLED_SPEC)
    harness.write(run, "TASKS.json", '{"tasks": []}')
    harness.write(run, "TEST.md", "# TEST\n")
    for phase in ("implement", "test"):
        harness.service.advance(run.run_id, to_phase=phase, user=harness.user)
    return harness.service.require_run(run.run_id)


def _count_distill(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Count ``distill_and_append`` calls (S-2's counting entity) around the real one."""
    calls: list[dict[str, Any]] = []
    real = run_service_module.distill_and_append

    def counting(**kwargs: Any) -> Any:
        calls.append(kwargs)
        return real(**kwargs)

    monkeypatch.setattr(run_service_module, "distill_and_append", counting)
    return calls


def _sha256(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else "missing"


def _write_traces(harness: Harness, run: Any, *, run_log: str) -> Path:
    """Structured traces live in the **host** run directory (the 丙 source)."""
    run_dir = Path(harness.host) / run_directory(run)
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "RUN.log.md").write_text(run_log, encoding="utf-8")
    return run_dir


def test_a_true_phase_change_distills_once_and_a_real_candidate_lands_on_disk(
    deliver_harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S-2 counting entity == 1, and the chain is **not** idle: a real candidate is written."""
    harness = deliver_harness
    run = _advance_to_test(harness)
    _write_traces(harness, run, run_log="- G-1 团队层写入点恰好 1 处\n")
    calls = _count_distill(monkeypatch)
    target = L.project_learnings_path(Path(harness.host), run.project_id)
    assert not target.exists()

    moved = harness.service.advance(run.run_id, to_phase="deliver", user=harness.user)

    assert moved.phase == "deliver"
    assert len(calls) == 1, "S-2：每 run distill_and_append 调用次数 == 1"
    written = target.read_text(encoding="utf-8")
    assert "- [G-1] - 团队层写入点恰好 1 处" in written


def test_a_repeated_deliver_writes_nothing_and_calls_the_distiller_zero_times(
    deliver_harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The phase is already ``deliver`` ⇒ count 0 and the target file is byte-identical."""
    harness = deliver_harness
    run = _advance_to_test(harness)
    _write_traces(harness, run, run_log="- G-1 团队层写入点恰好 1 处\n")
    calls = _count_distill(monkeypatch)
    harness.service.advance(run.run_id, to_phase="deliver", user=harness.user)
    target = L.project_learnings_path(Path(harness.host), run.project_id)
    before = _sha256(target)
    calls.clear()

    with pytest.raises(OctopError) as err:
        harness.service.advance(run.run_id, to_phase="deliver", user=harness.user)

    assert_code(err, ErrorCode.TEAM_RUN_PHASE_INVALID, status=409)
    assert calls == [], "相位已是 deliver ⇒ 调用计数 == 0"
    assert _sha256(target) == before
    assert harness.service.require_run(run.run_id).phase == "deliver"


def test_terminal_and_invalid_phases_are_refused_without_writing(
    deliver_harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Existing codes only (no new ErrorCode) and **zero** writes (sha256 unchanged)."""
    harness = deliver_harness
    run = _advance_to_test(harness)
    _write_traces(harness, run, run_log="- G-1 团队层写入点恰好 1 处\n")
    calls = _count_distill(monkeypatch)
    target = L.project_learnings_path(Path(harness.host), run.project_id)

    with pytest.raises(OctopError) as invalid:
        harness.service.advance(run.run_id, to_phase="deliver-typo", user=harness.user)
    assert_code(invalid, ErrorCode.TEAM_RUN_PHASE_INVALID, status=409)

    harness.services.team_run_repo.update_status(run.run_id, "cancelled")
    with pytest.raises(OctopError) as terminal:
        harness.service.advance(run.run_id, to_phase="deliver", user=harness.user)
    assert_code(terminal, ErrorCode.TEAM_RUN_TERMINAL, status=409)

    assert calls == []
    assert _sha256(target) == "missing"


def test_the_deliver_hook_holds_low_confidence_and_conflicting_candidates(
    deliver_harness: Harness, caplog: pytest.LogCaptureFixture
) -> None:
    """C-2/C-3 through the production entry: log event + ``pending-decision`` + no write."""
    harness = deliver_harness
    first, second = "[D-1] 先跑测试。", "[D-1] 先跑测试!"
    harness.service.bind_runtime(
        learnings_distill=lambda _material: f"无标签的一行\n{first}\n{second}"
    )
    run = _advance_to_test(harness)
    target = L.project_learnings_path(Path(harness.host), run.project_id)

    with caplog.at_level(logging.WARNING, logger="octop.infra.agents.teams.learnings"):
        harness.service.advance(run.run_id, to_phase="deliver", user=harness.user)

    assert L.LOW_CONFIDENCE_EVENT in caplog.text
    assert L.norm_learning("无标签的一行") in caplog.text
    assert f"pending-decision:{L.norm_learning(first)}" in caplog.text
    assert not target.exists(), "低置信 + 冲突 ⇒ 一个字节都不写"


def test_an_unbound_host_workspace_skips_the_hook(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No host write face ⇒ skip (never guess a path): the phase still moves, count stays 0.

    "Unbound" here is the *whole* runtime being unbound (no registry either) — the
    pre-T-85B semantics, which must not change.
    """
    run = _advance_to_test(harness)
    calls = _count_distill(monkeypatch)

    moved = harness.service.advance(run.run_id, to_phase="deliver", user=harness.user)

    assert moved.phase == "deliver"
    assert calls == []


def test_the_production_binding_reaches_the_host_write_face_without_a_seat(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T-85B on the **production composition path**: only ``bind_runtime(agent_manager=…)``.

    ``server.py`` binds the real registry and never passes ``host_workspace_for``, so
    injection-seat-only coverage (``deliver_harness``) proved nothing about production:
    the write face has to be reachable from the bound registry, and a real candidate has
    to land on disk through ``distill_and_append``. The `agent_manager` here is the real
    ``AgentManager`` (the class the server binds), not a hand-rolled host-path stub, and
    nothing stubs either accessor — so this case fails if the fallback is removed.
    """
    manager = AgentManager(repos=harness.services.repos, paths=harness.services.paths)
    harness.service.bind_runtime(agent_manager=manager)
    host = manager.resolve_workspace_dir(TEAM_ID, persist_if_missing=False)
    run = _advance_to_test(harness)
    run_dir = host / run_directory(run)
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "RUN.log.md").write_text("- G-1 团队层写入点恰好 1 处\n", encoding="utf-8")
    calls = _count_distill(monkeypatch)
    target = L.project_learnings_path(host, run.project_id)
    assert harness.service._learnings_home(run) == host  # noqa: SLF001
    assert not target.exists()

    moved = harness.service.advance(run.run_id, to_phase="deliver", user=harness.user)

    assert moved.phase == "deliver"
    assert len(calls) == 1, "S-2：每 run distill_and_append 调用次数 == 1"
    assert calls[0]["host_workspace"] == host, "写面必须来自绑定的注册表，而非注入座"
    written = target.read_text(encoding="utf-8")
    assert "- [G-1] - 团队层写入点恰好 1 处" in written, "候选必须真的落盘"


# ── empty-roster guard (A2 / A3 / A4): refuse before the first write ─────────
# 判据 = ``len(trim.kept) == 0``（DECISIONS D3）；``details.reason`` 三口径见 D7。
# 下面三条都走 ``SharedServices.team_run_service()`` —— 生产缝本身，不直接 new。

#: A3 判据覆盖的四张表（SPEC A3 逐字：projects / team_runs / threads / team_run_members）。
_GUARDED_TABLES = ("projects", "team_runs", "threads", "team_run_members")


def _lazy_services(tmp_path: Path, *, name: str) -> tuple[Any, int]:
    """一套真实控制面 + 一个 ``kind=team`` 的 agent 行；每个用例独占一份。"""
    paths = PathLayout(tmp_path / name)
    paths.ensure_root()
    db = SqlitePool(paths.db)
    run_migrations(db)
    services = build_shared_services(db=db, paths=paths, config=OctopConfig())
    user_id = services.user_repo.create(username="owner-lazy", password_hash="h", role="user")
    services.agent_repo.create(agent_id=TEAM_ID, user_id=user_id, name="Team", kind="team")
    return services, user_id


def _table_counts(services: Any) -> dict[str, int]:
    """四表行数，**直查表**（不经 service）—— 「拒绝即零写入」的判据。

    经过 service 的计数会把「没查」当成「没有」；A3 要求的是表里真的没有行。
    """
    sql = (
        "SELECT (SELECT COUNT(*) FROM projects), (SELECT COUNT(*) FROM team_runs),"
        " (SELECT COUNT(*) FROM threads), (SELECT COUNT(*) FROM team_run_members)"
    )
    with services.repos.db.connect() as conn:
        row = tuple(conn.execute(sql).fetchone())
    return dict(zip(_GUARDED_TABLES, (int(value) for value in row), strict=True))


def _workspace_accessor(workspace: FakeWorkspace) -> Any:
    return lambda agent_id: workspace if agent_id == TEAM_ID else None


def test_the_unbound_lazy_entry_point_refuses_an_unresolvable_roster(tmp_path: Path) -> None:
    """A2/A3 构造 ①（``workspace_for=None``）：解析链断 ⇒ 422，四表零新增。

    走的是生产缝本身（``SharedServices.team_run_service()``，不传 ``workspace_for``）
    ⇒ 访问器为 ``None`` ⇒ ``details.reason == "manifest-unavailable"``。**拒绝也可以
    是对的**，因为它的负向对照在 ``test_the_lazy_shared_services_entry_point_is_live``：
    同一条缝 + 一个可解析的访问器就建得出 run，所以这里不是「这条缝坏了」。
    """
    services, user_id = _lazy_services(tmp_path, name=".octop-unbound")
    service = services.team_run_service()
    assert isinstance(service, TeamRunService)
    before = _table_counts(services)
    assert before == dict.fromkeys(_GUARDED_TABLES, 0)  # 空库：零是「真的零」的前提

    with pytest.raises(OctopError) as err:
        service.create(team_agent_id=TEAM_ID, user=Actor(user_id), goal="未接线", tier="quick")

    assert_code(err, ErrorCode.TEAM_RUN_ROSTER_EMPTY, status=422)
    assert err.value.details["reason"] == "manifest-unavailable"
    assert err.value.details["team_agent_id"] == TEAM_ID
    assert err.value.details["tier"] == "quick"
    assert _table_counts(services) == before  # A3：拒绝即零写入


def test_an_empty_manifest_refuses_the_run_before_any_write(tmp_path: Path) -> None:
    """A2/A3 构造 ②（工作区可达、manifest 无成员）⇒ ``manifest-empty`` + 四表零新增。

    与构造 ① 的区别正是 ``reason``：访问器把工作区交出来了（不是接线问题），清单里
    确实一个成员都没有。守卫必须在 ``create_project``（第一个写）之前落下。
    """
    services, user_id = _lazy_services(tmp_path, name=".octop-empty")
    workspace = FakeWorkspace({MANIFEST: manifest([])})
    service = services.team_run_service(workspace_for=_workspace_accessor(workspace))
    before = _table_counts(services)

    with pytest.raises(OctopError) as err:
        service.create(team_agent_id=TEAM_ID, user=Actor(user_id), goal="空花名册", tier="standard")

    assert_code(err, ErrorCode.TEAM_RUN_ROSTER_EMPTY, status=422)
    assert err.value.details["reason"] == "manifest-empty"
    assert err.value.details["tier"] == "standard"
    assert _table_counts(services) == before
    assert before == dict.fromkeys(_GUARDED_TABLES, 0)


def test_a_lead_only_roster_creates_the_run_and_exactly_one_member_row(tmp_path: Path) -> None:
    """A4 反向对照：lead-only（``kept`` 长度 1）**必须放行**，且只落 1 行成员。

    守卫判据是 ``len(trim.kept) == 0``，**不是** ``< TEAM_MIN_MEMBERS(2)``：``lead`` 是
    合法 roster 角色，把团队清单的最小成员数挪到 run 花名册上会让这条用例以 422 变红
    —— 这正是它存在的理由（DECISIONS D3/D4）。
    """
    services, user_id = _lazy_services(tmp_path, name=".octop-lead-only")
    workspace = FakeWorkspace({MANIFEST: manifest([(TEAM_ID, "lead")])})
    service = services.team_run_service(workspace_for=_workspace_accessor(workspace))
    before = _table_counts(services)

    run = service.create(team_agent_id=TEAM_ID, user=Actor(user_id), goal="只有 lead", tier="quick")

    members = services.team_run_repo.list_members(run.run_id)
    assert len(members) == 1  # lead 是合法 roster 角色 —— 不得写成 `>= 2`
    assert members[0].role == "lead"
    # 本用例不传 host_agent_id、manifest 也没有 lead_agent_id ⇒ 按 ``_kept_lead`` 的
    # 既定语义「团队主持人亲自带队时不标记成员行」，这里**不该**期望 is_lead 为真。
    after = _table_counts(services)
    assert after["projects"] == before["projects"] + 1
    assert after["team_runs"] == before["team_runs"] + 1
    assert after["team_run_members"] == before["team_run_members"] + 1


def test_bind_runtime_invalidates_the_self_built_team_memo(harness: Harness) -> None:
    """SPEC A6 第二半：``bind_runtime`` 之后**自建**的 ``TeamService`` memo 必须失效。

    顺序就是全部要点 —— 物化(A) → 重绑(B) → 再取 ⇒ 必须是新实例、且只用 B：

    ① 先让 ``_team()`` 用访问器 A **自建** memo（A 的花名册 = lead + backend）；
    ② ``bind_runtime(workspace_for=B)``，B 的角色集合明显不同（lead + docs + devops）；
    ③ 再取 ``_team()`` ⇒ ``is not`` 旧实例，且 roster 来自 B；
    ④ 只建**一个** run（``run_id_for()`` 是秒级精度，同秒第二次 create 会 409
       ``TEAM_RUN_CONFLICT``）⇒ 落库成员来自 B —— 「陈旧访问器不再被读」的最终判据。

    这条钉的是 FIND-2：去掉 ``bind_runtime`` 末尾的失效之后 ``tests/unit`` + E2E **全绿**，
    说明该半条此前零判别性覆盖；本用例即那个缺失的判据。构造时**不注入** ``team_service=``
    —— 注入实例归调用方所有、repair-1 之后刻意不失效（``_team_service_injected``），
    本半条管的是自建 memo。
    """
    workspace_a = FakeWorkspace({MANIFEST: manifest([(TEAM_ID, "lead"), ("ag-a", "backend")])})
    workspace_b = FakeWorkspace(
        {MANIFEST: manifest([(TEAM_ID, "lead"), ("ag-b1", "docs"), ("ag-b2", "devops")])}
    )
    service = TeamRunService(
        services=harness.services, workspace_for=_workspace_accessor(workspace_a)
    )

    stale = service._team()  # noqa: SLF001 —— 物化自建 memo（访问器 A）
    assert [m["role"] for m in stale.roster(TEAM_ID)["members"]] == ["lead", "backend"]

    service.bind_runtime(workspace_for=_workspace_accessor(workspace_b))

    fresh = service._team()  # noqa: SLF001
    assert fresh is not stale, "bind_runtime 必须丢掉自建 memo（SPEC A6 第二半）"
    assert [m["role"] for m in fresh.roster(TEAM_ID)["members"]] == ["lead", "docs", "devops"]

    run = service.create(
        team_agent_id=TEAM_ID, user=harness.user, goal="失效之后建 run", tier="quick"
    )
    landed = {row.role for row in harness.services.team_run_repo.list_members(run.run_id)}
    assert landed == {"lead", "docs", "devops"}, landed  # 落库成员来自 B，不是陈旧的 A


def test_an_injected_team_service_survives_bind_runtime(harness: Harness) -> None:
    """SPEC A6 第一半 + repair-1：**注入**的 ``TeamService`` 穿过 ``bind_runtime`` 必须活着。

    与上一条是互补的两半，缺一不可：自建 memo 必须失效（否则读陈旧工作区），而注入实例归
    调用方所有 —— 它的 ``workspace_for`` 是**它自己构造时**捕获的，丢弃它并不会得到更好的
    roster，只会把调用方交出来的接线扔掉。这里刻意**不传**构造期 ``workspace_for``（注入方
    可能压根不传，正是 repair-1 注释里点名的形态）：

    ① 注入 ``team_service``（访问器 I：lead + backend），``bind_runtime(workspace_for=J)``
       （J：docs + devops + qa，且不含 lead，与 I 明显不同）；
    ② ``_team()`` 必须 ``is`` 那个注入实例（不是重建出来的等价物）；
    ③ 只建**一个** run ⇒ 落库成员来自 **I**；若注入实例被误丢，重建的服务会读 J（落库角色
       变成 J 的）或直接 422 ``TEAM_RUN_ROSTER_EMPTY`` —— 两种都得红。
    """
    workspace_i = FakeWorkspace({MANIFEST: manifest([(TEAM_ID, "lead"), ("ag-i", "backend")])})
    workspace_j = FakeWorkspace(
        {MANIFEST: manifest([("ag-j1", "docs"), ("ag-j2", "devops"), ("ag-j3", "qa")])}
    )
    injected = TeamService(harness.services.repos, workspace_for=_workspace_accessor(workspace_i))
    service = TeamRunService(services=harness.services, team_service=injected)
    assert [m["role"] for m in service._team().roster(TEAM_ID)["members"]] == ["lead", "backend"]

    service.bind_runtime(workspace_for=_workspace_accessor(workspace_j))

    assert service._team() is injected, "注入实例归调用方所有 —— bind_runtime 不得丢弃它"
    assert [m["role"] for m in service._team().roster(TEAM_ID)["members"]] == ["lead", "backend"]

    run = service.create(team_agent_id=TEAM_ID, user=harness.user, goal="注入优先", tier="quick")
    landed = {row.role for row in harness.services.team_run_repo.list_members(run.run_id)}
    assert landed == {"lead", "backend"}, landed  # 来自 I（注入优先），而不是 J
