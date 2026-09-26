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
from octop.infra.db.repos.projects import (
    MEMBER_SUBJECT_AGENT,
    MEMBER_SUBJECT_USER,
    ProjectMemberRepo,
    ProjectRepo,
    ProjectTaskRepo,
)
from octop.infra.db.repos.settings import SettingsRepo
from octop.infra.db.repos.users import UserRepo
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.knowledge import service as knowledge_service_module
from octop.infra.knowledge.service import MAX_BASES_PER_OWNER
from octop.infra.projects import service as project_service_module
from octop.infra.projects.service import (
    PROJECT_ARCHIVE,
    PROJECT_CONFIRM,
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
    return SimpleNamespace(
        db=pool,
        project_repo=ProjectRepo(pool),
        project_member_repo=ProjectMemberRepo(pool),
        project_task_repo=ProjectTaskRepo(pool),
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
    assert err.value.code is ErrorCode.FORBIDDEN


def test_create_project_requires_the_knowledge_bases_permission(
    service: ProjectService, services: SimpleNamespace
) -> None:
    """Creating a project creates a KB, so the feature must be available up front.

    Checking here keeps step ③ from failing after ①② already wrote rows.
    """
    actor = Actor(1, permissions=["projects"])
    with pytest.raises(OctopError) as err:
        service.create_project(owner_user=actor, name="Alpha")
    assert err.value.code is ErrorCode.FORBIDDEN
    assert services.project_repo.list_by_owner(1) == []
    assert services.knowledge_repo.count_bases_for_owner(1) == 0


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
            assert err.value.code is ErrorCode.FORBIDDEN

    assert service.assert_project_role(project.id, user=member, required=PROJECT_WRITE)
    with pytest.raises(OctopError):
        service.assert_project_role(project.id, user=member, required=PROJECT_CONFIRM)

    assert service.assert_project_role(project.id, user=proj_admin, required=PROJECT_CONFIRM)
    assert service.assert_project_role(project.id, user=proj_admin, required=PROJECT_MANAGE_MEMBERS)
    with pytest.raises(OctopError) as err:
        service.assert_project_role(project.id, user=proj_admin, required=PROJECT_ARCHIVE)
    assert err.value.code is ErrorCode.FORBIDDEN, "admin must not archive"

    assert service.assert_project_role(project.id, user=owner, required=PROJECT_ARCHIVE)


def test_non_member_is_rejected_even_when_a_platform_admin(
    service: ProjectService, services: SimpleNamespace, owner: Actor
) -> None:
    project = make_project(service, owner)
    outsider = Actor(
        services.user_repo.create(username="outsider", password_hash="h", role="admin"), admin=True
    )

    with pytest.raises(OctopError) as err:
        service.assert_project_role(project.id, user=outsider, required=PROJECT_READ)
    assert err.value.code is ErrorCode.FORBIDDEN


def test_unknown_action_is_a_programming_error(service: ProjectService, owner: Actor) -> None:
    project = make_project(service, owner)
    with pytest.raises(ValueError, match="unknown project action"):
        service.assert_project_role(project.id, user=owner, required="teleport")


def test_missing_project_is_not_found(service: ProjectService, owner: Actor) -> None:
    with pytest.raises(OctopError) as err:
        service.get_project("nope", user=owner)
    assert err.value.code is ErrorCode.NOT_FOUND


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
    assert err.value.code is ErrorCode.PROJECT_INVALID_TRANSITION
    assert service.get_project(project.id, user=owner).status == "draft"


def test_archived_is_terminal(service: ProjectService, owner: Actor) -> None:
    project = make_project(service, owner)
    service.transition_project(project.id, user=owner, target="active")
    service.transition_project(project.id, user=owner, target="archived")

    for target in ("active", "paused", "archived"):
        with pytest.raises(OctopError) as err:
            service.transition_project(project.id, user=owner, target=target)
        assert err.value.code in {
            ErrorCode.PROJECT_INVALID_TRANSITION,
            ErrorCode.FORBIDDEN,
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
    assert err.value.code is ErrorCode.FORBIDDEN
    with pytest.raises(OctopError) as err:
        service.add_member(
            project.id,
            user=owner,
            subject_type=MEMBER_SUBJECT_AGENT,
            subject_id="agent-1",
        )
    assert err.value.code is ErrorCode.FORBIDDEN


def test_activation_requires_at_least_one_member(
    service: ProjectService, services: SimpleNamespace, owner: Actor
) -> None:
    project = make_project(service, owner)
    # Drop the owner membership behind the service's back to reach the empty state.
    services.project_member_repo.remove(project.id, MEMBER_SUBJECT_USER, str(owner.id))

    with pytest.raises(OctopError) as err:
        service.transition_project(project.id, user=owner, target="active")
    assert err.value.code is ErrorCode.PROJECT_INVALID_TRANSITION


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
    assert err.value.code is ErrorCode.PROJECT_INVALID_TRANSITION


def test_unknown_status_is_a_programming_error(service: ProjectService, owner: Actor) -> None:
    project = make_project(service, owner)
    with pytest.raises(ValueError, match="unknown project status"):
        service.transition_project(project.id, user=owner, target="exploded")


# ── membership guards ────────────────────────────────────────────────────────


def test_owner_cannot_be_removed(service: ProjectService, owner: Actor) -> None:
    project = make_project(service, owner)
    with pytest.raises(OctopError) as err:
        service.remove_member(
            project.id, user=owner, subject_type=MEMBER_SUBJECT_USER, subject_id=str(owner.id)
        )
    assert err.value.code is ErrorCode.PROJECT_INVALID_TRANSITION


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
    assert err.value.code is ErrorCode.PROJECT_INVALID_TRANSITION


def test_unknown_role_is_rejected(service: ProjectService, owner: Actor) -> None:
    project = make_project(service, owner)
    with pytest.raises(ValueError, match="unknown project role"):
        service.add_member(
            project.id,
            user=owner,
            subject_type=MEMBER_SUBJECT_AGENT,
            subject_id="agent-1",
            role="wizard",
        )


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
    assert err.value.code is ErrorCode.FORBIDDEN


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
    assert err.value.code is ErrorCode.FORBIDDEN


def test_delete_project_requires_owner(
    service: ProjectService, services: SimpleNamespace, owner: Actor
) -> None:
    project = make_project(service, owner)
    proj_admin = Actor(owner.id + 102)
    add_member(service, project.id, actor=owner, subject_id=str(proj_admin.id), role="admin")

    with pytest.raises(OctopError) as err:
        service.delete_project(project.id, user=proj_admin)
    assert err.value.code is ErrorCode.FORBIDDEN

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
