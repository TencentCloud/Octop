"""Skill package copy policy (#770): deny gate, lock watermark, workspace guard."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from tests.unit.skills.test_skill_transfer import _MemWorkspace

from octop.infra.errors import ErrorCode, OctopError
from octop.infra.skills.skill_package_store import (
    normalize_copy_policy,
)
from octop.infra.skills.skill_transfer import (
    _stamp_locked_manifest,
    copy_package_skills_to_workspace,
)


def _user(uid: int, *, admin: bool = False) -> SimpleNamespace:
    return SimpleNamespace(id=uid, is_admin=admin)


def _row(policy: str, *, package_id: str = "pkg_1", created_by: str = "7") -> SimpleNamespace:
    return SimpleNamespace(id=package_id, copy_policy=policy, created_by=created_by)


def _store() -> SimpleNamespace:
    from octop.infra.skills.skill_package_store import SkillPackageStore

    return SkillPackageStore(repo=SimpleNamespace(), root=None)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("policy", "user", "allowed"),
    [
        ("snapshot", _user(2), True),
        ("lock", _user(2), True),
        ("deny", _user(2), False),
        ("deny", _user(7), True),  # creator
        ("deny", _user(1, admin=True), True),  # admin
        (None, _user(2), True),  # legacy rows without policy
        ("garbage", _user(2), True),  # unknown values clamp to snapshot
    ],
)
def test_can_copy_matrix(policy: str | None, user: SimpleNamespace, allowed: bool) -> None:
    store = _store()
    assert store.can_copy(_row(policy or ""), user) is allowed


def test_assert_can_copy_raises_deny_for_others() -> None:
    store = _store()
    with pytest.raises(OctopError) as excinfo:
        store.assert_can_copy(_row("deny"), _user(2))
    assert excinfo.value.code == ErrorCode.SKILL_PACKAGE_COPY_DENIED
    # creator passes without raising
    store.assert_can_copy(_row("deny"), _user(7))


def test_normalize_copy_policy() -> None:
    assert normalize_copy_policy("deny") == "deny"
    assert normalize_copy_policy(" LOCK ") == "lock"
    assert normalize_copy_policy("") == "snapshot"
    assert normalize_copy_policy(None) == "snapshot"
    assert normalize_copy_policy("nope") == "snapshot"


def test_stamp_locked_manifest_adds_keys() -> None:
    out = _stamp_locked_manifest(b"---\nname: x\ndescription: y\n---\n\nbody", "pkg_1")
    text = out.decode()
    assert "origin: pkg_1" in text
    assert "locked: true" in text
    assert text.startswith("---\n")
    assert text.endswith("body")


def test_stamp_locked_manifest_creates_frontmatter_when_missing() -> None:
    text = _stamp_locked_manifest(b"plain body", "pkg_1").decode()
    assert text == "---\norigin: pkg_1\nlocked: true\n---\n\nplain body"


def test_stamp_locked_manifest_is_idempotent() -> None:
    once = _stamp_locked_manifest(b"---\nname: x\n---\nbody", "pkg_1")
    twice = _stamp_locked_manifest(once, "pkg_1")
    assert twice.decode().count("origin: pkg_1") == 1


@pytest.mark.asyncio
async def test_copy_with_lock_policy_stamps_workspace_manifest(tmp_path) -> None:
    skills_dir = tmp_path / "pkg_1" / "alpha"
    skills_dir.mkdir(parents=True)
    (skills_dir / "SKILL.md").write_bytes(b"---\nname: alpha\n---\n\nhello")

    store = SimpleNamespace(
        package_skills_dir=lambda pack_id: tmp_path / pack_id,
    )
    workspace = _MemWorkspace()

    copied = await copy_package_skills_to_workspace(
        store=store,  # type: ignore[arg-type]
        package_id="pkg_1",
        slugs=["alpha"],
        workspace=workspace,
        copy_policy="lock",
    )
    assert copied == ["alpha"]
    manifest = workspace.files["skills/alpha/SKILL.md"].decode()
    assert "origin: pkg_1" in manifest
    assert "locked: true" in manifest


async def _run_guard(
    manifest: bytes | None,
    *,
    user: SimpleNamespace,
    origin_created_by: str = "7",
) -> OctopError | None:
    from octop.api.routers.skills import _guard_package_only_skill_write

    files = {"skills/alpha/SKILL.md": manifest} if manifest is not None else {}
    workspace = _MemWorkspace(files)

    class _Repo:
        def get(self, package_id: str) -> SimpleNamespace | None:
            if package_id != "pkg_1":
                return None
            return SimpleNamespace(created_by=origin_created_by)

    server = SimpleNamespace(
        services=SimpleNamespace(skill_package_repo=_Repo()),
        paths=SimpleNamespace(skill_packages_dir=tmp_path_unused),
    )
    try:
        await _guard_package_only_skill_write(workspace, {}, server, "alpha", user)
    except OctopError as exc:
        return exc
    return None


tmp_path_unused = ""


LOCKED_MANIFEST = b"---\nname: alpha\norigin: pkg_1\nlocked: true\n---\n\nhello"
PLAIN_MANIFEST = b"---\nname: alpha\n---\n\nhello"


@pytest.mark.asyncio
async def test_guard_rejects_locked_copy_for_others() -> None:
    exc = await _run_guard(LOCKED_MANIFEST, user=_user(2))
    assert exc is not None
    assert exc.code == ErrorCode.SKILL_PACKAGE_LOCKED


@pytest.mark.asyncio
async def test_guard_allows_locked_copy_for_creator_and_admin() -> None:
    assert await _run_guard(LOCKED_MANIFEST, user=_user(7)) is None
    assert await _run_guard(LOCKED_MANIFEST, user=_user(1, admin=True)) is None


@pytest.mark.asyncio
async def test_guard_ignores_plain_and_missing_manifests() -> None:
    assert await _run_guard(PLAIN_MANIFEST, user=_user(2)) is None
    assert await _run_guard(None, user=_user(2)) is None


@pytest.mark.asyncio
async def test_guard_unknown_origin_stays_locked_except_admin() -> None:
    manifest = b"---\nname: alpha\norigin: pkg_gone\nlocked: true\n---\n\nhi"
    exc = await _run_guard(manifest, user=_user(2))
    assert exc is not None
    assert exc.code == ErrorCode.SKILL_PACKAGE_LOCKED
    assert await _run_guard(manifest, user=_user(1, admin=True)) is None
