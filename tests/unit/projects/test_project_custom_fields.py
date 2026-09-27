"""Project custom fields: the four rings and the data-safety rules (PLAN.md §6).

The rings are asserted in order — ① define, ② enter, ③ read — and each one ends
with a count taken from the database rather than from the returned object. This
repository has twice shipped a table nothing read (``project_rooms``), so "the
table exists" is explicitly **not** accepted as evidence here.

The S-2 case is the other half of the point: dropping a ``select`` option that
stored values still reference must be refused *and* must leave those values
untouched, because silently destroying user data is the failure mode.
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
from octop.infra.db.repos.project_custom_fields import (
    CUSTOM_FIELD_TYPES,
    ProjectCustomFieldRepo,
    ProjectCustomFieldRow,
)
from octop.infra.db.repos.project_tasks import ProjectTaskRepo, TimelineRepo
from octop.infra.db.repos.projects import ProjectMemberRepo, ProjectRepo
from octop.infra.db.repos.settings import SettingsRepo
from octop.infra.db.repos.threads import ThreadRepo
from octop.infra.db.repos.users import UserRepo
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.knowledge import service as knowledge_service_module
from octop.infra.projects import service as project_service_module
from octop.infra.projects.custom_fields import (
    CUSTOM_FIELD_LABEL_MAX_LENGTH,
    CUSTOM_FIELD_OPTION_MAX_LENGTH,
    CUSTOM_FIELD_TEXT_MAX_LENGTH,
    CUSTOM_FIELD_TIMESTAMP_MAX,
    ProjectCustomFieldService,
    normalize_field_key,
    normalize_field_options,
    normalize_field_type,
    normalize_field_value,
)
from octop.infra.projects.service import ProjectService
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
        project_custom_field_repo=ProjectCustomFieldRepo(pool),
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
def service(
    services: SimpleNamespace, project_service: ProjectService
) -> ProjectCustomFieldService:
    return ProjectCustomFieldService(services, project_service=project_service)


@pytest.fixture
def owner(services: SimpleNamespace) -> Actor:
    return Actor(services.user_repo.create(username="owner", password_hash="h", role="user"))


@pytest.fixture
def project(project_service: ProjectService, owner: Actor) -> Any:
    return project_service.create_project(owner_user=owner, name="Alpha")


@pytest.fixture
def task(project_service: ProjectService, project: Any, owner: Actor) -> Any:
    return project_service.create_task(project.id, user=owner, title="Draft the plan")


def _expect(exc_info: pytest.ExceptionInfo[OctopError], code: ErrorCode, status: int) -> None:
    assert exc_info.value.code is code
    assert exc_info.value.status == status
    assert exc_info.value.status != 500, "a rejected metadata request must never be a server error"


def _define(
    service: ProjectCustomFieldService, project: Any, owner: Actor, **kwargs: Any
) -> ProjectCustomFieldRow:
    payload: dict[str, Any] = {"key": "estimate", "label": "Estimate", "type": "text"}
    payload.update(kwargs)
    return service.create_field(project.id, user=owner, **payload)


# ── ① definition ring ────────────────────────────────────────────────────────


def test_field_definition_crud_round_trip(
    service: ProjectCustomFieldService, project: Any, owner: Actor
) -> None:
    created = _define(service, project, owner, key="  estimate  ", label="  Estimate  ")
    assert created.key == "estimate", "key is trimmed before storing"
    assert created.label == "Estimate", "label is trimmed before storing"
    assert created.required is False
    assert created.options == []
    assert created.project_id == project.id

    assert [f.field_id for f in service.list_fields(project.id, user=owner)] == [created.field_id]

    patched = service.update_field(
        project.id, created.field_id, user=owner, label="Story points", required=True
    )
    assert (patched.label, patched.required) == ("Story points", True)

    # Omitting a field leaves it alone.
    assert (
        service.update_field(project.id, created.field_id, user=owner, label="SP").required is True
    )

    assert service.delete_field(project.id, created.field_id, user=owner) is True
    assert service.list_fields(project.id, user=owner) == []


def test_definitions_keep_sort_order(
    service: ProjectCustomFieldService, project: Any, owner: Actor
) -> None:
    first = _define(service, project, owner, key="first", label="First")
    second = _define(service, project, owner, key="second", label="Second")
    assert [f.key for f in service.list_fields(project.id, user=owner)] == ["first", "second"]
    assert (first.sort_order, second.sort_order) == (0, 1)

    service.update_field(project.id, second.field_id, user=owner, sort_order=-1)
    assert [f.key for f in service.list_fields(project.id, user=owner)] == ["second", "first"]


def test_the_four_types_are_exactly_what_the_contract_says() -> None:
    assert CUSTOM_FIELD_TYPES == ("text", "number", "date", "select")
    for type_name in CUSTOM_FIELD_TYPES:
        assert normalize_field_type(type_name) == type_name


def test_unknown_field_type_is_rejected_with_409(
    service: ProjectCustomFieldService, project: Any, owner: Actor
) -> None:
    with pytest.raises(OctopError) as err:
        _define(service, project, owner, type="boolean")
    _expect(err, ErrorCode.PROJECT_CUSTOM_FIELD_INVALID, 409)


@pytest.mark.parametrize("bad_key", ["", "Estimate", "1st", "with-dash", "a" * 33, "key space"])
def test_invalid_field_key_is_rejected_with_409(
    service: ProjectCustomFieldService, project: Any, owner: Actor, bad_key: str
) -> None:
    with pytest.raises(OctopError) as err:
        _define(service, project, owner, key=bad_key)
    _expect(err, ErrorCode.PROJECT_CUSTOM_FIELD_INVALID, 409)


def test_key_at_the_length_limit_is_accepted(
    service: ProjectCustomFieldService, project: Any, owner: Actor
) -> None:
    key = "a" + "b" * 31
    assert _define(service, project, owner, key=key).key == key


@pytest.mark.parametrize("bad_label", ["", "   ", "x" * (CUSTOM_FIELD_LABEL_MAX_LENGTH + 1)])
def test_invalid_field_label_is_rejected_with_409(
    service: ProjectCustomFieldService, project: Any, owner: Actor, bad_label: str
) -> None:
    with pytest.raises(OctopError) as err:
        _define(service, project, owner, label=bad_label)
    _expect(err, ErrorCode.PROJECT_CUSTOM_FIELD_INVALID, 409)


def test_duplicate_field_key_is_rejected_with_409(
    service: ProjectCustomFieldService, project: Any, owner: Actor
) -> None:
    _define(service, project, owner, key="estimate")
    with pytest.raises(OctopError) as err:
        _define(service, project, owner, key="estimate")
    _expect(err, ErrorCode.PROJECT_CUSTOM_FIELD_INVALID, 409)


def test_the_same_key_is_independent_per_project(
    project_service: ProjectService, service: ProjectCustomFieldService, owner: Actor, project: Any
) -> None:
    other = project_service.create_project(owner_user=owner, name="Beta")
    _define(service, project, owner, key="estimate")
    assert _define(service, other, owner, key="estimate").project_id == other.id


# ── select option rules ──────────────────────────────────────────────────────


def test_select_field_stores_its_options(
    service: ProjectCustomFieldService, project: Any, owner: Actor
) -> None:
    field = _define(
        service,
        project,
        owner,
        key="stage",
        label="Stage",
        type="select",
        options=["todo", "doing"],
    )
    assert field.options == ["todo", "doing"]
    # Read back through the repo, not just the returned object.
    assert service.list_fields(project.id, user=owner)[0].options == ["todo", "doing"]


def test_select_without_options_is_rejected_with_409(
    service: ProjectCustomFieldService, project: Any, owner: Actor
) -> None:
    with pytest.raises(OctopError) as err:
        _define(service, project, owner, type="select")
    _expect(err, ErrorCode.PROJECT_CUSTOM_FIELD_INVALID, 409)


@pytest.mark.parametrize(
    "bad_options",
    [
        [],
        [""],
        ["  "],
        ["a", "a"],
        ["x" * (CUSTOM_FIELD_OPTION_MAX_LENGTH + 1)],
        [str(index) for index in range(51)],
    ],
)
def test_invalid_select_options_are_rejected_with_409(
    service: ProjectCustomFieldService, project: Any, owner: Actor, bad_options: list[str]
) -> None:
    with pytest.raises(OctopError) as err:
        _define(service, project, owner, type="select", options=bad_options)
    _expect(err, ErrorCode.PROJECT_CUSTOM_FIELD_INVALID, 409)


def test_options_on_a_non_select_field_are_rejected_with_409(
    service: ProjectCustomFieldService, project: Any, owner: Actor
) -> None:
    for type_name in ("text", "number", "date"):
        with pytest.raises(OctopError) as err:
            _define(service, project, owner, type=type_name, options=["a"])
        _expect(err, ErrorCode.PROJECT_CUSTOM_FIELD_INVALID, 409)


def test_normalize_helpers_are_the_single_source() -> None:
    assert normalize_field_key(" ok_1 ") == "ok_1"
    assert normalize_field_options("select", [" a ", "b"]) == ["a", "b"]
    assert normalize_field_options("text", []) == []
    for call in (
        lambda: normalize_field_key("Bad"),
        lambda: normalize_field_type("nope"),
        lambda: normalize_field_options("select", []),
        lambda: normalize_field_options("text", ["a"]),
    ):
        with pytest.raises(OctopError):
            call()


# ── type / key immutability, last-write-wins ─────────────────────────────────


@pytest.mark.parametrize("immutable", [{"type": "number"}, {"key": "other"}])
def test_type_and_key_cannot_be_changed(
    service: ProjectCustomFieldService, project: Any, owner: Actor, immutable: dict[str, str]
) -> None:
    field = _define(service, project, owner)
    with pytest.raises(OctopError) as err:
        service.update_field(project.id, field.field_id, user=owner, **immutable)
    _expect(err, ErrorCode.PROJECT_CUSTOM_FIELD_INVALID, 409)
    # Unchanged on disk.
    assert service.list_fields(project.id, user=owner)[0].key == "estimate"


def test_concurrent_definition_edits_are_last_write_wins(
    service: ProjectCustomFieldService, project: Any, owner: Actor
) -> None:
    """S-12: no version column, no optimistic lock — the later write simply wins."""
    field = _define(service, project, owner)
    service.update_field(project.id, field.field_id, user=owner, label="First")
    service.update_field(project.id, field.field_id, user=owner, label="Second")
    assert service.list_fields(project.id, user=owner)[0].label == "Second"


# ── ② entry ring: the four types, one positive and one negative each ─────────


def test_text_value_is_stored_verbatim_and_length_checked_on_the_trimmed_form(
    service: ProjectCustomFieldService, project: Any, owner: Actor, task: Any
) -> None:
    field = _define(service, project, owner, key="note", label="Note", type="text")
    stored = service.set_task_values(
        project.id, task.id, user=owner, values={field.field_id: "  hello  "}
    )
    assert stored == {field.field_id: "  hello  "}, "the original string is stored"

    exact = "x" * CUSTOM_FIELD_TEXT_MAX_LENGTH
    assert service.set_task_values(
        project.id, task.id, user=owner, values={field.field_id: exact}
    ) == {field.field_id: exact}

    with pytest.raises(OctopError) as err:
        service.set_task_values(
            project.id,
            task.id,
            user=owner,
            values={field.field_id: "x" * (CUSTOM_FIELD_TEXT_MAX_LENGTH + 1)},
        )
    _expect(err, ErrorCode.PROJECT_CUSTOM_FIELD_VALUE_INVALID, 400)

    with pytest.raises(OctopError) as err:
        service.set_task_values(project.id, task.id, user=owner, values={field.field_id: 5})
    _expect(err, ErrorCode.PROJECT_CUSTOM_FIELD_VALUE_INVALID, 400)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(3, "3"), (3.0, "3"), (3.5, "3.5"), ("42", "42"), (" 2.5 ", "2.5")],
)
def test_number_values_are_normalised(
    service: ProjectCustomFieldService,
    project: Any,
    owner: Actor,
    task: Any,
    raw: object,
    expected: str,
) -> None:
    field = _define(service, project, owner, key="points", label="Points", type="number")
    stored = service.set_task_values(project.id, task.id, user=owner, values={field.field_id: raw})
    assert stored == {field.field_id: expected}


@pytest.mark.parametrize("bad", [True, False, "abc", "", None, [], {}])
def test_invalid_number_values_are_rejected_with_400(
    service: ProjectCustomFieldService, project: Any, owner: Actor, task: Any, bad: object
) -> None:
    field = _define(service, project, owner, key="points", label="Points", type="number")
    with pytest.raises(OctopError) as err:
        service.set_task_values(project.id, task.id, user=owner, values={field.field_id: bad})
    _expect(err, ErrorCode.PROJECT_CUSTOM_FIELD_VALUE_INVALID, 400)


def test_date_value_accepts_unix_seconds(
    service: ProjectCustomFieldService, project: Any, owner: Actor, task: Any
) -> None:
    field = _define(service, project, owner, key="sprint_end", label="Sprint end", type="date")
    stored = service.set_task_values(
        project.id, task.id, user=owner, values={field.field_id: 1767225600}
    )
    assert stored == {field.field_id: "1767225600"}


@pytest.mark.parametrize("bad", [0, -1, CUSTOM_FIELD_TIMESTAMP_MAX, 1.5, "1767225600", True])
def test_invalid_date_values_are_rejected_with_400(
    service: ProjectCustomFieldService, project: Any, owner: Actor, task: Any, bad: object
) -> None:
    field = _define(service, project, owner, key="sprint_end", label="Sprint end", type="date")
    with pytest.raises(OctopError) as err:
        service.set_task_values(project.id, task.id, user=owner, values={field.field_id: bad})
    _expect(err, ErrorCode.PROJECT_CUSTOM_FIELD_VALUE_INVALID, 400)


def test_select_value_must_be_one_of_the_options(
    service: ProjectCustomFieldService, project: Any, owner: Actor, task: Any
) -> None:
    field = _define(
        service,
        project,
        owner,
        key="stage",
        label="Stage",
        type="select",
        options=["todo", "doing"],
    )
    assert service.set_task_values(
        project.id, task.id, user=owner, values={field.field_id: "doing"}
    ) == {field.field_id: "doing"}

    with pytest.raises(OctopError) as err:
        service.set_task_values(project.id, task.id, user=owner, values={field.field_id: "nope"})
    _expect(err, ErrorCode.PROJECT_CUSTOM_FIELD_VALUE_INVALID, 400)


def test_normalize_field_value_rejects_an_unknown_stored_type() -> None:
    bogus = ProjectCustomFieldRow(
        pk=1,
        field_id="AAAAAA",
        project_id="P",
        key="k",
        label="l",
        type="wat",
        required=False,
        options=[],
        sort_order=0,
        created_by=1,
        created_at=0,
        updated_at=0,
    )
    with pytest.raises(OctopError) as err:
        normalize_field_value(bogus, "x")
    _expect(err, ErrorCode.PROJECT_CUSTOM_FIELD_VALUE_INVALID, 400)


# ── required semantics ───────────────────────────────────────────────────────


def test_put_always_validates_required(
    service: ProjectCustomFieldService, project: Any, owner: Actor, task: Any
) -> None:
    required = _define(service, project, owner, key="owner_name", label="Owner", required=True)
    optional = _define(service, project, owner, key="note", label="Note")

    with pytest.raises(OctopError) as err:
        service.set_task_values(project.id, task.id, user=owner, values={optional.field_id: "n"})
    _expect(err, ErrorCode.PROJECT_CUSTOM_FIELD_VALUE_INVALID, 400)

    assert service.set_task_values(
        project.id, task.id, user=owner, values={required.field_id: "alice"}
    ) == {required.field_id: "alice"}


def test_put_replaces_the_whole_value_set(
    service: ProjectCustomFieldService, project: Any, owner: Actor, task: Any
) -> None:
    first = _define(service, project, owner, key="first", label="First")
    second = _define(service, project, owner, key="second", label="Second")
    service.set_task_values(
        project.id, task.id, user=owner, values={first.field_id: "a", second.field_id: "b"}
    )
    # Omitting `first` detaches it.
    assert service.set_task_values(
        project.id, task.id, user=owner, values={second.field_id: "b"}
    ) == {second.field_id: "b"}


def test_apply_task_values_is_partial_but_still_checks_required(
    service: ProjectCustomFieldService, project: Any, owner: Actor, task: Any
) -> None:
    """The ``custom_fields`` passthrough used by create / patch."""
    required = _define(service, project, owner, key="owner_name", label="Owner", required=True)
    other = _define(service, project, owner, key="note", label="Note")

    # One field first, then a partial update: the sibling survives.
    service.apply_task_values(project.id, task.id, user=owner, values={required.field_id: "alice"})
    merged = service.apply_task_values(
        project.id, task.id, user=owner, values={other.field_id: "hi"}
    )
    assert merged == {required.field_id: "alice", other.field_id: "hi"}
    assert service.resolve_task_values([task.id])[task.id] == merged


def test_apply_task_values_refuses_when_a_required_value_is_still_missing(
    service: ProjectCustomFieldService, project: Any, owner: Actor, task: Any
) -> None:
    required = _define(service, project, owner, key="owner_name", label="Owner", required=True)
    other = _define(service, project, owner, key="note", label="Note")
    with pytest.raises(OctopError) as err:
        service.apply_task_values(project.id, task.id, user=owner, values={other.field_id: "hi"})
    _expect(err, ErrorCode.PROJECT_CUSTOM_FIELD_VALUE_INVALID, 400)
    # Nothing was written by the rejected call.
    assert service.resolve_task_values([task.id])[task.id] == {}
    assert required.field_id not in service.resolve_task_values([task.id])[task.id]


def test_validate_task_values_can_skip_the_completeness_check(
    service: ProjectCustomFieldService, project: Any, owner: Actor, task: Any
) -> None:
    required = _define(service, project, owner, key="owner_name", label="Owner", required=True)
    # require_complete=False only checks what was given.
    assert service.validate_task_values(project.id, {}, require_complete=False) == {}
    with pytest.raises(OctopError):
        service.validate_task_values(project.id, {}, require_complete=True)
    assert service.validate_task_values(
        project.id, {required.field_id: "alice"}, require_complete=False
    ) == {required.field_id: "alice"}


# ── ③ read ring, and the "table has data" evidence ───────────────────────────


def test_four_rings_end_to_end_with_real_rows(
    services: SimpleNamespace,
    service: ProjectCustomFieldService,
    project: Any,
    owner: Actor,
    task: Any,
) -> None:
    """① define ② enter ③ read ④ (shape handed to the UI), with DB counts."""
    repo: ProjectCustomFieldRepo = services.project_custom_field_repo

    # ① define
    stage = _define(
        service,
        project,
        owner,
        key="stage",
        label="Stage",
        type="select",
        options=["todo", "doing"],
    )
    points = _define(service, project, owner, key="points", label="Points", type="number")
    assert len(service.list_fields(project.id, user=owner)) == 2

    # ② enter
    written = service.set_task_values(
        project.id, task.id, user=owner, values={stage.field_id: "doing", points.field_id: 5}
    )
    assert written == {stage.field_id: "doing", points.field_id: "5"}

    # ★ "table has data": both tables carry real rows, read from the DB.
    assert repo.count_values_for_task(task.id) == 2, "project_task_field_values must hold rows"
    assert len(repo.list_by_project(project.id)) == 2, "project_custom_fields must hold rows"
    assert repo.count_orphan_values() == 0

    # ③ read
    definitions, values = service.get_task_fields(project.id, task.id, user=owner)
    assert [d.field_id for d in definitions] == [stage.field_id, points.field_id]
    assert values == {stage.field_id: "doing", points.field_id: "5"}

    # ④ the shape the UI renders: definitions carry label/type/options/required.
    rendered = {d.key: (d.label, d.type, d.options) for d in definitions}
    assert rendered["stage"] == ("Stage", "select", ["todo", "doing"])
    assert rendered["points"] == ("Points", "number", [])


def test_deleting_a_definition_cascades_its_values(
    services: SimpleNamespace,
    service: ProjectCustomFieldService,
    project: Any,
    owner: Actor,
    task: Any,
) -> None:
    doomed = _define(service, project, owner, key="doomed", label="Doomed")
    kept = _define(service, project, owner, key="kept", label="Kept")
    service.set_task_values(
        project.id, task.id, user=owner, values={doomed.field_id: "x", kept.field_id: "y"}
    )
    repo: ProjectCustomFieldRepo = services.project_custom_field_repo
    assert repo.count_values_for_field(doomed.field_id) == 1

    assert service.delete_field(project.id, doomed.field_id, user=owner) is True

    assert repo.count_values_for_field(doomed.field_id) == 0, "the value must cascade away"
    assert repo.count_orphan_values() == 0, "no value may outlive its definition"
    assert repo.count_values_for_task(task.id) == 1, "the sibling value is untouched"


def test_deleting_a_task_cascades_its_values(
    services: SimpleNamespace,
    project_service: ProjectService,
    service: ProjectCustomFieldService,
    project: Any,
    owner: Actor,
    task: Any,
) -> None:
    field = _define(service, project, owner, key="note", label="Note")
    service.set_task_values(project.id, task.id, user=owner, values={field.field_id: "x"})
    repo: ProjectCustomFieldRepo = services.project_custom_field_repo
    assert repo.count_values_for_task(task.id) == 1

    assert project_service.delete_task(project.id, task.id, user=owner) is True
    assert repo.count_values_for_task(task.id) == 0
    assert repo.count_orphan_values() == 0


def test_reading_a_task_without_values_returns_definitions_only(
    service: ProjectCustomFieldService, project: Any, owner: Actor, task: Any
) -> None:
    _define(service, project, owner, key="note", label="Note")
    definitions, values = service.get_task_fields(project.id, task.id, user=owner)
    assert len(definitions) == 1
    assert values == {}


def test_resolve_task_values_batches_many_tasks(
    service: ProjectCustomFieldService, project_service: ProjectService, project: Any, owner: Actor
) -> None:
    field = _define(service, project, owner, key="note", label="Note")
    first = project_service.create_task(project.id, user=owner, title="one")
    second = project_service.create_task(project.id, user=owner, title="two")
    service.set_task_values(project.id, first.id, user=owner, values={field.field_id: "x"})

    grouped = service.resolve_task_values([first.id, second.id])
    assert grouped[first.id] == {field.field_id: "x"}
    assert grouped[second.id] == {}
    assert service.resolve_task_values([]) == {}


# ── ★ S-2: an option that is still referenced cannot be removed ──────────────


def test_s2_removing_a_referenced_select_option_is_refused_and_keeps_the_values(
    services: SimpleNamespace,
    service: ProjectCustomFieldService,
    project: Any,
    owner: Actor,
    task: Any,
) -> None:
    field = _define(
        service,
        project,
        owner,
        key="stage",
        label="Stage",
        type="select",
        options=["todo", "doing", "done"],
    )
    service.set_task_values(project.id, task.id, user=owner, values={field.field_id: "doing"})
    repo: ProjectCustomFieldRepo = services.project_custom_field_repo
    assert repo.count_values_for_option(field.field_id, "doing") == 1

    # Dropping `doing` while a task still holds it must be refused.
    with pytest.raises(OctopError) as err:
        service.update_field(project.id, field.field_id, user=owner, options=["todo", "done"])
    _expect(err, ErrorCode.PROJECT_CUSTOM_FIELD_INVALID, 409)

    # ★ The stored value is still there — nothing was silently destroyed.
    stored = repo.list_values_for_task(task.id)
    assert stored == {field.field_id: "doing"}
    # ★ And the definition is untouched, so the value is still valid.
    assert service.list_fields(project.id, user=owner)[0].options == ["todo", "doing", "done"]


def test_s2_removing_an_unreferenced_option_is_allowed(
    service: ProjectCustomFieldService, project: Any, owner: Actor, task: Any
) -> None:
    field = _define(
        service,
        project,
        owner,
        key="stage",
        label="Stage",
        type="select",
        options=["todo", "doing", "done"],
    )
    service.set_task_values(project.id, task.id, user=owner, values={field.field_id: "doing"})
    # `done` is not referenced by any value, so it may go.
    updated = service.update_field(
        project.id, field.field_id, user=owner, options=["todo", "doing"]
    )
    assert updated.options == ["todo", "doing"]


def test_s2_clearing_the_value_first_then_removing_the_option_is_allowed(
    service: ProjectCustomFieldService, project: Any, owner: Actor, task: Any
) -> None:
    """The documented escape hatch: clear the values, then shrink the options."""
    field = _define(
        service,
        project,
        owner,
        key="stage",
        label="Stage",
        type="select",
        options=["todo", "doing"],
    )
    service.set_task_values(project.id, task.id, user=owner, values={field.field_id: "doing"})
    service.set_task_values(project.id, task.id, user=owner, values={})
    updated = service.update_field(project.id, field.field_id, user=owner, options=["todo"])
    assert updated.options == ["todo"]


# ── 404 / isolation ──────────────────────────────────────────────────────────


def test_unknown_field_id_is_not_found(
    service: ProjectCustomFieldService, project: Any, owner: Actor, task: Any
) -> None:
    for call in (
        lambda: service.set_task_values(project.id, task.id, user=owner, values={"ZZZZZZ": "x"}),
        lambda: service.update_field(project.id, "ZZZZZZ", user=owner, label="x"),
        lambda: service.delete_field(project.id, "ZZZZZZ", user=owner),
    ):
        with pytest.raises(OctopError) as err:
            call()
        _expect(err, ErrorCode.PROJECT_CUSTOM_FIELD_NOT_FOUND, 404)


def test_field_from_another_project_is_not_found(
    project_service: ProjectService,
    service: ProjectCustomFieldService,
    owner: Actor,
    project: Any,
    task: Any,
) -> None:
    other = project_service.create_project(owner_user=owner, name="Beta")
    foreign = _define(service, other, owner, key="stage", label="Stage")

    for call in (
        lambda: service.set_task_values(
            project.id, task.id, user=owner, values={foreign.field_id: "x"}
        ),
        lambda: service.update_field(project.id, foreign.field_id, user=owner, label="x"),
        lambda: service.delete_field(project.id, foreign.field_id, user=owner),
    ):
        with pytest.raises(OctopError) as err:
            call()
        _expect(err, ErrorCode.PROJECT_CUSTOM_FIELD_NOT_FOUND, 404)
    assert service.list_fields(other.id, user=owner) != []


def test_task_of_another_project_is_not_found(
    project_service: ProjectService, service: ProjectCustomFieldService, owner: Actor, project: Any
) -> None:
    other = project_service.create_project(owner_user=owner, name="Beta")
    other_task = project_service.create_task(other.id, user=owner, title="Elsewhere")
    field = _define(service, project, owner, key="note", label="Note")
    with pytest.raises(OctopError) as err:
        service.set_task_values(project.id, other_task.id, user=owner, values={field.field_id: "x"})
    assert err.value.code is ErrorCode.PROJECT_TASK_NOT_FOUND
    assert err.value.status == 404


def test_viewer_cannot_write_but_can_read(
    services: SimpleNamespace,
    project_service: ProjectService,
    service: ProjectCustomFieldService,
    project: Any,
    owner: Actor,
    task: Any,
) -> None:
    viewer = Actor(services.user_repo.create(username="viewer", password_hash="h", role="user"))
    project_service.add_member(
        project.id, user=owner, subject_type="user", subject_id=str(viewer.id), role="viewer"
    )
    field = _define(service, project, owner, key="note", label="Note")

    assert service.list_fields(project.id, user=viewer) != []
    assert service.get_task_fields(project.id, task.id, user=viewer)[1] == {}

    for call in (
        lambda: _define(service, project, viewer, key="new", label="New"),
        lambda: service.update_field(project.id, field.field_id, user=viewer, label="x"),
        lambda: service.delete_field(project.id, field.field_id, user=viewer),
        lambda: service.set_task_values(
            project.id, task.id, user=viewer, values={field.field_id: "x"}
        ),
    ):
        with pytest.raises(OctopError) as err:
            call()
        # A viewer is a member, so the role table refuses the action.
        assert err.value.code is ErrorCode.PROJECT_ROLE_FORBIDDEN
        assert err.value.status == 403


def test_non_member_is_refused_even_when_admin(
    services: SimpleNamespace, service: ProjectCustomFieldService, project: Any
) -> None:
    stranger = Actor(
        services.user_repo.create(username="stranger", password_hash="h", role="user"), admin=True
    )
    for call in (
        lambda: service.list_fields(project.id, user=stranger),
        lambda: _define(service, project, stranger, key="note", label="Note"),
    ):
        with pytest.raises(OctopError) as err:
            call()
        assert err.value.code is ErrorCode.PROJECT_FORBIDDEN
        assert err.value.status == 403, "membership is the boundary; admin is no exception"


def test_archived_project_refuses_writes_but_allows_reads(
    project_service: ProjectService, service: ProjectCustomFieldService, project: Any, owner: Actor
) -> None:
    field = _define(service, project, owner, key="note", label="Note")
    project_service.transition_project(project.id, user=owner, target="active")
    project_service.transition_project(project.id, user=owner, target="archived")

    assert [f.field_id for f in service.list_fields(project.id, user=owner)] == [field.field_id]
    with pytest.raises(OctopError) as err:
        _define(service, project, owner, key="later", label="Later")
    assert err.value.code is ErrorCode.PROJECT_FORBIDDEN
    assert err.value.status == 403
