"""Project skill declarations and the three-layer enumeration closure (PLAN.md §2).

The centrepiece is :func:`test_stopped_agent_still_sees_package_skills`. It is the
reason this module exists: neither built-in enumerator satisfies Q9 on its own —
the runtime path needs a loaded agent, the offline path cannot see mounted skill
packages — so the closure is asserted on a **real** ``AgentManager`` whose
``_harness_manager`` is absent, i.e. a genuinely stopped agent. The test first
proves the runtime path really is unavailable (it raises ``AGENT_NOT_RUNNING``),
so the skills it then finds can only come from the offline path with package
roots. A green assertion there is what stops ``project_skills`` from becoming the
next ``project_rooms``.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from octop.config import OctopConfig
from octop.infra.agents.manager import AgentManager
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.project_skills import ProjectSkillRepo
from octop.infra.db.services import build_shared_services
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.projects.service import ProjectService
from octop.infra.projects.skills import ProjectSkillService
from octop.infra.skills.workspace_catalog import list_workspace_skill_summaries
from octop.infra.utils.paths import PathLayout

AGENT_ID = "AGENT01"
PACKAGE_ID = "PACK01"


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


def _write_skill(root: Path, slug: str, *, name: str, description: str = "d") -> Path:
    skill_dir = root / slug
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\nbody for {slug}\n",
        encoding="utf-8",
    )
    return skill_dir


@pytest.fixture
def room(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """A real DB + real AgentManager + a real project with one agent member."""
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path / "home"))
    paths = PathLayout(tmp_path / ".octop")
    paths.ensure_root()
    db = SqlitePool(paths.db)
    run_migrations(db)
    services = build_shared_services(db=db, paths=paths, config=OctopConfig())
    manager = AgentManager(repos=services.repos, paths=services.paths)
    repo = ProjectSkillRepo(db)
    return SimpleNamespace(
        db=db, paths=paths, services=services, manager=manager, repo=repo, tmp=tmp_path
    )


@pytest.fixture
def project_service(room: SimpleNamespace) -> ProjectService:
    return ProjectService(room.services)


@pytest.fixture
def service(room: SimpleNamespace, project_service: ProjectService) -> ProjectSkillService:
    return ProjectSkillService(
        room.services,
        project_service=project_service,
        agent_manager=room.manager,
        skill_repo=room.repo,
    )


@pytest.fixture
def owner(room: SimpleNamespace) -> Actor:
    return Actor(
        room.services.repos.user_repo.create(username="owner", password_hash="h", role="user")
    )


@pytest.fixture
def project(project_service: ProjectService, owner: Actor) -> Any:
    return project_service.create_project(owner_user=owner, name="Alpha")


@pytest.fixture
def agent_member(
    room: SimpleNamespace, project_service: ProjectService, project: Any, owner: Actor
) -> str:
    """An agent row that is also a project member (subject_type='agent')."""
    room.services.repos.agent_repo.create(agent_id=AGENT_ID, user_id=owner.id, name="Expert")
    project_service.add_member(
        project.id, user=owner, subject_type="agent", subject_id=AGENT_ID, role="member"
    )
    return AGENT_ID


def _workspace_skills_dir(room: SimpleNamespace, agent_id: str) -> Path:
    root = room.manager.resolve_workspace_dir(agent_id) / "skills"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _mount_package(room: SimpleNamespace, agent_id: str, *, slug: str, name: str) -> Path:
    """Create a real skill package and mount it on the agent (persisted config)."""
    room.services.repos.skill_package_repo.create(id=PACKAGE_ID, name="Package", created_by="1")
    package_root = room.paths.skill_packages_dir / PACKAGE_ID / "skills"
    package_root.mkdir(parents=True, exist_ok=True)
    _write_skill(package_root, slug, name=name)
    cfg = room.manager.get_config(agent_id)
    cfg["skill_package_ids"] = [PACKAGE_ID]
    room.services.repos.agent_repo.update_config(agent_id, config_json=json.dumps(cfg))
    return package_root


# ── the closure: a stopped agent must still see package skills ───────────────


@pytest.mark.asyncio
async def test_stopped_agent_still_sees_package_skills(
    room: SimpleNamespace, service: ProjectSkillService, agent_member: str
) -> None:
    """R21-3 gate: layer 1 is unavailable, layer 3 supplies the package skill."""
    _write_skill(_workspace_skills_dir(room, agent_member), "wsskill", name="Workspace Skill")
    _mount_package(room, agent_member, slug="packskill", name="Package Skill")

    # ① the runtime path really is unavailable for a stopped agent — this is what
    #    makes the assertion below meaningful rather than accidental.
    with pytest.raises(OctopError) as err:
        await room.manager.list_skill_summaries(agent_member)
    assert err.value.code is ErrorCode.AGENT_NOT_RUNNING

    # ② the closed enumeration returns both, and the package one is labelled.
    installed = await service.list_installed(agent_member)
    by_slug = {row["slug"]: row for row in installed}
    assert set(by_slug) == {"wsskill", "packskill"}, by_slug
    assert by_slug["packskill"]["kind"] == "package", "package rows must be labelled"
    assert by_slug["packskill"]["display_name"] == "Package Skill"
    assert by_slug["wsskill"]["kind"] == "workspace"


@pytest.mark.asyncio
async def test_offline_path_without_package_roots_would_miss_the_package(
    room: SimpleNamespace, agent_member: str
) -> None:
    """The contrast that proves layer 3 is load-bearing, not decorative."""
    _write_skill(_workspace_skills_dir(room, agent_member), "wsskill", name="Workspace Skill")
    _mount_package(room, agent_member, slug="packskill", name="Package Skill")

    workspace_dir = room.manager.resolve_workspace_dir(agent_member)
    bare = list_workspace_skill_summaries(workspace_dir, skills_disabled=set())
    assert {row["slug"] for row in bare} == {"wsskill"}, "workspace-only scan cannot see packages"

    with_packages = list_workspace_skill_summaries(
        workspace_dir,
        skills_disabled=set(),
        package_dirs=room.manager.resolve_skill_package_dirs(agent_member),
    )
    assert {row["slug"] for row in with_packages} == {"wsskill", "packskill"}


@pytest.mark.asyncio
async def test_list_installed_without_a_manager_proves_nothing(
    room: SimpleNamespace, project_service: ProjectService, agent_member: str
) -> None:
    """Fail closed: no runtime and no resolver ⇒ nothing can be proven installed."""
    svc = ProjectSkillService(
        room.services, project_service=project_service, agent_manager=None, skill_repo=room.repo
    )
    assert await svc.list_installed(agent_member) == []


@pytest.mark.asyncio
async def test_skill_package_ids_are_resolved_from_persisted_state(
    room: SimpleNamespace, service: ProjectSkillService, agent_member: str
) -> None:
    """FIND-5: the directories come from the existing resolver, not a second one."""
    package_root = _mount_package(room, agent_member, slug="packskill", name="Package Skill")
    dirs = room.manager.resolve_skill_package_dirs(agent_member)
    assert [Path(d) for d in dirs] == [package_root.resolve()]
    # An unmounted package contributes nothing.
    room.services.repos.agent_repo.update_config(agent_member, config_json=json.dumps({}))
    assert room.manager.resolve_skill_package_dirs(agent_member) == []


# ── S3: package wins over a same-slug workspace copy ─────────────────────────


@pytest.mark.asyncio
async def test_s3_package_shadows_a_same_slug_workspace_skill(
    room: SimpleNamespace, service: ProjectSkillService, agent_member: str
) -> None:
    """Same slug from two sources → exactly one row, and it is the package's."""
    _write_skill(_workspace_skills_dir(room, agent_member), "report", name="Workspace Report")
    _mount_package(room, agent_member, slug="report", name="Package Report")

    installed = await service.list_installed(agent_member)
    matches = [row for row in installed if row["slug"] == "report"]
    assert len(matches) == 1, f"expected exactly one 'report', got {matches}"
    assert matches[0]["kind"] == "package"
    assert matches[0]["display_name"] == "Package Report"


