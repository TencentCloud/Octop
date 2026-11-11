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
from octop.infra.skills.skillhub_market import SkillHubSkillNotFound


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


def test_skips_unpublished_skill_and_keeps_the_rest(store: SkillPackageStore) -> None:
    def download(skill_slug: str) -> list[tuple[str, bytes]]:
        if skill_slug == "content-writer":
            raise SkillHubSkillNotFound("SkillHub skill package not found: HTTP 404")
        return [("SKILL.md", f"---\nname: {skill_slug}\n---\n".encode())]

    result = create_package_from_skillhub(
        store,
        slug="demo-skillset",
        created_by="1",
        fetch_skillset_fn=lambda _slug: _item(skill_slugs=("alpha", "content-writer")),
        download_skill_files_fn=download,
    )

    assert result.skipped_slugs == ("content-writer",)
    assert result.row.skill_count == 1
    assert [skill["slug"] for skill in store.list_skill_summaries(result.row.id)] == ["alpha"]


def test_all_missing_skills_fail_without_creating_a_package(store: SkillPackageStore) -> None:
    def download(_skill_slug: str) -> list[tuple[str, bytes]]:
        raise SkillHubSkillNotFound("SkillHub skill package not found: HTTP 404")

    with pytest.raises(SkillHubSkillNotFound):
        create_package_from_skillhub(
            store,
            slug="demo-skillset",
            created_by="1",
            fetch_skillset_fn=lambda _slug: _item(skill_slugs=("content-writer",)),
            download_skill_files_fn=download,
        )

    assert store.repo.list_all() == []


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


def _portal_archive(
    *, expert_id: str = "portal-only", extra: dict[str, bytes] | None = None
) -> bytes:
    import io
    import json
    import zipfile

    files = {
        "manifest.json": json.dumps({"id": expert_id}).encode(),
        "AGENTS.md": b"Read skills/child/SKILL.md, then use scripts/helper.py.",
        "USER.md": b"template profile",
        "skills/child/SKILL.md": b"---\nname: child\ndescription: child task\n---\nRead ../../references/shared.md",
        "references/shared.md": b"shared reference",
        "scripts/helper.py": b"print('helper')",
    }
    files.update(extra or {})
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for path, content in files.items():
            archive.writestr(path, content)
    return buffer.getvalue()


