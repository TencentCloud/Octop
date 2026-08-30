"""Tests for global skill package disk storage."""

from __future__ import annotations

from pathlib import Path

import pytest

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.skill_packages import SkillPackageRepo
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.skills.skill_package_store import SkillPackageStore
from octop.infra.users.identity import Role, User


@pytest.fixture
def db(tmp_path: Path) -> SqlitePool:
    pool = SqlitePool(tmp_path / "octop.db")
    run_migrations(pool)
    return pool


@pytest.fixture
def store(tmp_path: Path, db: SqlitePool) -> SkillPackageStore:
    return SkillPackageStore(
        repo=SkillPackageRepo(db),
        root=tmp_path / "skill-packages",
    )


def test_create_package_makes_skills_dir(store: SkillPackageStore) -> None:
    row = store.create(name="P", description="", created_by="42")

    assert len(row.id) == 6
    assert (store.root / row.id / "skills").is_dir()


def test_write_and_delete_skill_updates_disk_summaries_and_count(
    store: SkillPackageStore,
) -> None:
    row = store.create(name="P", description="", created_by="42")

    store.write_skill(
        row.id,
        "pdf",
        [
            (
                "SKILL.md",
                (
                    "---\nname: PDF\nmetadata:\n  octop:\n"
                    "    display_name: PDF Reader\n"
                    "    emoji: '📄'\n"
                    "    icon_url: https://cdn.example.com/pdf.png\n"
                    "---\nRead PDFs."
                ).encode(),
            ),
            ("references/guide.md", b"# Guide"),
        ],
    )

    assert (
        store.package_skills_dir(row.id) / "pdf" / "references" / "guide.md"
    ).read_bytes() == b"# Guide"
    assert store.list_skill_summaries(row.id) == [
        {
            "slug": "pdf",
            "name": "PDF",
            "description": "",
            "path": "skills/pdf/SKILL.md",
            "kind": "package",
            "package_id": row.id,
            "display_name": "PDF Reader",
            "emoji": "\U0001f4c4",
            "icon_url": "https://cdn.example.com/pdf.png",
        }
    ]
    assert store.repo.get(row.id).skill_count == 1

    store.delete_skill(row.id, "pdf")

    assert not (store.package_skills_dir(row.id) / "pdf").exists()
    assert store.list_skill_summaries(row.id) == []
    assert store.repo.get(row.id).skill_count == 0


@pytest.mark.parametrize(
    ("method", "slug", "files"),
    [
        ("write_skill", "../unsafe", [("SKILL.md", b"# skill")]),
        ("write_skill", "safe", [("../unsafe", b"bad")]),
        ("delete_skill", "../unsafe", None),
    ],
)
def test_skill_validation_errors_are_mapped_to_octop_errors(
    store: SkillPackageStore,
    method: str,
    slug: str,
    files: list[tuple[str, bytes]] | None,
) -> None:
    row = store.create(name="P", description="", created_by="42")

    with pytest.raises(OctopError) as exc_info:
        if method == "write_skill":
            assert files is not None
            store.write_skill(row.id, slug, files)
        else:
            store.delete_skill(row.id, slug)

    assert exc_info.value.code is ErrorCode.SLASH_BAD_ARGS


def test_write_skill_recreates_empty_directories(store: SkillPackageStore) -> None:
    row = store.create(name="P", description="", created_by="42")

    store.write_skill(
        row.id,
        "word-docx",
        [
            ("SKILL.md", b"---\nname: word-docx\n---\n"),
            ("ai/", b""),
            ("data/", b""),
            ("scripts/", b""),
            ("index.html", b"<html></html>"),
        ],
    )

    skill_dir = store.package_skills_dir(row.id) / "word-docx"
    assert skill_dir.is_dir()
    assert (skill_dir / "SKILL.md").read_bytes() == b"---\nname: word-docx\n---\n"
    assert (skill_dir / "index.html").read_bytes() == b"<html></html>"
    assert (skill_dir / "ai").is_dir()
    assert (skill_dir / "data").is_dir()
    assert (skill_dir / "scripts").is_dir()
    assert list((skill_dir / "ai").iterdir()) == []


def test_list_skill_summaries_localizes_octop_metadata(store: SkillPackageStore) -> None:
    row = store.create(name="P", description="", created_by="42")
    store.write_skill(
        row.id,
        "pdf-reader",
        [
            (
                "SKILL.md",
                (
                    "---\n"
                    "name: pdf-reader\n"
                    "description: Agent trigger\n"
                    "metadata:\n"
                    "  octop:\n"
                    "    label:\n"
                    "      zh: PDF 阅读\n"
                    "      en: PDF Reader\n"
                    "    summary:\n"
                    "      zh: 读取 PDF\n"
                    "      en: Read PDFs\n"
                    "---\n"
                ).encode(),
            )
        ],
    )

    zh = store.list_skill_summaries(row.id, locale="zh")[0]
    en = store.list_skill_summaries(row.id, locale="en")[0]

    assert (zh["name"], zh["description"]) == ("PDF 阅读", "读取 PDF")
    assert (en["name"], en["description"]) == ("PDF Reader", "Read PDFs")


def test_skill_count_excludes_skills_hidden_from_summaries(store: SkillPackageStore) -> None:
    row = store.create(name="P", description="", created_by="42")
    skills_dir = store.package_skills_dir(row.id)
    (skills_dir / "missing-manifest").mkdir()
    hidden = skills_dir / "hidden"
    hidden.mkdir()
    (hidden / "SKILL.md").write_text("---\nremoved: true\n---\n", encoding="utf-8")

    store.write_skill(row.id, "visible", [("SKILL.md", b"# visible")])

    assert [summary["slug"] for summary in store.list_skill_summaries(row.id)] == ["visible"]
    assert store.repo.get(row.id).skill_count == 1


def test_delete_package_removes_database_row_and_directory(
    store: SkillPackageStore,
) -> None:
    row = store.create(name="P", description="", created_by="42")

    store.delete_package(row.id)

    assert store.repo.get(row.id) is None
    assert not (store.root / row.id).exists()


def test_assert_can_mutate_allows_creator_and_admin_only(
    store: SkillPackageStore,
) -> None:
    row = store.create(name="P", description="", created_by="42")
    creator = User(id=42, username="creator", role=Role.USER, display_name=None)
    other = User(id=7, username="other", role=Role.USER, display_name=None)
    admin = User(id=1, username="admin", role=Role.ADMIN, display_name=None)

    store.assert_can_mutate(row, creator)
    store.assert_can_mutate(row, admin)

    with pytest.raises(OctopError) as exc_info:
        store.assert_can_mutate(row, other)
    assert exc_info.value.code is ErrorCode.FORBIDDEN