@pytest.mark.asyncio
async def test_s3_deterministic_rule_is_scan_order(
    room: SimpleNamespace, agent_member: str
) -> None:
    """The offline S3 rule is literally ``package roots first`` — same as runtime."""
    _write_skill(_workspace_skills_dir(room, agent_member), "report", name="Workspace Report")
    _mount_package(room, agent_member, slug="report", name="Package Report")
    rows = list_workspace_skill_summaries(
        room.manager.resolve_workspace_dir(agent_member),
        skills_disabled=set(),
        package_dirs=room.manager.resolve_skill_package_dirs(agent_member),
    )
    report = [row for row in rows if row["slug"] == "report"]
    assert len(report) == 1
    assert report[0]["kind"] == "package"
    assert report[0]["name"] == "Package Report"


# ── the write side: declarations must be provable ────────────────────────────


@pytest.mark.asyncio
async def test_declare_then_read_back_records_real_rows(
    room: SimpleNamespace,
    service: ProjectSkillService,
    project: Any,
    owner: Actor,
    agent_member: str,
) -> None:
    """① 定义 → ② 录入 → ③ 读取 → ④ 展示, with ``project_skills`` counted on disk."""
    _write_skill(_workspace_skills_dir(room, agent_member), "wsskill", name="Workspace Skill")

    # ① what the picker may offer (the projection Q9 requires)
    installed = await service.list_installed(agent_member)
    assert [row["slug"] for row in installed] == ["wsskill"]

    # ② declare
    payload = await service.set_project_skills(
        project.id,
        user=owner,
        entries=[{"agent_id": agent_member, "skill_slug": "wsskill"}],
    )
    assert payload["effective"] == [
        {
            "agent_id": agent_member,
            "skill_slug": "wsskill",
            "display_name": "Workspace Skill",
            "kind": "workspace",
        }
    ]
    assert payload["stale"] == []

    # ★ "table has data" — the row is really there
    assert room.repo.count_by_project(project.id) == 1
    assert room.repo.get(project.id, agent_member, "wsskill") is not None

    # ③ read back
    read = await service.list_project_skills(project.id, user=owner)
    assert read["effective"] == payload["effective"]
    assert read["stale"] == []

    # ④ the shape the rail renders
    assert read["effective"][0]["display_name"] == "Workspace Skill"
    assert read["effective"][0]["kind"] == "workspace"