@pytest.fixture
def portal_market(monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    import hashlib

    from octop.infra.market import experts, http

    payload = _portal_archive()
    item: dict[str, object] = {
        "slug": "portal-only",
        "label": {"zh": "Portal workflow"},
        "description": {"zh": "A complete workflow"},
        "download_url": "https://download.octop.cloud/portal.zip",
        "size_bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }
    monkeypatch.setattr(experts, "get_market_expert", lambda _slug: item)
    monkeypatch.setattr(http, "fetch_bytes", lambda *_args, **_kwargs: payload)
    monkeypatch.setattr(
        "octop.infra.skills.skill_package_from_skillhub.fetch_skillset",
        lambda _slug: pytest.fail("portal entry must not query SkillHub"),
    )
    return item


def test_portal_only_import_keeps_self_contained_dependencies(
    store: SkillPackageStore, portal_market: dict[str, object]
) -> None:
    result = create_package_from_skillhub(store, slug="portal-only", created_by="1")

    assert result.row.name == "Portal workflow"
    assert result.row.skill_count == 1
    root = store.package_skills_dir(result.row.id) / "portal-only"
    assert (root / "references/shared.md").read_bytes() == b"shared reference"
    assert (root / "scripts/helper.py").read_bytes() == b"print('helper')"
    child = root / "skills/child"
    assert (child / "../../USER.md").resolve().read_bytes() == b"template profile"
    assert (child / "../../references/shared.md").resolve().read_bytes() == b"shared reference"
    workflow = (root / "SKILL.md").read_text()
    from octop.infra.utils.frontmatter import parse_frontmatter

    metadata, _ = parse_frontmatter(workflow)
    assert metadata["name"] == "portal-only"
    assert metadata["description"] == "A complete workflow"
    assert "AGENTS.md" in workflow
    assert "skills/child/SKILL.md" in workflow


@pytest.mark.parametrize(
    "field,value",
    [
        ("sha256", "0" * 64),
        ("size_bytes", 1),
        ("download_url", "https://attacker.invalid/archive.zip"),
    ],
)
def test_portal_rejects_bad_catalog_archive(
    store: SkillPackageStore, portal_market: dict[str, object], field: str, value: object
) -> None:
    from octop.infra.market.errors import PortalMarketError

    portal_market[field] = value
    with pytest.raises(PortalMarketError):
        create_package_from_skillhub(store, slug="portal-only", created_by="1")
    assert store.repo.list_all() == []


@pytest.mark.parametrize(
    "payload",
    [
        b"not a zip",
        _portal_archive(expert_id="wrong"),
        _portal_archive(extra={"../escape": b"bad"}),
    ],
    ids=["not-zip", "wrong-id", "path-traversal"],
)
def test_portal_rejects_invalid_archive(
    store: SkillPackageStore,
    portal_market: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
    payload: bytes,
) -> None:
    import hashlib

    from octop.infra.market import http
    from octop.infra.market.errors import PortalMarketError

    portal_market.update(size_bytes=len(payload), sha256=hashlib.sha256(payload).hexdigest())
    monkeypatch.setattr(http, "fetch_bytes", lambda *_args, **_kwargs: payload)
    with pytest.raises(PortalMarketError):
        create_package_from_skillhub(store, slug="portal-only", created_by="1")
    assert store.repo.list_all() == []


def test_portal_write_failure_rolls_back(
    store: SkillPackageStore, portal_market: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(*_args: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(store, "write_skill", fail)
    with pytest.raises(OSError, match="disk full"):
        create_package_from_skillhub(store, slug="portal-only", created_by="1")
    assert store.repo.list_all() == []
    assert list(store.root.iterdir()) == []


def test_absent_portal_entry_keeps_skillhub_fallback(
    store: SkillPackageStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    from octop.infra.market import experts
    from octop.infra.skills import skill_package_from_skillhub

    monkeypatch.setattr(experts, "get_market_expert", lambda _slug: None)
    monkeypatch.setattr(skill_package_from_skillhub, "fetch_skillset", lambda _slug: _item())
    result = create_package_from_skillhub(
        store,
        slug="demo-skillset",
        created_by="1",
        download_skill_files_fn=lambda _slug: [("SKILL.md", b"---\nname: alpha\n---\n")],
    )
    assert result.row.name == "Demo package"
    assert result.row.skill_count == 1


@pytest.mark.parametrize("include_manifest", [True, False])
def test_portal_rejects_empty_or_missing_manifest(
    store: SkillPackageStore,
    portal_market: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
    include_manifest: bool,
) -> None:
    import hashlib
    import io
    import zipfile

    from octop.infra.market import http
    from octop.infra.market.errors import PortalMarketError

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        if include_manifest:
            archive.writestr("manifest.json", '{"id":"portal-only"}')
        else:
            archive.writestr("skills/child/SKILL.md", "# Child")
    payload = buffer.getvalue()
    portal_market.update(size_bytes=len(payload), sha256=hashlib.sha256(payload).hexdigest())
    monkeypatch.setattr(http, "fetch_bytes", lambda *_args, **_kwargs: payload)
    with pytest.raises(PortalMarketError):
        create_package_from_skillhub(store, slug="portal-only", created_by="1")
    assert store.repo.list_all() == []


def test_duplicate_portal_name_does_not_download(
    store: SkillPackageStore, portal_market: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    from octop.infra.market import http

    store.create(name="Portal workflow", description="", created_by="1")
    monkeypatch.setattr(
        http, "fetch_bytes", lambda *_args, **_kwargs: pytest.fail("duplicate must not download")
    )
    with pytest.raises(OctopError) as exc_info:
        create_package_from_skillhub(store, slug="portal-only", created_by="1")
    assert exc_info.value.code is ErrorCode.SKILL_PACKAGE_NAME_TAKEN
