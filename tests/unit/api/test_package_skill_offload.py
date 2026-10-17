"""Tests for get_package_skill offloading, corruption handling, and error mapping."""

from __future__ import annotations

import asyncio
import threading
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from octop.api.routers import skill_packages as sp_router
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.skills.skill_package_store import SkillPackageStore
from octop.infra.users.identity import User


def _make_fake_env(tmp_path):
    root = tmp_path / "skill_packages"
    root.mkdir(parents=True, exist_ok=True)

    fake_row = SimpleNamespace(
        id="pkg_test",
        name="Test Package",
        created_by="1",
        copy_policy="clone",
    )
    fake_repo = MagicMock()
    fake_repo.get.return_value = fake_row

    store = SkillPackageStore(repo=fake_repo, root=root)
    server = SimpleNamespace(
        services=SimpleNamespace(skill_package_repo=fake_repo),
        paths=SimpleNamespace(skill_packages_dir=root),
        app_runtime=None,
    )
    req = SimpleNamespace(headers={})
    user = User(id=1, username="admin", role="admin", display_name="Admin")
    return store, server, req, user


def test_package_skill_reads_happen_off_the_event_loop(tmp_path, monkeypatch):
    store, server, req, user = _make_fake_env(tmp_path)
    skill_dir = store.package_skills_dir("pkg_test") / "demo-skill"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text("---\nname: Demo\n---\nHello world", encoding="utf-8")

    seen: dict[str, int] = {}
    real_read_text = type(skill_dir / "SKILL.md").read_text

    def _spy_read_text(self, *args, **kwargs):
        seen["read"] = threading.get_ident()
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(type(skill_dir / "SKILL.md"), "read_text", _spy_read_text)

    async def _go():
        seen["loop"] = threading.get_ident()
        return await sp_router.get_package_skill(
            package_id="pkg_test",
            slug="demo-skill",
            request=req,
            server=server,
            _user=user,
        )

    result = asyncio.run(_go())
    assert result["slug"] == "demo-skill"
    assert result["body"] == "Hello world"
    assert "read" in seen
    assert seen["read"] != seen["loop"], "SKILL.md read occurred directly on the asyncio event loop"


def test_package_skill_corrupt_utf8_does_not_crash(tmp_path):
    store, server, req, user = _make_fake_env(tmp_path)
    skill_dir = store.package_skills_dir("pkg_test") / "corrupt-skill"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_bytes(b"---\nname: Corrupt\n---\n\xff\xfe binary junk")

    async def _go():
        return await sp_router.get_package_skill(
            package_id="pkg_test",
            slug="corrupt-skill",
            request=req,
            server=server,
            _user=user,
        )

    result = asyncio.run(_go())
    assert result["slug"] == "corrupt-skill"
    assert result.get("corrupt") is True
    assert result["frontmatter"] == {}
    assert result["body"] == ""
    assert result["raw"] == ""


def test_package_skill_repaired_utf8(tmp_path):
    store, server, req, user = _make_fake_env(tmp_path)
    skill_dir = store.package_skills_dir("pkg_test") / "repaired-skill"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_bytes(b"---\nname: Repaired\n---\nScore \xe2j$ 10")

    async def _go():
        return await sp_router.get_package_skill(
            package_id="pkg_test",
            slug="repaired-skill",
            request=req,
            server=server,
            _user=user,
        )

    result = asyncio.run(_go())
    assert result["slug"] == "repaired-skill"
    assert result["body"] == "Score \u2264 10"


def test_package_skill_missing_manifest_raises_not_found(tmp_path, monkeypatch):
    store, server, req, user = _make_fake_env(tmp_path)
    skill_dir = store.package_skills_dir("pkg_test") / "vanished-skill"
    skill_dir.mkdir(parents=True, exist_ok=True)
    manifest = skill_dir / "SKILL.md"
    manifest.write_text("---\nname: Vanished\n---\nGhost", encoding="utf-8")

    # Simulate listing succeeding but the manifest file being removed right after
    orig_package_skill_or_404 = sp_router._package_skill_or_404

    def _hook(*args, **kwargs):
        res = orig_package_skill_or_404(*args, **kwargs)
        manifest.unlink(missing_ok=True)
        return res

    monkeypatch.setattr(sp_router, "_package_skill_or_404", _hook)

    async def _go():
        return await sp_router.get_package_skill(
            package_id="pkg_test",
            slug="vanished-skill",
            request=req,
            server=server,
            _user=user,
        )

    with pytest.raises(OctopError) as exc_info:
        asyncio.run(_go())
    assert exc_info.value.code == ErrorCode.NOT_FOUND