@pytest.mark.asyncio
async def test_declaring_an_uninstalled_skill_is_409(
    room: SimpleNamespace,
    service: ProjectSkillService,
    project: Any,
    owner: Actor,
    agent_member: str,
) -> None:
    _write_skill(_workspace_skills_dir(room, agent_member), "wsskill", name="Workspace Skill")
    with pytest.raises(OctopError) as err:
        await service.set_project_skills(
            project.id,
            user=owner,
            entries=[{"agent_id": agent_member, "skill_slug": "ghost"}],
        )
    assert err.value.code is ErrorCode.PROJECT_SKILL_INVALID
    assert err.value.status == 409
    assert err.value.status != 500
    assert room.repo.count_by_project(project.id) == 0, "a refused PUT must not write"


@pytest.mark.asyncio
async def test_agent_that_is_not_a_project_member_is_409(
    room: SimpleNamespace, service: ProjectSkillService, project: Any, owner: Actor
) -> None:
    outsider = "OUTSIDE1"
    room.services.repos.agent_repo.create(agent_id=outsider, user_id=owner.id, name="Outsider")
    _write_skill(_workspace_skills_dir(room, outsider), "wsskill", name="Workspace Skill")
    with pytest.raises(OctopError) as err:
        await service.set_project_skills(
            project.id,
            user=owner,
            entries=[{"agent_id": outsider, "skill_slug": "wsskill"}],
        )
    assert err.value.code is ErrorCode.PROJECT_SKILL_INVALID
    assert err.value.status == 409


