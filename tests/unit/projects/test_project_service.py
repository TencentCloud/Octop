"""Project service — KB lifecycle, state machine, and the §4.6 permission matrix.

The compensating-delete tests are the point of this file: creating a project
spans two repos and a knowledge base, each opening its own transaction, so a
failure part-way through must leave **nothing** behind.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.knowledge import KnowledgeRepo
from octop.infra.db.repos.project_tasks import ProjectTaskRepo, TimelineRepo
from octop.infra.db.repos.projects import (
    MEMBER_SUBJECT_AGENT,
    MEMBER_SUBJECT_USER,
    ProjectMemberRepo,
    ProjectRepo,
)
from octop.infra.db.repos.settings import SettingsRepo
from octop.infra.db.repos.users import UserRepo
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.knowledge import service as knowledge_service_module
from octop.infra.knowledge.service import MAX_BASES_PER_OWNER
from octop.infra.projects import service as project_service_module
from octop.infra.projects.service import (
    PROJECT_ACTIONS,
    PROJECT_ARCHIVE,
    PROJECT_CONFIRM,
    PROJECT_MANAGE_CONFIG,
    PROJECT_MANAGE_MEMBERS,
    PROJECT_READ,
    PROJECT_WRITE,
    ProjectService,
)
from octop.infra.utils.paths import PathLayout


class Actor:
    """Minimal user stand-in: ``id`` + ``is_admin`` + ``permissions``."""

    def __init__(
        self, user_id: int, *, admin: bool = False, permissions: list[str] | None = None
    ) -> None:
        self.id = user_id
        self._admin = admin
        # Creating a project also creates its knowledge base, so a usable actor
        # needs both keys by default.
        self.permissions = ["projects", "knowledge_bases"] if permissions is None else permissions

    @property
    def is_admin(self) -> bool:
        return self._admin


@pytest.fixture
def services(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path / "home"))
    pool = SqlitePool(tmp_path / "octop.db")
    run_migrations(pool)
    # The knowledge feature gate needs an embedding provider; the project
    # service is not what is under test here.
    monkeypatch.setattr(knowledge_service_module, "assert_knowledge_usable", lambda *_a: None)
    # Pretend the knowledge feature is ready, so create_project binds a KB.
    # test_create_project_without_a_usable_knowledge_feature overrides this.
    monkeypatch.setattr(
        project_service_module, "get_capability", lambda *_a, **_k: {"usable": True}
    )
    return SimpleNamespace(
        db=pool,
        project_repo=ProjectRepo(pool),
        project_member_repo=ProjectMemberRepo(pool),
        project_task_repo=ProjectTaskRepo(pool),
        timeline_repo=TimelineRepo(pool),
        knowledge_repo=KnowledgeRepo(pool),
        settings_repo=SettingsRepo(pool),
        user_repo=UserRepo(pool),
        paths=PathLayout.from_env(),
    )


@pytest.fixture
def service(services: SimpleNamespace) -> ProjectService:
    return ProjectService(services)


@pytest.fixture
def owner(services: SimpleNamespace) -> Actor:
    return Actor(services.user_repo.create(username="owner", password_hash="h", role="user"))


def make_project(service: ProjectService, owner: Actor, name: str = "Alpha") -> Any:
    return service.create_project(owner_user=owner, name=name)


def add_member(
    service: ProjectService,
    project_id: str,
    *,
    actor: Actor,
    subject_id: str,
    role: str,
) -> None:
    service.add_member(
        project_id,
        user=actor,
        subject_type=MEMBER_SUBJECT_USER,
        subject_id=subject_id,
        role=role,
        subject_user_id=int(subject_id),
    )


# ── create: happy path ───────────────────────────────────────────────────────


def test_create_project_binds_owner_membership_and_knowledge_base(
    service: ProjectService, services: SimpleNamespace, owner: Actor
) -> None:
    project = make_project(service, owner)

    assert project.status == "draft"
    assert project.memory_namespace == f"project_{project.id}"
    assert project.kb_id is not None, "the project's KB id must be written back"

    member = services.project_member_repo.get(project.id, MEMBER_SUBJECT_USER, str(owner.id))
    assert member is not None and member.role == "owner"

    bases = services.knowledge_repo.list_visible(owner.id)
    assert [b.id for b in bases] == [project.kb_id]
    assert bases[0].name == "Alpha"


def test_create_project_allows_non_ascii_names(
    service: ProjectService, services: SimpleNamespace, owner: Actor
) -> None:
    project = make_project(service, owner, name="项目甲")
    assert project.name == "项目甲"
    assert services.knowledge_repo.list_visible(owner.id)[0].name == "项目甲"


def test_create_project_requires_the_projects_permission(service: ProjectService) -> None:
    actor = Actor(1, permissions=[])
    with pytest.raises(OctopError) as err:
        service.create_project(owner_user=actor, name="Alpha")
    assert err.value.code is ErrorCode.PROJECT_FORBIDDEN


def test_create_project_requires_the_knowledge_bases_permission(
    service: ProjectService, services: SimpleNamespace
) -> None:
    """Creating a project creates a KB, so the feature must be available up front.

    Checking here keeps step ③ from failing after ①② already wrote rows.
    """
    actor = Actor(1, permissions=["projects"])
    with pytest.raises(OctopError) as err:
        service.create_project(owner_user=actor, name="Alpha")
    assert err.value.code is ErrorCode.PROJECT_FORBIDDEN
    assert services.project_repo.list_by_owner(1) == []
    assert services.knowledge_repo.count_bases_for_owner(1) == 0


def test_create_project_without_a_usable_knowledge_feature(
    service: ProjectService,
    services: SimpleNamespace,
    owner: Actor,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A fresh install has the knowledge feature off; projects must still work.

    Regression: the capability check used to be missing from the ⓪ phase, so a
    project created on a fresh install died at step ③ with an opaque
    PROJECT_KB_BIND_FAILED (500). ``kb_id`` stays NULL, which is the case the
    plan's T3.4 note already allows for.
    """
    monkeypatch.setattr(
        project_service_module, "get_capability", lambda *_a, **_k: {"usable": False}
    )

    project = make_project(service, owner, name="无知识库项目")

    assert project.kb_id is None, "no KB should be bound when the feature is off"
    assert project.memory_namespace == f"project_{project.id}"
    assert services.project_repo.list_by_owner(owner.id) == [project]
    assert services.knowledge_repo.count_bases_for_owner(owner.id) == 0

    # And the project is fully usable: activate, add a task, read the timeline.
    activated = service.transition_project(project.id, user=owner, target="active")
    assert activated.status == "active"
    task = service.create_task(project.id, user=owner, title="照常可用")
    assert task.status == "planning"


