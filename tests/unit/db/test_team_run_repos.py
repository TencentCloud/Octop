"""``TeamRunRepo`` / ``ProjectTaskFindingRepo`` (migration 025).

Behaviour under test is the repo contract only -- the tables themselves are
covered by ``test_migration_025.py``. Two points get extra attention because the
DB, not Python, is what enforces them:

* **at most one lead per run** -- the partial unique index ``WHERE is_lead = 1``
  must reject a second lead (and accept any number of non-leads);
* **``pending_decision`` is addressed by ``run_id``** although the column lives on
  ``threads``, and reading it is idempotent (unset / unknown / malformed all give
  ``None`` rather than raising).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.agents import AgentRepo
from octop.infra.db.repos.project_task_findings import ProjectTaskFindingRepo
from octop.infra.db.repos.projects import ProjectRepo
from octop.infra.db.repos.team_runs import TeamRunRepo
from octop.infra.db.repos.threads import ThreadRepo
from octop.infra.db.repos.users import UserRepo
from octop.infra.db.services import RepoBundle, build_shared_services


@pytest.fixture
def db(tmp_path: Path) -> SqlitePool:
    pool = SqlitePool(tmp_path / "octop.db")
    run_migrations(pool)
    return pool


def _seed_run(
    db: SqlitePool, *, project_id: str | None = None, thread_id: str | None = None
) -> str:
    """A user + agent + project (+ optional room thread) and one run on top."""
    UserRepo(db).create(username="u", password_hash="h", role="user")
    AgentRepo(db).create(agent_id="a1", user_id=1, name="Host")
    project = ProjectRepo(db).create(owner_user_id=1, name="P")
    if thread_id is not None:
        ThreadRepo(db).insert(
            thread_id=thread_id,
            agent_id="a1",
            user_id=1,
            channel_type="dashboard",
            session_key=f"a1:team:{thread_id}",
        )
    run_id = "2026-09-29-000001"
    TeamRunRepo(db).create(
        run_id=run_id,
        team_agent_id="a1",
        project_id=project_id or project.id,
        goal="ship it",
        created_by=1,
        room_thread_id=thread_id,
    )
    return run_id


def test_create_and_get_round_trip(db: SqlitePool) -> None:
    run_id = _seed_run(db)
    row = TeamRunRepo(db).get(run_id)
    assert row is not None
    assert row.run_id == run_id
    assert row.status == "running"
    assert row.phase == "clarify"
    assert row.mode == "one-shot"
    assert row.max_review_rounds == 3
    assert row.room_thread_id is None
    assert row.created_at == row.updated_at


def test_a_project_can_own_only_one_run(db: SqlitePool) -> None:
    run_id = _seed_run(db)
    row = TeamRunRepo(db).get(run_id)
    assert row is not None
    with pytest.raises(sqlite3.IntegrityError):
        TeamRunRepo(db).create(
            run_id="2026-09-29-000002",
            team_agent_id="a1",
            project_id=row.project_id,
            goal="second",
            created_by=1,
        )


def test_list_filters_by_team_and_status(db: SqlitePool) -> None:
    run_id = _seed_run(db)
    repo = TeamRunRepo(db)
    assert [r.run_id for r in repo.list()] == [run_id]
    assert [r.run_id for r in repo.list(team_agent_id="a1")] == [run_id]
    assert repo.list(team_agent_id="other") == []
    assert repo.list(status="running") != []
    assert repo.list(status="complete") == []


def test_update_phase_and_status_touch_updated_at(db: SqlitePool) -> None:
    run_id = _seed_run(db)
    repo = TeamRunRepo(db)
    before = repo.get(run_id)
    assert before is not None
    assert repo.update_phase(run_id, "方案确认") is True
    assert repo.update_status(run_id, "awaiting_confirmation") is True
    after = repo.get(run_id)
    assert after is not None
    assert after.phase == "方案确认"
    assert after.status == "awaiting_confirmation"
    assert after.updated_at >= before.updated_at
    assert repo.update_phase("no-such-run", "x") is False
    assert repo.update_status("no-such-run", "x") is False


def test_phases_upsert_and_order(db: SqlitePool) -> None:
    run_id = _seed_run(db)
    repo = TeamRunRepo(db)
    repo.upsert_phase(run_id, "clarify", seq=1, status="passed", passed_at=10)
    repo.upsert_phase(run_id, "design", seq=2, status="active", entered_at=11)
    # Re-running the same phase must update in place, not duplicate (UNIQUE(run_id, phase)).
    repo.upsert_phase(run_id, "design", seq=2, status="passed", gate_detail={"ok": True})
    phases = repo.list_phases(run_id)
    assert [p.phase for p in phases] == ["clarify", "design"]
    assert phases[1].status == "passed"
    assert phases[1].gate_detail == {"ok": True}
    assert repo.get_phase(run_id, "design") is not None
    assert repo.get_phase(run_id, "missing") is None


def test_members_add_list_remove(db: SqlitePool) -> None:
    run_id = _seed_run(db)
    repo = TeamRunRepo(db)
    lead = repo.add_member(run_id, role="lead", agent_id="a1", is_lead=True)
    dev = repo.add_member(run_id, role="dev", agent_id="a2")
    assert lead.is_lead is True
    assert dev.is_lead is False
    assert [m.role for m in repo.list_members(run_id)] == ["lead", "dev"]
    assert repo.get_member(run_id, "dev") is not None
    assert repo.lead_member(run_id) is not None
    assert repo.lead_member(run_id).role == "lead"  # type: ignore[union-attr]
    assert repo.remove_member(run_id, "dev") is True
    assert [m.role for m in repo.list_members(run_id)] == ["lead"]
    assert repo.remove_member(run_id, "dev") is False


def test_role_is_unique_per_run(db: SqlitePool) -> None:
    run_id = _seed_run(db)
    repo = TeamRunRepo(db)
    repo.add_member(run_id, role="dev", agent_id="a2")
    with pytest.raises(sqlite3.IntegrityError):
        repo.add_member(run_id, role="dev", agent_id="a3")


def test_at_most_one_lead_per_run_is_enforced_by_the_index(db: SqlitePool) -> None:
    """A second ``is_lead=1`` row must be rejected; non-leads stay unlimited."""
    run_id = _seed_run(db)
    repo = TeamRunRepo(db)
    repo.add_member(run_id, role="lead", agent_id="a1", is_lead=True)
    with pytest.raises(sqlite3.IntegrityError):
        repo.add_member(run_id, role="deputy", agent_id="a2", is_lead=True)
    for role in ("dev", "qa", "reviewer"):
        repo.add_member(run_id, role=role, agent_id=f"a-{role}")
    assert len(repo.list_members(run_id)) == 4


def test_pending_decision_set_overwrite_and_resolve(db: SqlitePool) -> None:
    """``pending_decision`` is set and overwritten -- there is no "clear to NULL".

    Resolving a decision records a **resolved marker** through the same
    ``set_pending_decision`` (that is what ``run_service.decide`` does), because
    "no decision yet" and "decision handled" are different facts: NULLing the
    column would leave the reader unable to tell them apart. An earlier revision
    shipped a ``clear_pending_decision`` helper; it was deleted as a method with
    no producer.
    """
    run_id = _seed_run(db, thread_id="thr_1")
    repo = TeamRunRepo(db)
    # Idempotent read: nothing pending yet.
    assert repo.get_pending_decision(run_id) is None

    payload = {
        "id": "d1",
        "kind": "plan_confirm",
        "question": "执行？",
        "options": [{"key": "run", "label": "执行", "effect": "implement"}],
        "created_at": 1,
    }
    assert repo.set_pending_decision(run_id, payload) is True
    assert repo.get_pending_decision(run_id) == payload

    # Overwrite with an escalation, then with a resolved marker.
    assert repo.set_pending_decision(run_id, {"id": "d2", "kind": "escalate"}) is True
    assert repo.get_pending_decision(run_id) == {"id": "d2", "kind": "escalate"}
    resolved = {"id": "d2", "kind": "escalate", "resolved": True, "choice": "run"}
    assert repo.set_pending_decision(run_id, resolved) is True
    assert repo.get_pending_decision(run_id) == resolved


def test_pending_decision_malformed_json_reads_as_unset(db: SqlitePool) -> None:
    run_id = _seed_run(db, thread_id="thr_1")
    with db.transaction() as conn:
        conn.execute(
            "UPDATE threads SET pending_decision = ? WHERE thread_id = 'thr_1'", ("{oops",)
        )
    assert TeamRunRepo(db).get_pending_decision(run_id) is None


def test_room_thread_can_be_bound_after_creation(db: SqlitePool) -> None:
    run_id = _seed_run(db, thread_id="thr_1")
    repo = TeamRunRepo(db)
    assert repo.set_room_thread(run_id, "thr_1") is True
    row = repo.get(run_id)
    assert row is not None
    assert row.room_thread_id == "thr_1"
    assert repo.set_room_thread("no-such-run", "thr_1") is False


def test_delete_run_cascades_to_children(db: SqlitePool) -> None:
    run_id = _seed_run(db)
    repo = TeamRunRepo(db)
    repo.upsert_phase(run_id, "clarify", seq=1)
    repo.add_member(run_id, role="dev", agent_id="a2")
    assert repo.delete(run_id) is True
    assert repo.get(run_id) is None
    assert repo.list_phases(run_id) == []
    assert repo.list_members(run_id) == []
    assert repo.delete(run_id) is False


# ── findings ─────────────────────────────────────────────────────────────────


def test_finding_insert_get_and_lists(db: SqlitePool) -> None:
    UserRepo(db).create(username="u", password_hash="h", role="user")
    repo = ProjectTaskFindingRepo(db)
    first = repo.insert(
        finding_id="f1", task_id="t1", severity="high", title="Missing test", round=1
    )
    repo.insert(finding_id="f2", task_id="t1", severity="low", title="Typo", round=1)
    assert first.status == "open"
    assert first.verdict is None
    assert first.run_id is None
    assert repo.get("f1") is not None
    assert repo.get("nope") is None
    assert [f.finding_id for f in repo.list_by_task("t1")] == ["f1", "f2"]
    assert repo.list_by_task("t2") == []


def test_findings_list_by_run(db: SqlitePool) -> None:
    run_id = _seed_run(db)
    repo = ProjectTaskFindingRepo(db)
    repo.insert(finding_id="f1", task_id="t1", severity="high", title="A", run_id=run_id)
    repo.insert(finding_id="f2", task_id="t1", severity="low", title="B")
    assert [f.finding_id for f in repo.list_by_run(run_id)] == ["f1"]
    assert repo.list_by_run("no-such-run") == []


# ── wiring ───────────────────────────────────────────────────────────────────


def test_repo_bundle_exposes_both_repos(db: SqlitePool) -> None:
    bundle = RepoBundle.from_pool(db)
    assert isinstance(bundle.team_run_repo, TeamRunRepo)
    assert isinstance(bundle.task_finding_repo, ProjectTaskFindingRepo)
    assert bundle.team_run_repo is not None and bundle.task_finding_repo is not None


def test_shared_services_exposes_both_repos(db: SqlitePool, tmp_path: Path) -> None:
    from octop.config import OctopConfig
    from octop.infra.utils.paths import PathLayout

    services = build_shared_services(db=db, paths=PathLayout(root=tmp_path), config=OctopConfig())
    assert isinstance(services.team_run_repo, TeamRunRepo)
    assert isinstance(services.task_finding_repo, ProjectTaskFindingRepo)