@pytest.mark.asyncio
async def test_declaration_requires_both_fields(
    room: SimpleNamespace, service: ProjectSkillService, project: Any, owner: Actor
) -> None:
    for entry in ({"agent_id": "", "skill_slug": "x"}, {"agent_id": "A", "skill_slug": ""}):
        with pytest.raises(OctopError) as err:
            await service.set_project_skills(project.id, user=owner, entries=[entry])
        assert err.value.code is ErrorCode.PROJECT_SKILL_INVALID


@pytest.mark.asyncio
async def test_put_is_a_full_replacement(
    room: SimpleNamespace,
    service: ProjectSkillService,
    project: Any,
    owner: Actor,
    agent_member: str,
) -> None:
    root = _workspace_skills_dir(room, agent_member)
    _write_skill(root, "one", name="One")
    _write_skill(root, "two", name="Two")

    await service.set_project_skills(
        project.id,
        user=owner,
        entries=[
            {"agent_id": agent_member, "skill_slug": "one"},
            {"agent_id": agent_member, "skill_slug": "two"},
        ],
    )
    assert room.repo.count_by_project(project.id) == 2

    # Omitting `one` removes it, and the row is really gone.
    payload = await service.set_project_skills(
        project.id, user=owner, entries=[{"agent_id": agent_member, "skill_slug": "two"}]
    )
    assert [row["skill_slug"] for row in payload["effective"]] == ["two"]
    assert room.repo.count_by_project(project.id) == 1
    assert room.repo.get(project.id, agent_member, "one") is None

    # An empty set clears everything.
    assert await service.set_project_skills(project.id, user=owner, entries=[]) == {
        "effective": [],
        "stale": [],
    }
    assert room.repo.count_by_project(project.id) == 0


# ── stale: marked on read, refused on write ──────────────────────────────────


@pytest.mark.asyncio
async def test_a_skill_that_disappears_becomes_stale_and_is_never_auto_deleted(
    room: SimpleNamespace,
    service: ProjectSkillService,
    project: Any,
    owner: Actor,
    agent_member: str,
) -> None:
    root = _workspace_skills_dir(room, agent_member)
    skill_dir = _write_skill(root, "temporary", name="Temporary")
    await service.set_project_skills(
        project.id, user=owner, entries=[{"agent_id": agent_member, "skill_slug": "temporary"}]
    )
    assert (await service.list_project_skills(project.id, user=owner))["stale"] == []

    # The skill goes away after the declaration was stored.
    import shutil

    shutil.rmtree(skill_dir)

    payload = await service.list_project_skills(project.id, user=owner)
    assert payload["effective"] == []
    assert payload["stale"] == [
        {"agent_id": agent_member, "skill_slug": "temporary", "reason": "not_installed"}
    ]
    # ★ the row survives — stale is a display state, not a delete
    assert room.repo.count_by_project(project.id) == 1


@pytest.mark.asyncio
async def test_resubmitting_a_stale_entry_is_409(
    room: SimpleNamespace,
    service: ProjectSkillService,
    project: Any,
    owner: Actor,
    agent_member: str,
) -> None:
    """A request may not persist a disconnected declaration — even the same one."""
    root = _workspace_skills_dir(room, agent_member)
    skill_dir = _write_skill(root, "temporary", name="Temporary")
    await service.set_project_skills(
        project.id, user=owner, entries=[{"agent_id": agent_member, "skill_slug": "temporary"}]
    )
    import shutil

    shutil.rmtree(skill_dir)

    with pytest.raises(OctopError) as err:
        await service.set_project_skills(
            project.id, user=owner, entries=[{"agent_id": agent_member, "skill_slug": "temporary"}]
        )
    assert err.value.code is ErrorCode.PROJECT_SKILL_INVALID
    assert err.value.status == 409
    # The stale row is still there (the refusal wrote nothing).
    assert room.repo.count_by_project(project.id) == 1