def test_create_project_rejects_a_blank_name(service: ProjectService, owner: Actor) -> None:
    with pytest.raises(ValueError, match="project name is required"):
        service.create_project(owner_user=owner, name="   ")


# ── create: ⓪ preconditions leave nothing behind ────────────────────────────


def test_create_rejects_at_the_kb_limit_without_writing_anything(
    service: ProjectService,
    services: SimpleNamespace,
    owner: Actor,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(project_service_module, "MAX_BASES_PER_OWNER", 1)
    make_project(service, owner, name="First")

    with pytest.raises(OctopError) as err:
        make_project(service, owner, name="Second")
    assert err.value.code is ErrorCode.KNOWLEDGE_BASE_LIMIT

    assert [p.name for p in services.project_repo.list_by_owner(owner.id)] == ["First"]
    assert services.knowledge_repo.count_bases_for_owner(owner.id) == 1


def test_create_rejects_a_kb_name_clash_without_writing_anything(
    service: ProjectService, services: SimpleNamespace, owner: Actor
) -> None:
    make_project(service, owner, name="Alpha")
    with pytest.raises(OctopError) as err:
        make_project(service, owner, name="Alpha")
    assert err.value.code is ErrorCode.KNOWLEDGE_NAME_TAKEN

    assert [p.name for p in services.project_repo.list_by_owner(owner.id)] == ["Alpha"]
    assert services.knowledge_repo.count_bases_for_owner(owner.id) == 1


def test_kb_limit_constant_is_the_one_the_service_uses() -> None:
    assert MAX_BASES_PER_OWNER == 20


# ── create: failure branches must compensate ─────────────────────────────────


def test_kb_creation_failure_leaves_no_project(
    service: ProjectService,
    services: SimpleNamespace,
    owner: Actor,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The injected-failure test T2.1 calls for: no project row, no extra KB."""

    def boom(**_kwargs: Any) -> Any:
        raise RuntimeError("kb service exploded")

    monkeypatch.setattr(service._knowledge, "create_base", boom)

    with pytest.raises(OctopError) as err:
        make_project(service, owner)
    assert err.value.code is ErrorCode.PROJECT_KB_BIND_FAILED

    assert services.project_repo.list_by_owner(owner.id) == []
    assert (
        services.project_member_repo.list_project_ids_for_subject(
            MEMBER_SUBJECT_USER, str(owner.id)
        )
        == []
    )
    assert services.knowledge_repo.count_bases_for_owner(owner.id) == 0


def test_kb_binding_failure_deletes_the_kb_it_just_created(
    service: ProjectService,
    services: SimpleNamespace,
    owner: Actor,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Step ④ failing must not leave a knowledge base without a project."""

    def boom(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("update failed")

    monkeypatch.setattr(services.project_repo, "set_kb_id", boom)

    with pytest.raises(OctopError) as err:
        make_project(service, owner)
    assert err.value.code is ErrorCode.PROJECT_KB_BIND_FAILED

    assert services.project_repo.list_by_owner(owner.id) == []
    assert services.knowledge_repo.count_bases_for_owner(owner.id) == 0


def test_member_insert_failure_removes_the_project_row(
    service: ProjectService,
    services: SimpleNamespace,
    owner: Actor,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("member insert failed")

    monkeypatch.setattr(services.project_member_repo, "add", boom)

    with pytest.raises(OctopError) as err:
        make_project(service, owner)
    assert err.value.code is ErrorCode.PROJECT_KB_BIND_FAILED
    assert services.project_repo.list_by_owner(owner.id) == []


def test_compensation_survives_a_failing_cleanup(
    service: ProjectService,
    services: SimpleNamespace,
    owner: Actor,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A compensation step that itself fails must not mask the original error."""

    def boom(**_kwargs: Any) -> Any:
        raise RuntimeError("kb exploded")

    monkeypatch.setattr(service._knowledge, "create_base", boom)

    def also_boom(*_args: Any, **_kwargs: Any) -> bool:
        raise RuntimeError("cleanup exploded")

    monkeypatch.setattr(services.project_repo, "delete", also_boom)

    with pytest.raises(OctopError) as err:
        make_project(service, owner)
    assert err.value.code is ErrorCode.PROJECT_KB_BIND_FAILED


# ── permission matrix (§4.6) ─────────────────────────────────────────────────


def test_role_matrix_matches_the_plan(service: ProjectService, owner: Actor) -> None:
    project = make_project(service, owner)

    viewer = Actor(owner.id + 100)
    member = Actor(owner.id + 101)
    proj_admin = Actor(owner.id + 102)
    add_member(service, project.id, actor=owner, subject_id=str(viewer.id), role="viewer")
    add_member(service, project.id, actor=owner, subject_id=str(member.id), role="member")
    add_member(service, project.id, actor=owner, subject_id=str(proj_admin.id), role="admin")

    # read: everyone
    for actor in (owner, viewer, member, proj_admin):
        assert service.assert_project_role(project.id, user=actor, required=PROJECT_READ)

    # write / confirm / manage_members: owner + admin only... plus member for write
    for actor in (viewer,):
        for action in (PROJECT_WRITE, PROJECT_CONFIRM, PROJECT_MANAGE_MEMBERS, PROJECT_ARCHIVE):
            with pytest.raises(OctopError) as err:
                service.assert_project_role(project.id, user=actor, required=action)
            assert err.value.code is ErrorCode.PROJECT_ROLE_FORBIDDEN

    assert service.assert_project_role(project.id, user=member, required=PROJECT_WRITE)
    with pytest.raises(OctopError):
        service.assert_project_role(project.id, user=member, required=PROJECT_CONFIRM)

    assert service.assert_project_role(project.id, user=proj_admin, required=PROJECT_CONFIRM)
    assert service.assert_project_role(project.id, user=proj_admin, required=PROJECT_MANAGE_MEMBERS)
    with pytest.raises(OctopError) as err:
        service.assert_project_role(project.id, user=proj_admin, required=PROJECT_ARCHIVE)
    assert err.value.code is ErrorCode.PROJECT_ROLE_FORBIDDEN, "admin must not archive"

    assert service.assert_project_role(project.id, user=owner, required=PROJECT_ARCHIVE)


# ── permission matrix: completeness (second batch PLAN §6 / F5) ──────────────
#
# The hand-written assertions above exercise *chosen* actions. Nothing there
# fails if an action is missing from ``PROJECT_ACTIONS`` or from a role's level
# set — the frozen matrix ("owner/admin have manage_config, member/viewer do
# not") could be implemented backwards and stay green. The three tests below
# make the action set and every role × action cell assertable.

#: The four project roles, in matrix order.
_MATRIX_ROLES = ("owner", "admin", "member", "viewer")

#: Frozen matrix (second batch PLAN §6, first frozen in the first batch's §3.3).
#: ``owner`` and ``admin`` are derived from ``PROJECT_ACTIONS`` on purpose: a new
#: action must then be granted (or explicitly removed) for those roles instead of
#: silently drifting out of the contract.
_EXPECTED_ROLE_ACTIONS: dict[str, frozenset[str]] = {
    "owner": frozenset(PROJECT_ACTIONS),
    "admin": frozenset(PROJECT_ACTIONS) - {PROJECT_ARCHIVE},
    "member": frozenset({PROJECT_READ, PROJECT_WRITE}),
    "viewer": frozenset({PROJECT_READ}),
}

#: Distinct user ids for the non-owner rows of the matrix.
_MATRIX_ROLE_OFFSETS = {"admin": 201, "member": 202, "viewer": 203}


def test_project_actions_is_the_frozen_full_set() -> None:
    """The action universe itself is asserted: dropping one is a failure.

    Literal strings on purpose — they are the wire values the routers, the
    i18n keys and the frontend depend on, so a rename must be a deliberate act.
    """
    assert set(PROJECT_ACTIONS) == {
        "read",
        "write",
        "confirm",
        "manage_members",
        "manage_config",
        "archive",
    }
    assert len(PROJECT_ACTIONS) == 6
    assert PROJECT_MANAGE_CONFIG == "manage_config"


def test_matrix_definition_covers_the_full_cartesian_product() -> None:
    """Guard the matrix definition itself: 4 roles × 6 actions = 24 cells.

    Without this, a shortened parametrize list or a typo inside an expected set
    (which would silently turn a cell into "expected allow" while never being
    exercised) would shrink coverage instead of failing.
    """
    assert _MATRIX_ROLES == ("owner", "admin", "member", "viewer")
    assert set(_EXPECTED_ROLE_ACTIONS) == set(_MATRIX_ROLES)
    assert len(PROJECT_ACTIONS) == 6
    cells = {(role, action) for role in _MATRIX_ROLES for action in PROJECT_ACTIONS}
    assert len(cells) == 24
    for role, actions in _EXPECTED_ROLE_ACTIONS.items():
        assert actions <= set(PROJECT_ACTIONS), f"{role} expects an unknown action"
    # 6 (owner has every action) + 5 (admin has all but archive) + 2 + 1.
    assert sum(len(actions) for actions in _EXPECTED_ROLE_ACTIONS.values()) == 14


@pytest.mark.parametrize("role", _MATRIX_ROLES)
def test_role_matrix_matches_the_plan_for_every_cell(
    service: ProjectService, owner: Actor, role: str
) -> None:
    """Walk the whole cartesian product for one role: every action, every cell.

    Allowed cells must return the caller's role; denied cells must raise
    ``PROJECT_ROLE_FORBIDDEN`` (403) — never a 500 and never a silent pass.
    """
    project = make_project(service, owner, name=f"Matrix {role}")
    actor = owner
    if role != "owner":
        actor = Actor(owner.id + _MATRIX_ROLE_OFFSETS[role])
        add_member(
            service,
            project.id,
            actor=owner,
            subject_id=str(actor.id),
            role=role,
        )

    allowed = _EXPECTED_ROLE_ACTIONS[role]
    visited: set[tuple[str, str]] = set()
    for action in PROJECT_ACTIONS:
        visited.add((role, action))
        if action in allowed:
            assert service.assert_project_role(project.id, user=actor, required=action) == role, (
                f"{role} must be allowed to {action}"
            )
        else:
            with pytest.raises(OctopError) as err:
                service.assert_project_role(project.id, user=actor, required=action)
            assert err.value.code is ErrorCode.PROJECT_ROLE_FORBIDDEN, f"{role} + {action}"
            assert err.value.status == 403, f"{role} + {action} must be a 403"

    assert visited == {(role, action) for action in PROJECT_ACTIONS}


def test_manage_config_is_not_implied_by_write_or_archive(
    service: ProjectService, owner: Actor
) -> None:
    """R18: actions are looked up, never implied — in both directions.

    ``member`` may write, yet must not configure (a member could otherwise widen
    what the project's agents can reach); ``admin`` may configure, yet must not
    archive (archiving stays owner-only).
    """
    project = make_project(service, owner)
    member = Actor(owner.id + 301)
    proj_admin = Actor(owner.id + 302)
    add_member(service, project.id, actor=owner, subject_id=str(member.id), role="member")
    add_member(service, project.id, actor=owner, subject_id=str(proj_admin.id), role="admin")

    # write does not imply manage_config
    assert service.assert_project_role(project.id, user=member, required=PROJECT_WRITE)
    with pytest.raises(OctopError) as err:
        service.assert_project_role(project.id, user=member, required=PROJECT_MANAGE_CONFIG)
    assert err.value.code is ErrorCode.PROJECT_ROLE_FORBIDDEN
    assert err.value.status == 403

    # manage_config does not imply archive
    assert service.assert_project_role(project.id, user=proj_admin, required=PROJECT_MANAGE_CONFIG)
    with pytest.raises(OctopError) as err:
        service.assert_project_role(project.id, user=proj_admin, required=PROJECT_ARCHIVE)
    assert err.value.code is ErrorCode.PROJECT_ROLE_FORBIDDEN

    # …and the same two claims against the frozen table, so an implication
    # sneaking into either side is caught even where no role can observe it.
    assert PROJECT_WRITE in project_service_module._ROLE_LEVELS["member"]
    assert PROJECT_MANAGE_CONFIG not in project_service_module._ROLE_LEVELS["member"]
    assert PROJECT_MANAGE_CONFIG in project_service_module._ROLE_LEVELS["admin"]
    assert PROJECT_ARCHIVE not in project_service_module._ROLE_LEVELS["admin"]


def test_archived_project_rejects_manage_config_as_well(
    service: ProjectService, owner: Actor
) -> None:
    """The read-only rule is orthogonal to the role table, and still applies."""
    project = make_project(service, owner)
    service.transition_project(project.id, user=owner, target="active")
    service.transition_project(project.id, user=owner, target="archived")

    assert service.assert_project_role(project.id, user=owner, required=PROJECT_READ) == "owner"
    with pytest.raises(OctopError) as err:
        service.assert_project_role(project.id, user=owner, required=PROJECT_MANAGE_CONFIG)
    assert err.value.code is ErrorCode.PROJECT_FORBIDDEN
    assert err.value.status == 403


def test_non_member_is_rejected_even_when_a_platform_admin(
    service: ProjectService, services: SimpleNamespace, owner: Actor
) -> None:
    project = make_project(service, owner)
    outsider = Actor(
        services.user_repo.create(username="outsider", password_hash="h", role="admin"), admin=True
    )

    with pytest.raises(OctopError) as err:
        service.assert_project_role(project.id, user=outsider, required=PROJECT_READ)
    assert err.value.code is ErrorCode.PROJECT_FORBIDDEN


def test_unknown_action_is_a_programming_error(service: ProjectService, owner: Actor) -> None:
    project = make_project(service, owner)
    with pytest.raises(ValueError, match="unknown project action"):
        service.assert_project_role(project.id, user=owner, required="teleport")


def test_missing_project_is_not_found(service: ProjectService, owner: Actor) -> None:
    with pytest.raises(OctopError) as err:
        service.get_project("nope", user=owner)
    assert err.value.code is ErrorCode.PROJECT_NOT_FOUND


# ── state machine (§4.6 / M8) ────────────────────────────────────────────────


def test_draft_can_activate_then_pause_and_resume(service: ProjectService, owner: Actor) -> None:
    project = make_project(service, owner)
    assert service.transition_project(project.id, user=owner, target="active").status == "active"
    assert service.transition_project(project.id, user=owner, target="paused").status == "paused"
    assert service.transition_project(project.id, user=owner, target="active").status == "active"


def test_draft_cannot_jump_straight_to_archived(service: ProjectService, owner: Actor) -> None:
    project = make_project(service, owner)
    with pytest.raises(OctopError) as err:
        service.transition_project(project.id, user=owner, target="archived")
    assert err.value.code is ErrorCode.PROJECT_STATUS_INVALID
    assert service.get_project(project.id, user=owner).status == "draft"


def test_archived_is_terminal(service: ProjectService, owner: Actor) -> None:
    project = make_project(service, owner)
    service.transition_project(project.id, user=owner, target="active")
    service.transition_project(project.id, user=owner, target="archived")

    for target in ("active", "paused", "archived"):
        with pytest.raises(OctopError) as err:
            service.transition_project(project.id, user=owner, target=target)
        assert err.value.code in {
            ErrorCode.PROJECT_STATUS_INVALID,
            ErrorCode.PROJECT_FORBIDDEN,
        }


def test_archived_project_is_read_only(
    service: ProjectService, services: SimpleNamespace, owner: Actor
) -> None:
    project = make_project(service, owner)
    service.transition_project(project.id, user=owner, target="active")
    service.transition_project(project.id, user=owner, target="archived")

    assert service.get_project(project.id, user=owner) is not None
    with pytest.raises(OctopError) as err:
        service.update_project(project.id, user=owner, name="Renamed")
    assert err.value.code is ErrorCode.PROJECT_FORBIDDEN
    with pytest.raises(OctopError) as err:
        service.add_member(
            project.id,
            user=owner,
            subject_type=MEMBER_SUBJECT_AGENT,
            subject_id="agent-1",
        )
    assert err.value.code is ErrorCode.PROJECT_FORBIDDEN


def test_activation_requires_at_least_one_member(
    service: ProjectService, services: SimpleNamespace, owner: Actor
) -> None:
    project = make_project(service, owner)
    # Drop the owner membership behind the service's back to reach the empty state.
    services.project_member_repo.remove(project.id, MEMBER_SUBJECT_USER, str(owner.id))

    with pytest.raises(OctopError) as err:
        service.transition_project(project.id, user=owner, target="active")
    assert err.value.code is ErrorCode.PROJECT_STATUS_INVALID


def test_activation_requires_the_owner_row_to_keep_the_owner_role(
    service: ProjectService, services: SimpleNamespace, owner: Actor
) -> None:
    project = make_project(service, owner)
    with services.db.transaction() as conn:
        conn.execute(
            "UPDATE project_members SET role = 'member' WHERE project_id = ?",
            (project.id,),
        )

    with pytest.raises(OctopError) as err:
        service.transition_project(project.id, user=owner, target="active")
    assert err.value.code is ErrorCode.PROJECT_STATUS_INVALID


def test_unknown_status_is_rejected_with_its_code(service: ProjectService, owner: Actor) -> None:
    project = make_project(service, owner)
    with pytest.raises(OctopError) as err:
        service.transition_project(project.id, user=owner, target="exploded")
    assert err.value.code is ErrorCode.PROJECT_STATUS_INVALID
    assert err.value.status == 409, "an unknown enum value is a 4xx, never a 500"


# ── membership guards ────────────────────────────────────────────────────────


def test_owner_cannot_be_removed(service: ProjectService, owner: Actor) -> None:
    project = make_project(service, owner)
    with pytest.raises(OctopError) as err:
        service.remove_member(
            project.id, user=owner, subject_type=MEMBER_SUBJECT_USER, subject_id=str(owner.id)
        )
    assert err.value.code is ErrorCode.PROJECT_MEMBER_INVALID


def test_owner_cannot_be_demoted(service: ProjectService, owner: Actor) -> None:
    project = make_project(service, owner)
    with pytest.raises(OctopError) as err:
        service.add_member(
            project.id,
            user=owner,
            subject_type=MEMBER_SUBJECT_USER,
            subject_id=str(owner.id),
            role="viewer",
        )
    assert err.value.code is ErrorCode.PROJECT_MEMBER_INVALID


def test_unknown_role_is_rejected(service: ProjectService, owner: Actor) -> None:
    project = make_project(service, owner)
    with pytest.raises(OctopError) as err:
        service.add_member(
            project.id,
            user=owner,
            subject_type=MEMBER_SUBJECT_AGENT,
            subject_id="agent-1",
            role="wizard",
        )
    assert err.value.code is ErrorCode.PROJECT_MEMBER_INVALID
    assert err.value.status == 400, "an unknown enum value is a 4xx, never a 500"


def test_viewer_cannot_add_members(
    service: ProjectService, services: SimpleNamespace, owner: Actor
) -> None:
    project = make_project(service, owner)
    viewer = Actor(owner.id + 100)
    add_member(service, project.id, actor=owner, subject_id=str(viewer.id), role="viewer")

    with pytest.raises(OctopError) as err:
        service.add_member(
            project.id,
            user=viewer,
            subject_type=MEMBER_SUBJECT_AGENT,
            subject_id="agent-1",
        )
    assert err.value.code is ErrorCode.PROJECT_ROLE_FORBIDDEN


def test_member_can_be_removed_by_an_admin_role(
    service: ProjectService, services: SimpleNamespace, owner: Actor
) -> None:
    project = make_project(service, owner)
    proj_admin = Actor(owner.id + 102)
    guest = Actor(owner.id + 103)
    add_member(service, project.id, actor=owner, subject_id=str(proj_admin.id), role="admin")
    add_member(service, project.id, actor=owner, subject_id=str(guest.id), role="member")

    assert service.remove_member(
        project.id,
        user=proj_admin,
        subject_type=MEMBER_SUBJECT_USER,
        subject_id=str(guest.id),
    )
    assert (
        services.project_member_repo.role_of(project.id, MEMBER_SUBJECT_USER, str(guest.id)) is None
    )


def test_agent_members_are_supported(service: ProjectService, owner: Actor) -> None:
    project = make_project(service, owner)
    member = service.add_member(
        project.id,
        user=owner,
        subject_type=MEMBER_SUBJECT_AGENT,
        subject_id="agent-1",
        role="member",
    )
    assert member.subject_type == MEMBER_SUBJECT_AGENT
    assert member.user_id is None


# ── list / delete ────────────────────────────────────────────────────────────


def test_list_projects_includes_member_projects(
    service: ProjectService, services: SimpleNamespace, owner: Actor
) -> None:
    own = make_project(service, owner, name="Own")
    other_owner = Actor(services.user_repo.create(username="other", password_hash="h", role="user"))
    invited = make_project(service, other_owner, name="Invited")
    add_member(service, invited.id, actor=other_owner, subject_id=str(owner.id), role="member")

    assert {p.id for p in service.list_projects(user=owner)} == {own.id, invited.id}


def test_list_projects_requires_the_projects_permission(service: ProjectService) -> None:
    with pytest.raises(OctopError) as err:
        service.list_projects(user=Actor(1, permissions=[]))
    assert err.value.code is ErrorCode.PROJECT_FORBIDDEN


def test_delete_project_requires_owner(
    service: ProjectService, services: SimpleNamespace, owner: Actor
) -> None:
    project = make_project(service, owner)
    proj_admin = Actor(owner.id + 102)
    add_member(service, project.id, actor=owner, subject_id=str(proj_admin.id), role="admin")

    with pytest.raises(OctopError) as err:
        service.delete_project(project.id, user=proj_admin)
    assert err.value.code is ErrorCode.PROJECT_ROLE_FORBIDDEN

    assert service.delete_project(project.id, user=owner) is True
    assert services.project_repo.get(project.id) is None


def test_delete_project_keeps_the_knowledge_base(
    service: ProjectService, services: SimpleNamespace, owner: Actor
) -> None:
    """Deleting a project must not destroy documents it never mentioned."""
    project = make_project(service, owner)
    kb_id = project.kb_id
    service.delete_project(project.id, user=owner)
    assert [b.id for b in services.knowledge_repo.list_visible(owner.id)] == [kb_id]


# ── discard_created_project: the symmetric undo of create_project ────────────
# 与上面 ``test_delete_project_keeps_the_knowledge_base`` 并列看最直观：同一个 project
# 行、同一个 KB —— ``delete_project`` **留** KB（里面可能有用户文档），
# ``discard_created_project`` **删** KB（这次创建从没被用户看见、KB 里不可能有文档；
# 留下它就白烧配额 20 / 占住名字，攒够 20 次失败之后连合法 goal 都建不出 project）。


def test_discard_created_project_removes_the_project_and_its_kb(
    service: ProjectService, services: SimpleNamespace, owner: Actor
) -> None:
    """KB 可用：撤销 ⇒ project 行没了**且** KB 没了（``delete_project`` 的对照面）。"""
    project = make_project(service, owner)
    # 正向对照（门真的开着）：create 确实绑了 KB —— 否则「KB 没了」是 0==0 假绿。
    assert project.kb_id is not None
    assert services.knowledge_repo.count_bases_for_owner(owner.id) == 1

    service.discard_created_project(project.id)

    assert services.project_repo.get(project.id) is None
    assert services.knowledge_repo.get_base(project.kb_id) is None
    assert services.knowledge_repo.count_bases_for_owner(owner.id) == 0


def test_discard_created_project_without_a_kb_only_removes_the_project(
    service: ProjectService,
    services: SimpleNamespace,
    owner: Actor,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``kb_id`` 为 NULL（fresh install / 未绑定）⇒ 只删 project，**不抛**。

    门关掉的构造与 ``test_create_project_without_a_usable_knowledge_feature`` 同源
    （``get_capability`` ⇒ ``{"usable": False}``），所以真的走 NULL 分支；随后再把门打开
    建一个带 KB 的同类 project，证明本用例不是「空库 0==0」。
    """
    monkeypatch.setattr(
        project_service_module, "get_capability", lambda *_a, **_k: {"usable": False}
    )
    project = make_project(service, owner, name="无知识库项目")
    assert project.kb_id is None, "本用例必须真的落在 NULL 分支"

    service.discard_created_project(project.id)

    assert services.project_repo.get(project.id) is None
    assert services.knowledge_repo.count_bases_for_owner(owner.id) == 0

    # 同函数在门打开时**必须**真的删掉 KB —— 否则上面那两行随时可能变成恒真。
    monkeypatch.setattr(
        project_service_module, "get_capability", lambda *_a, **_k: {"usable": True}
    )
    bound = make_project(service, owner, name="带知识库项目")
    assert bound.kb_id is not None
    service.discard_created_project(bound.id)
    assert services.knowledge_repo.get_base(bound.kb_id) is None


def test_discard_created_project_never_raises_when_the_kb_delete_fails(
    service: ProjectService,
    services: SimpleNamespace,
    owner: Actor,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """KB 删除抛错 ⇒ **绝不向外抛**，project 仍被删；KB 残留是这条纪律的既定代价。

    与 ``test_compensation_survives_a_failing_cleanup`` 同一纪律（补偿不得掩盖原始异常）：
    调用方（team-run 的补偿路径）要拿到「已尽力」，而不是一个新异常。残留一个 KB 是可恢复
    的脏行，异常链藏掉原始拒绝则不是。
    """
    project = make_project(service, owner)
    assert project.kb_id is not None  # 正向对照：这一步真的会被走到（不是空跑）

    def boom(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("kb delete exploded")

    monkeypatch.setattr(service._knowledge, "delete_base", boom)

    service.discard_created_project(project.id)  # 不抛

    assert services.project_repo.get(project.id) is None, "project 仍必须被删掉"
    assert services.knowledge_repo.get_base(project.kb_id) is not None, (
        "KB 残留 = 「绝不抛」的既定代价（可恢复的脏行 < 掩盖原始异常的异常链）"
    )


def test_discard_created_project_is_silent_for_an_unknown_id(
    service: ProjectService, services: SimpleNamespace, owner: Actor
) -> None:
    """未知 ``project_id`` ⇒ 静默返回、不抛（补偿路径的幂等语义：删过了不算错）。"""
    project = make_project(service, owner)
    assert project.kb_id is not None  # 正向对照：库里确实有东西，不是空库
    before = services.knowledge_repo.count_bases_for_owner(owner.id)

    service.discard_created_project("proj-does-not-exist")  # 不抛

    assert services.project_repo.get(project.id) is not None, "邻居必须原样活着"
    assert services.knowledge_repo.count_bases_for_owner(owner.id) == before


# ── F3: knowledge-base rebind (PLAN.md §4) ───────────────────────────────────


def _make_kb(
    services: SimpleNamespace, *, owner_user_id: int, name: str, shared: bool = False
) -> str:
    from octop.infra.knowledge.service import KnowledgeService

    return (
        KnowledgeService(services)
        .create_base(owner_user_id=owner_user_id, name=name, shared=shared)
        .id
    )


def test_kb_rebind_is_three_state_and_idempotent(
    service: ProjectService, services: SimpleNamespace, owner: Actor
) -> None:
    """Absent leaves it alone; a value rebinds; null unbinds — all 200."""
    project = service.create_project(owner_user=owner, name="Alpha")
    first = project.kb_id or _make_kb(services, owner_user_id=owner.id, name="Alpha")

    # ① the key is absent: nothing changes (the easiest case to get wrong)
    service.update_project(project.id, user=owner, goal="new goal")
    assert service.get_project(project.id, user=owner).kb_id == first

    second = _make_kb(services, owner_user_id=owner.id, name="Beta")
    rebound = service.update_project(project.id, user=owner, kb_id=second)
    assert rebound.kb_id == second

    # ② idempotent: rebinding to the same base keeps the value and does not raise
    assert service.update_project(project.id, user=owner, kb_id=second).kb_id == second

    # ③ null unbinds (a 200, not an error face)
    assert service.update_project(project.id, user=owner, kb_id=None).kb_id is None
    assert service.get_project(project.id, user=owner).kb_id is None


def test_kb_rebind_refusal_codes(
    service: ProjectService, services: SimpleNamespace, owner: Actor
) -> None:
    """404 for an invisible base, 403 for a visible-but-unwritable one (never 500)."""
    project = service.create_project(owner_user=owner, name="Alpha")
    other = Actor(services.user_repo.create(username="other", password_hash="h", role="user"))
    private = _make_kb(services, owner_user_id=other.id, name="Private")

    with pytest.raises(OctopError) as err:
        service.update_project(project.id, user=owner, kb_id="kb_missing")
    assert err.value.code is ErrorCode.KNOWLEDGE_NOT_FOUND
    assert err.value.status == 404
    assert err.value.status != 500

    with pytest.raises(OctopError) as err:
        service.update_project(project.id, user=owner, kb_id=private)
    assert err.value.code is ErrorCode.PROJECT_KB_FORBIDDEN
    assert err.value.status == 403
    assert err.value.status != 500

    # A refused rebind must not have written anything.
    assert service.get_project(project.id, user=owner).kb_id == project.kb_id


def test_kb_rebind_permission_matrix(
    service: ProjectService, services: SimpleNamespace, owner: Actor
) -> None:
    """The key's presence raises the whole request; other fields stay PROJECT_WRITE."""
    project = service.create_project(owner_user=owner, name="Alpha")
    member = Actor(services.user_repo.create(username="member", password_hash="h", role="user"))
    admin = Actor(services.user_repo.create(username="padmin", password_hash="h", role="user"))
    for actor, role in ((member, "member"), (admin, "admin")):
        service.add_member(
            project.id,
            user=owner,
            subject_type=MEMBER_SUBJECT_USER,
            subject_id=str(actor.id),
            role=role,
            subject_user_id=actor.id,
        )
    kb_id = _make_kb(services, owner_user_id=owner.id, name="Shared-KB")

    # A write-only member may still edit a plain field…
    assert service.update_project(project.id, user=member, goal="member goal").goal == "member goal"

    # …but the same request carrying ``kb_id`` is refused for the whole payload.
    with pytest.raises(OctopError) as err:
        service.update_project(project.id, user=member, goal="smuggled", kb_id=kb_id)
    assert err.value.code is ErrorCode.PROJECT_ROLE_FORBIDDEN
    assert err.value.status == 403
    assert err.value.status != 500
    assert service.get_project(project.id, user=owner).goal == "member goal", "no smuggling"

    # admin holds MANAGE_CONFIG and may rebind — to a base it can write. The KB
    # owner is a *knowledge* fact, independent of the project role: the owner's KB
    # stays out of reach (that is the 403 case above, seen from the other side).
    admin_kb = _make_kb(services, owner_user_id=admin.id, name="Admin-KB")
    assert service.update_project(project.id, user=admin, kb_id=admin_kb).kb_id == admin_kb
    with pytest.raises(OctopError) as err:
        service.update_project(project.id, user=admin, kb_id=kb_id)
    assert err.value.code is ErrorCode.PROJECT_KB_FORBIDDEN
    assert err.value.status == 403


def test_kb_rebind_on_an_archived_project_is_forbidden(
    service: ProjectService, services: SimpleNamespace, owner: Actor
) -> None:
    project = service.create_project(owner_user=owner, name="Alpha")
    service.transition_project(project.id, user=owner, target="active")
    service.transition_project(project.id, user=owner, target="archived")
    kb_id = _make_kb(services, owner_user_id=owner.id, name="Late-KB")

    with pytest.raises(OctopError) as err:
        service.update_project(project.id, user=owner, kb_id=kb_id)
    assert err.value.code is ErrorCode.PROJECT_FORBIDDEN
    assert err.value.status == 403
    assert err.value.status != 500
