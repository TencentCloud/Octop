"""Tests for materializing SkillHub skillsets as global packages."""

from __future__ import annotations

from pathlib import Path

import pytest

from octop.infra.agents.experts.skillhub_market import SkillHubSkillset
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.skill_packages import SkillPackageRepo
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.skills.skill_package_from_skillhub import create_package_from_skillhub
from octop.infra.skills.skill_package_store import SkillPackageStore


@pytest.fixture
def store(tmp_path: Path) -> SkillPackageStore:
    db = SqlitePool(tmp_path / "octop.db")
    run_migrations(db)
    return SkillPackageStore(
        repo=SkillPackageRepo(db),
        root=tmp_path / "skill-packages",
    )


def _item(*, skill_slugs: tuple[str, ...] = ("alpha",)) -> SkillHubSkillset:
    return SkillHubSkillset(
        slug="demo-skillset",
        display_name="Demo package",
        summary="A package from SkillHub.",
        scene="tech",
        icon_url="https://cdn.skillhub.cn/icons/demo.png",
        skill_slugs=skill_slugs,
    )


def test_duplicate_name_raises_package_name_taken(store: SkillPackageStore) -> None:
    store.create(name="Demo package", description="", created_by="1")

    with pytest.raises(OctopError) as exc_info:
        create_package_from_skillhub(
            store,
            slug="demo-skillset",
            created_by="1",
            fetch_skillset_fn=lambda _slug: _item(),
            download_skill_files_fn=lambda _slug: [("SKILL.md", b"---\nname: alpha\n---\n")],
        )

    assert exc_info.value.code is ErrorCode.SKILL_PACKAGE_NAME_TAKEN
    assert exc_info.value.status == 409


def test_create_maps_integrity_error_when_name_races(
    store: SkillPackageStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store.create(name="Demo package", description="", created_by="1")
    monkeypatch.setattr(store.repo, "get_by_name", lambda _name: None)

    with pytest.raises(OctopError) as exc_info:
        create_package_from_skillhub(
            store,
            slug="demo-skillset",
            created_by="1",
            fetch_skillset_fn=lambda _slug: _item(),
            download_skill_files_fn=lambda _slug: [("SKILL.md", b"---\nname: alpha\n---\n")],
        )

    assert exc_info.value.code is ErrorCode.SKILL_PACKAGE_NAME_TAKEN
    assert len(store.repo.list_all()) == 1


def test_writes_skills_and_default_icons(store: SkillPackageStore) -> None:
    result = create_package_from_skillhub(
        store,
        slug="demo-skillset",
        created_by="1",
        fetch_skillset_fn=lambda _slug: _item(),
        download_skill_files_fn=lambda _slug: [("SKILL.md", b"---\nname: alpha\n---\n")],
    )

    assert result.row.icon_name == "cpu"
    assert result.row.icon_url == "https://cdn.skillhub.cn/icons/demo.png"
    assert result.row.skill_count == 1
    assert [skill["slug"] for skill in store.list_skill_summaries(result.row.id)] == ["alpha"]


def test_returns_refreshed_skill_count_for_multiple_skills(store: SkillPackageStore) -> None:
    result = create_package_from_skillhub(
        store,
        slug="demo-skillset",
        created_by="1",
        fetch_skillset_fn=lambda _slug: _item(skill_slugs=("alpha", "beta")),
        download_skill_files_fn=lambda skill_slug: [
            ("SKILL.md", f"---\nname: {skill_slug}\n---\n".encode())
        ],
    )

    assert result.row.skill_count == 2


def test_write_failure_deletes_new_package(
    store: SkillPackageStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = 0
    original_write_skill = store.write_skill

    def fail_on_second_write(
        package_id: str,
        skill_slug: str,
        files: list[tuple[str, bytes]],
    ) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("disk write failed")
        original_write_skill(package_id, skill_slug, files)

    monkeypatch.setattr(store, "write_skill", fail_on_second_write)

    with pytest.raises(RuntimeError, match="disk write failed"):
        create_package_from_skillhub(
            store,
            slug="demo-skillset",
            created_by="1",
            fetch_skillset_fn=lambda _slug: _item(skill_slugs=("alpha", "beta")),
            download_skill_files_fn=lambda skill_slug: [
                ("SKILL.md", f"---\nname: {skill_slug}\n---\n".encode())
            ],
        )

    assert store.repo.list_all() == []
    assert list(store.root.iterdir()) == []