@pytest.mark.asyncio
async def test_a_restored_skill_becomes_effective_again(
    room: SimpleNamespace,
    service: ProjectSkillService,
    project: Any,
    owner: Actor,
    agent_member: str,
) -> None:
    """The other half of "stale is computed": it self-heals when the skill returns."""
    root = _workspace_skills_dir(room, agent_member)
    skill_dir = _write_skill(root, "temporary", name="Temporary")
    await service.set_project_skills(
        project.id, user=owner, entries=[{"agent_id": agent_member, "skill_slug": "temporary"}]
    )
    import shutil

    shutil.rmtree(skill_dir)
    assert (await service.list_project_skills(project.id, user=owner))["stale"] != []

    _write_skill(root, "temporary", name="Temporary")
    payload = await service.list_project_skills(project.id, user=owner)
    assert payload["stale"] == []
    assert [row["skill_slug"] for row in payload["effective"]] == ["temporary"]


@pytest.mark.asyncio
async def test_a_package_skill_declared_while_stopped_stays_effective(
    room: SimpleNamespace,
    service: ProjectSkillService,
    project: Any,
    owner: Actor,
    agent_member: str,
) -> None:
    """End-to-end on the closed path: declare a package skill with the agent stopped."""
    _mount_package(room, agent_member, slug="packskill", name="Package Skill")
    payload = await service.set_project_skills(
        project.id, user=owner, entries=[{"agent_id": agent_member, "skill_slug": "packskill"}]
    )
    assert payload["stale"] == []
    assert payload["effective"][0]["kind"] == "package"
    assert room.repo.count_by_project(project.id) == 1


# ── permissions ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_viewer_cannot_write_but_can_read(
    room: SimpleNamespace,
    project_service: ProjectService,
    service: ProjectSkillService,
    project: Any,
    owner: Actor,
    agent_member: str,
) -> None:
    viewer = Actor(
        room.services.repos.user_repo.create(username="viewer", password_hash="h", role="user")
    )
    project_service.add_member(
        project.id, user=owner, subject_type="user", subject_id=str(viewer.id), role="viewer"
    )
    _write_skill(_workspace_skills_dir(room, agent_member), "wsskill", name="Workspace Skill")
    await service.set_project_skills(
        project.id, user=owner, entries=[{"agent_id": agent_member, "skill_slug": "wsskill"}]
    )

    assert (await service.list_project_skills(project.id, user=viewer))["effective"] != []

    with pytest.raises(OctopError) as err:
        await service.set_project_skills(project.id, user=viewer, entries=[])
    # A viewer is a member, so the role table refuses the action.
    assert err.value.code is ErrorCode.PROJECT_ROLE_FORBIDDEN
    assert err.value.status == 403
    assert room.repo.count_by_project(project.id) == 1


@pytest.mark.asyncio
async def test_non_member_is_refused_even_when_admin(
    room: SimpleNamespace, service: ProjectSkillService, project: Any
) -> None:
    stranger = Actor(
        room.services.repos.user_repo.create(username="stranger", password_hash="h", role="user"),
        admin=True,
    )
    with pytest.raises(OctopError) as err:
        await service.list_project_skills(project.id, user=stranger)
    assert err.value.code is ErrorCode.PROJECT_FORBIDDEN
    assert err.value.status == 403, "membership is the boundary; admin is no exception"


@pytest.mark.asyncio
async def test_validate_declarations_reuses_the_same_rules(
    room: SimpleNamespace,
    service: ProjectSkillService,
    project: Any,
    owner: Actor,
    agent_member: str,
) -> None:
    """A second caller can validate without writing — and without restating rules."""
    _write_skill(_workspace_skills_dir(room, agent_member), "wsskill", name="Workspace Skill")
    await service.validate_declarations(
        project.id, user=owner, entries=[{"agent_id": agent_member, "skill_slug": "wsskill"}]
    )
    assert room.repo.count_by_project(project.id) == 0, "validation never writes"

    with pytest.raises(OctopError) as err:
        await service.validate_declarations(
            project.id, user=owner, entries=[{"agent_id": agent_member, "skill_slug": "ghost"}]
        )
    assert err.value.code is ErrorCode.PROJECT_SKILL_INVALID
