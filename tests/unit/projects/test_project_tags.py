"""Project tag definitions and task links (PLAN.md §4, T-TAGS).

The tag subsystem exists to be *used*, so these tests do not stop at "the table
exists": they drive definition → link → read and then assert the stored rows,
because this repository has twice shipped a table that nothing read (the
``project_rooms`` dead schema).

Rejection codes are asserted together with their HTTP status — an unknown enum
value must be a 4xx, never a 500.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.agents import AgentRepo
from octop.infra.db.repos.knowledge import KnowledgeRepo
from octop.infra.db.repos.project_tags import ProjectTagRepo, ProjectTagRow
from octop.infra.db.repos.project_tasks import ProjectTaskRepo, TimelineRepo
from octop.infra.db.repos.projects import ProjectMemberRepo, ProjectRepo
from octop.infra.db.repos.settings import SettingsRepo
from octop.infra.db.repos.threads import ThreadRepo
from octop.infra.db.repos.users import UserRepo
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.knowledge import service as knowledge_service_module
from octop.infra.projects import service as project_service_module
from octop.infra.projects.service import ProjectService
from octop.infra.projects.tags import (
    TAG_NAME_MAX_LENGTH,
    ProjectTagService,
    normalize_tag_color,
    normalize_tag_name,
)
from octop.infra.utils.paths import PathLayout


class Actor:
    def __init__(
        self, user_id: int, *, admin: bool = False, permissions: list[str] | None = None
    ) -> None:
        self.id = user_id
        self._admin = admin
        self.permissions = ["projects", "knowledge_bases"] if permissions is None else permissions

    @property
    def is_admin(self) -> bool:
        return self._admin


@pytest.fixture
def services(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path / "home"))
    pool = SqlitePool(tmp_path / "octop.db")
    run_migrations(pool)
    monkeypatch.setattr(knowledge_service_module, "assert_knowledge_usable", lambda *_a: None)
    monkeypatch.setattr(
        project_service_module, "get_capability", lambda *_a, **_k: {"usable": True}
    )
    return SimpleNamespace(
        db=pool,
        project_repo=ProjectRepo(pool),
        project_member_repo=ProjectMemberRepo(pool),
        project_task_repo=ProjectTaskRepo(pool),
        project_tag_repo=ProjectTagRepo(pool),
        timeline_repo=TimelineRepo(pool),
        knowledge_repo=KnowledgeRepo(pool),
        settings_repo=SettingsRepo(pool),
        user_repo=UserRepo(pool),
        agent_repo=AgentRepo(pool),
        thread_repo=ThreadRepo(pool),
        paths=PathLayout.from_env(),
    )


@pytest.fixture
def project_service(services: SimpleNamespace) -> ProjectService:
    return ProjectService(services)


@pytest.fixture
def service(services: SimpleNamespace, project_service: ProjectService) -> ProjectTagService:
    return ProjectTagService(services, project_service=project_service)


@pytest.fixture
def owner(services: SimpleNamespace) -> Actor:
    return Actor(services.user_repo.create(username="owner", password_hash="h", role="user"))


@pytest.fixture
def project(project_service: ProjectService, owner: Actor) -> Any:
    return project_service.create_project(owner_user=owner, name="Alpha")


@pytest.fixture
def task(project_service: ProjectService, project: Any, owner: Actor) -> Any:
    return project_service.create_task(project.id, user=owner, title="Draft the plan")


def _expect_code(exc_info: pytest.ExceptionInfo[OctopError], code: ErrorCode, status: int) -> None:
    assert exc_info.value.code is code
    assert exc_info.value.status == status
    assert exc_info.value.status != 500, "a rejected tag request must never be a server error"


# ── definition CRUD (happy path) ─────────────────────────────────────────────


def test_tag_definition_crud_round_trip(
    service: ProjectTagService, project: Any, owner: Actor
) -> None:
    created = service.create_tag(project.id, user=owner, name="  urgent  ", color="#AABBCC")
    assert created.name == "urgent", "name is trimmed before storing"
    assert created.color == "#aabbcc", "colour is normalised to lower case"
    assert created.project_id == project.id

    listed = service.list_tags(project.id, user=owner)
    assert [t.tag_id for t in listed] == [created.tag_id]

    renamed = service.update_tag(
        project.id, created.tag_id, user=owner, name="blocker", color="#112233"
    )
    assert (renamed.name, renamed.color) == ("blocker", "#112233")

    # A patch that omits `color` must leave it alone.
    assert (
        service.update_tag(project.id, created.tag_id, user=owner, name="later").color == "#112233"
    )

    # An explicit empty colour clears it.
    assert service.update_tag(project.id, created.tag_id, user=owner, color="").color == ""

    assert service.delete_tag(project.id, created.tag_id, user=owner) is True
    assert service.list_tags(project.id, user=owner) == []
    # Deleting it again is an unknown tag, which is the same frozen 409 as
    # every other "does not exist or is not mine" tag rejection.
    with pytest.raises(OctopError) as err:
        service.delete_tag(project.id, created.tag_id, user=owner)
    _expect_code(err, ErrorCode.PROJECT_TASK_TAG_INVALID, 409)


def test_tag_color_may_be_empty(service: ProjectTagService, project: Any, owner: Actor) -> None:
    assert service.create_tag(project.id, user=owner, name="plain").color == ""


# ── validation ───────────────────────────────────────────────────────────────


def test_duplicate_tag_name_is_rejected_with_409(
    service: ProjectTagService, project: Any, owner: Actor
) -> None:
    service.create_tag(project.id, user=owner, name="urgent")
    with pytest.raises(OctopError) as err:
        service.create_tag(project.id, user=owner, name="urgent")
    _expect_code(err, ErrorCode.PROJECT_TASK_TAG_INVALID, 409)


def test_renaming_onto_an_existing_name_is_rejected(
    service: ProjectTagService, project: Any, owner: Actor
) -> None:
    service.create_tag(project.id, user=owner, name="urgent")
    other = service.create_tag(project.id, user=owner, name="later")
    with pytest.raises(OctopError) as err:
        service.update_tag(project.id, other.tag_id, user=owner, name="urgent")
    _expect_code(err, ErrorCode.PROJECT_TASK_TAG_INVALID, 409)


def test_renaming_a_tag_to_its_own_name_is_allowed(
    service: ProjectTagService, project: Any, owner: Actor
) -> None:
    tag = service.create_tag(project.id, user=owner, name="urgent")
    assert service.update_tag(project.id, tag.tag_id, user=owner, name="urgent").name == "urgent"


def test_the_same_name_is_independent_per_project(
    project_service: ProjectService, service: ProjectTagService, owner: Actor, project: Any
) -> None:
    other_project = project_service.create_project(owner_user=owner, name="Beta")
    service.create_tag(project.id, user=owner, name="urgent")
    # Same name, different project: not a collision (UNIQUE is per project).
    assert service.create_tag(other_project.id, user=owner, name="urgent").name == "urgent"


@pytest.mark.parametrize("bad_name", ["", "   ", "x" * (TAG_NAME_MAX_LENGTH + 1)])
def test_invalid_tag_name_is_rejected_with_409(
    service: ProjectTagService, project: Any, owner: Actor, bad_name: str
) -> None:
    with pytest.raises(OctopError) as err:
        service.create_tag(project.id, user=owner, name=bad_name)
    _expect_code(err, ErrorCode.PROJECT_TASK_TAG_INVALID, 409)


def test_name_at_the_length_limit_is_accepted(
    service: ProjectTagService, project: Any, owner: Actor
) -> None:
    name = "x" * TAG_NAME_MAX_LENGTH
    assert service.create_tag(project.id, user=owner, name=name).name == name


@pytest.mark.parametrize("bad_color", ["red", "#12345", "#1234567", "112233", "#GGGGGG"])
def test_invalid_tag_color_is_rejected_with_409(
    service: ProjectTagService, project: Any, owner: Actor, bad_color: str
) -> None:
    with pytest.raises(OctopError) as err:
        service.create_tag(project.id, user=owner, name="urgent", color=bad_color)
    _expect_code(err, ErrorCode.PROJECT_TASK_TAG_INVALID, 409)


def test_normalize_helpers_are_the_single_source() -> None:
    assert normalize_tag_name(" a ") == "a"
    assert normalize_tag_color(" #AbCdEf ") == "#abcdef"
    assert normalize_tag_color("") == ""
    with pytest.raises(OctopError):
        normalize_tag_name("")
    with pytest.raises(OctopError):
        normalize_tag_color("blue")


# ── task links: the write path actually stores rows ──────────────────────────


def test_task_tags_are_stored_and_read_back(
    services: SimpleNamespace, service: ProjectTagService, project: Any, owner: Actor, task: Any
) -> None:
    urgent = service.create_tag(project.id, user=owner, name="urgent", color="#ff0000")
    later = service.create_tag(project.id, user=owner, name="later")

    resolved = service.set_task_tags(
        project.id, task.id, user=owner, tag_ids=[urgent.tag_id, later.tag_id]
    )
    assert [t.tag_id for t in resolved] == [urgent.tag_id, later.tag_id], "created_at order"

    # ★ "table has data": one definition row AND one link row, read back from the DB.
    repo: ProjectTagRepo = services.project_tag_repo
    assert repo.count_links_for_task(task.id) == 2
    assert len(repo.list_tags_for_tasks([task.id])[task.id]) == 2

    # The whole set is replaced: `later` is detached, `urgent` stays.
    replaced = service.set_task_tags(project.id, task.id, user=owner, tag_ids=[urgent.tag_id])
    assert [t.tag_id for t in replaced] == [urgent.tag_id]
    assert repo.count_links_for_task(task.id) == 1

    # An empty set detaches everything.
    assert service.set_task_tags(project.id, task.id, user=owner, tag_ids=[]) == []
    assert repo.count_links_for_task(task.id) == 0


def test_replace_keeps_the_link_created_at_of_kept_tags(
    services: SimpleNamespace, service: ProjectTagService, project: Any, owner: Actor, task: Any
) -> None:
    first = service.create_tag(project.id, user=owner, name="first")
    second = service.create_tag(project.id, user=owner, name="second")
    service.set_task_tags(project.id, task.id, user=owner, tag_ids=[first.tag_id])
    service.set_task_tags(project.id, task.id, user=owner, tag_ids=[first.tag_id, second.tag_id])
    # `first` was never removed, so it must still sort ahead of `second`.
    assert services.project_tag_repo.list_tag_ids_for_task(task.id) == [
        first.tag_id,
        second.tag_id,
    ]


def test_duplicate_tag_in_one_request_is_rejected_with_409(
    service: ProjectTagService, project: Any, owner: Actor, task: Any
) -> None:
    tag = service.create_tag(project.id, user=owner, name="urgent")
    with pytest.raises(OctopError) as err:
        service.set_task_tags(project.id, task.id, user=owner, tag_ids=[tag.tag_id, tag.tag_id])
    _expect_code(err, ErrorCode.PROJECT_TASK_TAG_INVALID, 409)


def test_unknown_tag_id_is_rejected_with_409(
    service: ProjectTagService, project: Any, owner: Actor, task: Any
) -> None:
    with pytest.raises(OctopError) as err:
        service.set_task_tags(project.id, task.id, user=owner, tag_ids=["ZZZZZZ"])
    _expect_code(err, ErrorCode.PROJECT_TASK_TAG_INVALID, 409)


def test_tag_from_another_project_is_rejected_with_409(
    project_service: ProjectService,
    service: ProjectTagService,
    owner: Actor,
    project: Any,
    task: Any,
) -> None:
    other_project = project_service.create_project(owner_user=owner, name="Beta")
    foreign = service.create_tag(other_project.id, user=owner, name="urgent")

    # The tag exists — but not in *this* project, so it must be refused.
    with pytest.raises(OctopError) as err:
        service.set_task_tags(project.id, task.id, user=owner, tag_ids=[foreign.tag_id])
    _expect_code(err, ErrorCode.PROJECT_TASK_TAG_INVALID, 409)


def test_tag_operations_scoped_by_project_reject_a_foreign_tag_id(
    project_service: ProjectService, service: ProjectTagService, owner: Actor, project: Any
) -> None:
    other_project = project_service.create_project(owner_user=owner, name="Beta")
    foreign = service.create_tag(other_project.id, user=owner, name="urgent")

    for call in (
        lambda: service.update_tag(project.id, foreign.tag_id, user=owner, name="x"),
        lambda: service.delete_tag(project.id, foreign.tag_id, user=owner),
    ):
        with pytest.raises(OctopError) as err:
            call()
        _expect_code(err, ErrorCode.PROJECT_TASK_TAG_INVALID, 409)
    # The foreign tag survived both attempts.
    assert [t.tag_id for t in service.list_tags(other_project.id, user=owner)] == [foreign.tag_id]


def test_task_of_another_project_is_not_found(
    project_service: ProjectService, service: ProjectTagService, owner: Actor, project: Any
) -> None:
    other_project = project_service.create_project(owner_user=owner, name="Beta")
    other_task = project_service.create_task(other_project.id, user=owner, title="Elsewhere")
    tag = service.create_tag(project.id, user=owner, name="urgent")
    with pytest.raises(OctopError) as err:
        service.set_task_tags(project.id, other_task.id, user=owner, tag_ids=[tag.tag_id])
    assert err.value.code is ErrorCode.PROJECT_TASK_NOT_FOUND
    assert err.value.status == 404


# ── cascade: deleting a definition leaves no orphan link ─────────────────────


def test_deleting_a_tag_cascades_its_links(
    services: SimpleNamespace, service: ProjectTagService, project: Any, owner: Actor, task: Any
) -> None:
    kept = service.create_tag(project.id, user=owner, name="kept")
    doomed = service.create_tag(project.id, user=owner, name="doomed")
    service.set_task_tags(project.id, task.id, user=owner, tag_ids=[kept.tag_id, doomed.tag_id])

    repo: ProjectTagRepo = services.project_tag_repo
    assert repo.count_links_for_tag(doomed.tag_id) == 1

    assert service.delete_tag(project.id, doomed.tag_id, user=owner) is True

    # ★ the link row is gone — not merely hidden by a join
    assert repo.count_links_for_tag(doomed.tag_id) == 0, "the link must cascade away"
    assert repo.count_orphan_links() == 0, "no link may outlive its definition"
    # The other tag on the same task is untouched.
    assert repo.list_tag_ids_for_task(task.id) == [kept.tag_id]


def test_deleting_a_task_cascades_its_links(
    services: SimpleNamespace,
    project_service: ProjectService,
    service: ProjectTagService,
    project: Any,
    owner: Actor,
    task: Any,
) -> None:
    tag = service.create_tag(project.id, user=owner, name="urgent")
    service.set_task_tags(project.id, task.id, user=owner, tag_ids=[tag.tag_id])
    repo: ProjectTagRepo = services.project_tag_repo
    assert repo.count_links_for_task(task.id) == 1

    assert project_service.delete_task(project.id, task.id, user=owner) is True
    assert repo.count_links_for_task(task.id) == 0
    assert repo.count_orphan_links() == 0


# ── batch read (N+1 guard) ───────────────────────────────────────────────────


def test_resolve_task_tags_batches_many_tasks(
    service: ProjectTagService, project_service: ProjectService, project: Any, owner: Actor
) -> None:
    tag = service.create_tag(project.id, user=owner, name="urgent")
    first = project_service.create_task(project.id, user=owner, title="one")
    second = project_service.create_task(project.id, user=owner, title="two")
    service.set_task_tags(project.id, first.id, user=owner, tag_ids=[tag.tag_id])

    grouped = service.resolve_task_tags([first.id, second.id])
    assert [t.tag_id for t in grouped[first.id]] == [tag.tag_id]
    assert grouped[second.id] == []
    assert service.resolve_task_tags([]) == {}


# ── permissions ──────────────────────────────────────────────────────────────


def test_viewer_cannot_write_tags_but_can_read_them(
    services: SimpleNamespace,
    project_service: ProjectService,
    service: ProjectTagService,
    project: Any,
    owner: Actor,
    task: Any,
) -> None:
    viewer = Actor(services.user_repo.create(username="viewer", password_hash="h", role="user"))
    project_service.add_member(
        project.id, user=owner, subject_type="user", subject_id=str(viewer.id), role="viewer"
    )
    tag = service.create_tag(project.id, user=owner, name="urgent")

    assert service.list_tags(project.id, user=viewer) != []

    for call in (
        lambda: service.create_tag(project.id, user=viewer, name="nope"),
        lambda: service.update_tag(project.id, tag.tag_id, user=viewer, name="nope"),
        lambda: service.delete_tag(project.id, tag.tag_id, user=viewer),
        lambda: service.set_task_tags(project.id, task.id, user=viewer, tag_ids=[tag.tag_id]),
    ):
        with pytest.raises(OctopError) as err:
            call()
        # A viewer *is* a member, so the role table refuses the action; the
        # "not a member at all" case is PROJECT_FORBIDDEN (see the test below).
        assert err.value.code is ErrorCode.PROJECT_ROLE_FORBIDDEN
        assert err.value.status == 403


def test_non_member_is_refused_even_when_admin(
    services: SimpleNamespace, service: ProjectTagService, project: Any
) -> None:
    stranger = Actor(
        services.user_repo.create(username="stranger", password_hash="h", role="user"),
        admin=True,
    )
    for call in (
        lambda: service.list_tags(project.id, user=stranger),
        lambda: service.create_tag(project.id, user=stranger, name="urgent"),
    ):
        with pytest.raises(OctopError) as err:
            call()
        assert err.value.code is ErrorCode.PROJECT_FORBIDDEN
        assert err.value.status == 403, "membership is the boundary; admin is no exception"


def test_archived_project_refuses_tag_writes_but_allows_reads(
    project_service: ProjectService, service: ProjectTagService, project: Any, owner: Actor
) -> None:
    tag = service.create_tag(project.id, user=owner, name="urgent")
    project_service.transition_project(project.id, user=owner, target="active")
    project_service.transition_project(project.id, user=owner, target="archived")

    assert [t.tag_id for t in service.list_tags(project.id, user=owner)] == [tag.tag_id]
    with pytest.raises(OctopError) as err:
        service.create_tag(project.id, user=owner, name="later")
    assert err.value.code is ErrorCode.PROJECT_FORBIDDEN
    assert err.value.status == 403


# ── read model ───────────────────────────────────────────────────────────────


def test_tag_row_carries_what_the_ui_needs(
    service: ProjectTagService, project: Any, owner: Actor
) -> None:
    row = service.create_tag(project.id, user=owner, name="urgent", color="#ff0000")
    assert isinstance(row, ProjectTagRow)
    assert (row.tag_id, row.name, row.color) == (row.tag_id, "urgent", "#ff0000")
    assert row.created_by == owner.id
