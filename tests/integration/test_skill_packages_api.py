"""Integration coverage for global skill package HTTP routes."""

from __future__ import annotations

import base64
import io
import zipfile
from typing import Any

import pytest

SAMPLE_SKILL = """---
name: pdf-reader
description: Read PDF documents
---
# PDF Reader
"""


def _b64(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


async def test_create_and_list_skill_package(env: Any) -> None:
    client, _server, auth = env

    created = await client.post(
        "/api/skill-packages",
        headers=auth,
        json={
            "name": "Office",
            "description": "",
            "copy_policy": "lock",
            "allow_download": False,
            "shared": False,
        },
    )

    assert created.status_code == 200, created.text
    body = created.json()
    package_id = body["id"]
    assert body["copy_policy"] == "lock"
    assert body["allow_download"] is False
    assert body["shared"] is False

    listed = await client.get("/api/skill-packages", headers=auth)

    assert listed.status_code == 200, listed.text
    assert any(package["id"] == package_id for package in listed.json())


async def test_create_skill_package_rejects_duplicate_name(env: Any) -> None:
    client, _server, auth = env
    payload = {"name": "Office"}

    created = await client.post("/api/skill-packages", headers=auth, json=payload)
    duplicate = await client.post("/api/skill-packages", headers=auth, json=payload)

    assert created.status_code == 200, created.text
    assert duplicate.status_code == 409, duplicate.text
    assert duplicate.json()["error"]["code"] == "SKILL_PACKAGE_NAME_TAKEN"


async def test_update_skill_package_rejects_existing_name(env: Any) -> None:
    client, _server, auth = env
    first = await client.post(
        "/api/skill-packages",
        headers=auth,
        json={"name": "Office"},
    )
    second = await client.post(
        "/api/skill-packages",
        headers=auth,
        json={"name": "Research"},
    )

    response = await client.patch(
        f"/api/skill-packages/{second.json()['id']}",
        headers=auth,
        json={"name": first.json()["name"]},
    )

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "SKILL_PACKAGE_NAME_TAKEN"


async def test_package_skill_content_lifecycle(env: Any) -> None:
    client, _server, auth = env
    package_id = (
        await client.post(
            "/api/skill-packages",
            headers=auth,
            json={"name": "Office"},
        )
    ).json()["id"]

    created = await client.post(
        f"/api/skill-packages/{package_id}/skills",
        headers=auth,
        json={"name": "pdf-reader", "content": SAMPLE_SKILL},
    )
    assert created.status_code == 200, created.text
    assert created.json()["slug"] == "pdf-reader"

    detail = await client.get(
        f"/api/skill-packages/{package_id}/skills/pdf-reader",
        headers=auth,
    )
    assert detail.status_code == 200, detail.text
    assert detail.json()["raw"] == SAMPLE_SKILL

    updated = await client.put(
        f"/api/skill-packages/{package_id}/skills/pdf-reader",
        headers=auth,
        json={"content": "# Updated"},
    )
    assert updated.status_code == 200, updated.text

    deleted = await client.delete(
        f"/api/skill-packages/{package_id}/skills/pdf-reader",
        headers=auth,
    )
    assert deleted.status_code == 204, deleted.text
    assert (await client.get(f"/api/skill-packages/{package_id}/skills", headers=auth)).json() == []


async def test_export_skill_package_zip(env: Any) -> None:
    client, _server, auth = env
    package_id = (
        await client.post(
            "/api/skill-packages",
            headers=auth,
            json={"name": "Office", "description": ""},
        )
    ).json()["id"]
    for name, content in (
        ("pdf-reader", SAMPLE_SKILL),
        ("notes", "---\nname: notes\n---\n\n# Notes\n"),
    ):
        created = await client.post(
            f"/api/skill-packages/{package_id}/skills",
            headers=auth,
            json={"name": name, "content": content},
        )
        assert created.status_code == 200, created.text

    exported = await client.get(f"/api/skill-packages/{package_id}/export", headers=auth)
    assert exported.status_code == 200, exported.text
    assert exported.headers["content-type"].startswith("application/zip")
    assert "Office.zip" in exported.headers["content-disposition"]
    with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
        assert archive.read("pdf-reader/SKILL.md").decode("utf-8") == SAMPLE_SKILL
        assert "notes/SKILL.md" in archive.namelist()

    empty_id = (
        await client.post(
            "/api/skill-packages",
            headers=auth,
            json={"name": "Empty", "description": ""},
        )
    ).json()["id"]
    empty = await client.get(f"/api/skill-packages/{empty_id}/export", headers=auth)
    assert empty.status_code == 400


async def test_skill_package_download_can_be_disabled(env_boundary: Any) -> None:
    client, _server, _admin_auth, alice_auth, bob_auth, _ctx = env_boundary
    package_id = (
        await client.post(
            "/api/skill-packages",
            headers=alice_auth,
            json={"name": "Alice download", "shared": True},
        )
    ).json()["id"]
    created = await client.post(
        f"/api/skill-packages/{package_id}/skills",
        headers=alice_auth,
        json={"name": "pdf-reader", "content": SAMPLE_SKILL},
    )
    assert created.status_code == 200, created.text

    open_download = await client.get(f"/api/skill-packages/{package_id}/export", headers=bob_auth)
    assert open_download.status_code == 200, open_download.text

    closed = await client.patch(
        f"/api/skill-packages/{package_id}",
        headers=alice_auth,
        json={"allow_download": False},
    )
    assert closed.status_code == 200, closed.text
    assert closed.json()["allow_download"] is False

    denied = await client.get(f"/api/skill-packages/{package_id}/export", headers=bob_auth)
    assert denied.status_code == 403, denied.text
    assert denied.json()["error"]["code"] == "SKILL_PACKAGE_DOWNLOAD_DENIED"

    owner = await client.get(f"/api/skill-packages/{package_id}/export", headers=alice_auth)
    assert owner.status_code == 200, owner.text


async def test_private_skill_package_hidden_from_other_users(env_boundary: Any) -> None:
    client, _server, admin_auth, alice_auth, bob_auth, _ctx = env_boundary
    private = await client.post(
        "/api/skill-packages",
        headers=alice_auth,
        json={"name": "Alice private"},
    )
    assert private.status_code == 200, private.text
    assert private.json()["shared"] is False
    package_id = private.json()["id"]

    bob_list = await client.get("/api/skill-packages", headers=bob_auth)
    assert bob_list.status_code == 200, bob_list.text
    assert all(row["id"] != package_id for row in bob_list.json())

    bob_get = await client.get(f"/api/skill-packages/{package_id}", headers=bob_auth)
    assert bob_get.status_code == 404, bob_get.text
    assert bob_get.json()["error"]["code"] == "SKILL_PACKAGE_NOT_FOUND"

    shared = await client.patch(
        f"/api/skill-packages/{package_id}",
        headers=alice_auth,
        json={"shared": True},
    )
    assert shared.status_code == 200, shared.text
    assert shared.json()["shared"] is True

    bob_after = await client.get(f"/api/skill-packages/{package_id}", headers=bob_auth)
    assert bob_after.status_code == 200, bob_after.text
    assert bob_after.json()["can_write"] is False

    admin_list = await client.get("/api/skill-packages", headers=admin_auth)
    assert admin_list.status_code == 200, admin_list.text
    assert any(row["id"] == package_id for row in admin_list.json())


async def test_other_user_cannot_mutate_skill_package(env_boundary: Any) -> None:
    client, _server, _admin_auth, alice_auth, bob_auth, _ctx = env_boundary
    package_id = (
        await client.post(
            "/api/skill-packages",
            headers=alice_auth,
            json={"name": "Alice's skills"},
        )
    ).json()["id"]

    response = await client.patch(
        f"/api/skill-packages/{package_id}",
        headers=bob_auth,
        json={"name": "Bob's edit"},
    )

    assert response.status_code == 403, response.text
    assert response.json()["error"]["code"] == "FORBIDDEN"


async def test_other_user_cannot_mutate_package_skills(env_boundary: Any) -> None:
    client, _server, _admin_auth, alice_auth, bob_auth, _ctx = env_boundary
    package_id = (
        await client.post(
            "/api/skill-packages",
            headers=alice_auth,
            json={"name": "Alice's skill contents", "shared": True},
        )
    ).json()["id"]
    created = await client.post(
        f"/api/skill-packages/{package_id}/skills",
        headers=alice_auth,
        json={"name": "pdf-reader", "content": SAMPLE_SKILL},
    )
    assert created.status_code == 200, created.text

    alice_detail = await client.get(f"/api/skill-packages/{package_id}", headers=alice_auth)
    bob_detail = await client.get(f"/api/skill-packages/{package_id}", headers=bob_auth)
    assert alice_detail.status_code == 200, alice_detail.text
    assert bob_detail.status_code == 200, bob_detail.text
    assert alice_detail.json()["can_write"] is True
    assert bob_detail.json()["can_write"] is False

    create_skill = await client.post(
        f"/api/skill-packages/{package_id}/skills",
        headers=bob_auth,
        json={"name": "bob-skill", "content": SAMPLE_SKILL},
    )
    update_skill = await client.put(
        f"/api/skill-packages/{package_id}/skills/pdf-reader",
        headers=bob_auth,
        json={"content": "# hijack"},
    )
    delete_skill = await client.delete(
        f"/api/skill-packages/{package_id}/skills/pdf-reader",
        headers=bob_auth,
    )
    import_skill = await client.post(
        f"/api/skill-packages/{package_id}/skills/import",
        headers=bob_auth,
        json={"bundle_url": "https://skills.sh/demo/url-skill"},
    )
    for response in (create_skill, update_skill, delete_skill, import_skill):
        assert response.status_code == 403, response.text
        assert response.json()["error"]["code"] == "FORBIDDEN"


async def test_writable_package_list_respects_creator_permissions(
    env_boundary: Any,
) -> None:
    client, _server, admin_auth, alice_auth, bob_auth, _ctx = env_boundary
    alice_package = (
        await client.post(
            "/api/skill-packages",
            headers=alice_auth,
            json={"name": "Alice writable"},
        )
    ).json()
    bob_package = (
        await client.post(
            "/api/skill-packages",
            headers=bob_auth,
            json={"name": "Bob writable"},
        )
    ).json()

    alice_list = await client.get(
        "/api/skill-packages?writable_only=true",
        headers=alice_auth,
    )
    assert alice_list.status_code == 200, alice_list.text
    assert [row["id"] for row in alice_list.json()] == [alice_package["id"]]
    assert alice_list.json()[0]["can_write"] is True

    admin_list = await client.get(
        "/api/skill-packages?writable_only=true",
        headers=admin_auth,
    )
    assert admin_list.status_code == 200, admin_list.text
    assert {row["id"] for row in admin_list.json()} >= {
        alice_package["id"],
        bob_package["id"],
    }
    assert all(row["can_write"] is True for row in admin_list.json())


async def test_regular_user_cannot_push_to_another_users_package(
    env_alice_bob_agent: Any,
) -> None:
    client, _server, alice_auth, bob_auth, alice_agent_id = env_alice_bob_agent
    bob_package = (
        await client.post(
            "/api/skill-packages",
            headers=bob_auth,
            json={"name": "Bob push target"},
        )
    ).json()
    created_skill = await client.post(
        f"/api/agents/{alice_agent_id}/skills",
        headers=alice_auth,
        json={"name": "private-skill", "content": SAMPLE_SKILL},
    )
    assert created_skill.status_code == 201, created_skill.text
    forbidden = await client.post(
        f"/api/agents/{alice_agent_id}/skills/private-skill/push-to-package",
        headers=alice_auth,
        json={"package_id": bob_package["id"]},
    )
    assert forbidden.status_code == 403, forbidden.text
    assert forbidden.json()["error"]["code"] == "FORBIDDEN"


async def test_import_skill_url_into_package(env: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from octop.infra.skills import skills_hub

    client, _server, auth = env
    package_id = (
        await client.post(
            "/api/skill-packages",
            headers=auth,
            json={"name": "Imported"},
        )
    ).json()["id"]

    def _fake_resolve(**_kwargs: object) -> skills_hub.BundleResolveResult:
        return skills_hub.BundleResolveResult(
            name="url-skill",
            uploads=[("skills/url-skill/SKILL.md", SAMPLE_SKILL.encode("utf-8"))],
            source_url="https://skills.sh/demo/url-skill",
        )

    monkeypatch.setattr(skills_hub, "resolve_bundle_from_url", _fake_resolve)
    monkeypatch.setattr(skills_hub, "is_supported_skill_url", lambda _url: True)

    response = await client.post(
        f"/api/skill-packages/{package_id}/skills/import",
        headers=auth,
        json={"bundle_url": "https://skills.sh/demo/url-skill"},
    )
    assert response.status_code == 201, response.text
    assert response.json()["slug"] == "url-skill"

    listed = await client.get(
        f"/api/skill-packages/{package_id}/skills",
        headers=auth,
    )
    assert any(skill["slug"] == "url-skill" for skill in listed.json())


async def test_delete_package_strips_agent_mounts(env_with_main_agent: Any) -> None:
    client, server, auth, _main_agent_id = env_with_main_agent
    created = await client.post(
        "/api/agents/from-expert/general-assistant",
        headers=auth,
        json={
            "name": "Package Mount Agent",
            "backend": {
                "type": "local_shell",
                "root_dir": "/",
                "virtual_mode": True,
            },
        },
    )
    assert created.status_code == 201, created.text
    agent_id = created.json()["agent_id"]
    package_id = (
        await client.post(
            "/api/skill-packages",
            headers=auth,
            json={"name": "Office"},
        )
    ).json()["id"]
    await server.app_runtime.agent_registry.persist_skill_package_ids(agent_id, [package_id])

    deleted = await client.delete(f"/api/skill-packages/{package_id}", headers=auth)

    assert deleted.status_code == 204, deleted.text
    assert server.app_runtime.agent_registry.get_config(agent_id)["skill_package_ids"] == []


async def test_create_package_from_skillhub_returns_skills_and_rejects_duplicate_name(
    env: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from octop.api.routers import skill_packages
    from octop.infra.agents.experts.skillhub_market import SkillHubSkillset
    from octop.infra.skills.skill_package_from_skillhub import (
        create_package_from_skillhub as real_create,
    )

    client, _server, auth = env

    def _fake_create(store: Any, **kwargs: Any) -> Any:
        return real_create(
            store,
            **kwargs,
            fetch_skillset_fn=lambda _slug: SkillHubSkillset(
                slug="office-suite",
                display_name="Office Suite",
                summary="Office productivity skills",
                skill_slugs=("pdf-reader",),
            ),
            download_skill_files_fn=lambda _slug: [("SKILL.md", SAMPLE_SKILL.encode())],
        )

    monkeypatch.setattr(
        skill_packages,
        "create_package_from_skillhub",
        _fake_create,
        raising=False,
    )

    created = await client.post(
        "/api/skill-packages/from-skillhub",
        headers=auth,
        json={"slug": "office-suite", "icon_name": "FileText"},
    )

    assert created.status_code == 201, created.text
    assert created.json()["name"] == "Office Suite"
    assert created.json()["icon_name"] == "FileText"
    assert created.json()["skill_count"] == 1
    assert [skill["slug"] for skill in created.json()["skills"]] == ["pdf-reader"]

    duplicate = await client.post(
        "/api/skill-packages/from-skillhub",
        headers=auth,
        json={"slug": "office-suite"},
    )

    assert duplicate.status_code == 409, duplicate.text
    assert duplicate.json()["error"]["code"] == "SKILL_PACKAGE_NAME_TAKEN"


async def test_create_package_from_skillhub_maps_skill_download_error(
    env: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from octop.api.routers import skill_packages
    from octop.infra.skills.skillhub_market import SkillHubMarketError

    client, _server, auth = env

    def _raise_download_error(*_args: Any, **_kwargs: Any) -> None:
        raise SkillHubMarketError("SkillHub download failed")

    monkeypatch.setattr(skill_packages, "create_package_from_skillhub", _raise_download_error)

    response = await client.post(
        "/api/skill-packages/from-skillhub",
        headers=auth,
        json={"slug": "office-suite"},
    )

    assert response.status_code == 502, response.text
    assert response.json()["error"]["code"] == "EXPERT_MARKET_FAILED"


# --- local zip-style files create / overwrite -----------------------------


async def test_create_package_skill_from_files_payload(env: Any) -> None:
    client, server, auth = env
    package_id = (
        await client.post(
            "/api/skill-packages",
            headers=auth,
            json={"name": "Zip Bundle"},
        )
    ).json()["id"]
    skill_md = "---\nname: zip-demo\ndescription: from zip\n---\n\n# Zip Demo\n"

    created = await client.post(
        f"/api/skill-packages/{package_id}/skills",
        headers=auth,
        json={
            "name": "zip-demo",
            "files": [
                {"path": "SKILL.md", "content_base64": _b64(skill_md)},
                {"path": "notes.txt", "content_base64": _b64("hello")},
                {"path": "scripts/run.py", "content_base64": _b64("print(1)\n")},
            ],
        },
    )
    assert created.status_code == 200, created.text
    assert created.json()["slug"] == "zip-demo"

    from octop.infra.skills.skill_package_store import SkillPackageStore

    store = SkillPackageStore(
        repo=server.services.skill_package_repo,
        root=server.paths.skill_packages_dir,
    )
    skill_dir = store.package_skills_dir(package_id) / "zip-demo"
    assert (skill_dir / "SKILL.md").read_text(encoding="utf-8") == skill_md
    assert (skill_dir / "notes.txt").read_text(encoding="utf-8") == "hello"
    assert (skill_dir / "scripts" / "run.py").read_text(encoding="utf-8") == "print(1)\n"


async def test_create_package_skill_files_conflict_without_overwrite(env: Any) -> None:
    client, _server, auth = env
    package_id = (
        await client.post(
            "/api/skill-packages",
            headers=auth,
            json={"name": "Zip Bundle"},
        )
    ).json()["id"]
    await client.post(
        f"/api/skill-packages/{package_id}/skills",
        headers=auth,
        json={"name": "zip-demo", "content": SAMPLE_SKILL},
    )

    conflict = await client.post(
        f"/api/skill-packages/{package_id}/skills",
        headers=auth,
        json={
            "name": "zip-demo",
            "files": [{"path": "SKILL.md", "content_base64": _b64(SAMPLE_SKILL)}],
            "overwrite": False,
        },
    )
    assert conflict.status_code == 409, conflict.text
    assert conflict.json()["error"]["code"] == "SKILL_ALREADY_EXISTS"


async def test_package_skill_tree_file_and_content_only_update(env: Any) -> None:
    client, server, auth = env
    package_id = (
        await client.post(
            "/api/skill-packages",
            headers=auth,
            json={"name": "Tree Bundle"},
        )
    ).json()["id"]
    created = await client.post(
        f"/api/skill-packages/{package_id}/skills",
        headers=auth,
        json={
            "name": "demo",
            "files": [
                {"path": "SKILL.md", "content_base64": _b64(SAMPLE_SKILL)},
                {"path": "notes.txt", "content_base64": _b64("hello")},
                {"path": "references/guide.md", "content_base64": _b64("# Guide")},
            ],
        },
    )
    assert created.status_code == 200, created.text

    tree = await client.get(
        f"/api/skill-packages/{package_id}/skills/demo/tree",
        headers=auth,
    )
    assert tree.status_code == 200, tree.text
    assert {row["path"] for row in tree.json()} == {
        "skills/demo/SKILL.md",
        "skills/demo/notes.txt",
        "skills/demo/references",
    }

    nested = await client.get(
        f"/api/skill-packages/{package_id}/skills/demo/tree",
        headers=auth,
        params={"path": "references"},
    )
    assert nested.status_code == 200, nested.text
    assert nested.json() == [
        {"path": "skills/demo/references/guide.md", "is_dir": False, "size": 7},
    ]

    text = await client.get(
        f"/api/skill-packages/{package_id}/skills/demo/file",
        headers=auth,
        params={"path": "notes.txt"},
    )
    assert text.status_code == 200, text.text
    assert text.json()["content"] == "hello"

    download = await client.get(
        f"/api/skill-packages/{package_id}/skills/demo/download",
        headers=auth,
        params={"path": "references/guide.md"},
    )
    assert download.status_code == 200, download.text
    assert download.content == b"# Guide"

    updated_md = "---\nname: demo\ndescription: kept siblings\n---\n\n# Updated\n"
    updated = await client.put(
        f"/api/skill-packages/{package_id}/skills/demo",
        headers=auth,
        json={"content": updated_md},
    )
    assert updated.status_code == 200, updated.text

    from octop.infra.skills.skill_package_store import SkillPackageStore

    skill_dir = (
        SkillPackageStore(
            repo=server.services.skill_package_repo,
            root=server.paths.skill_packages_dir,
        ).package_skills_dir(package_id)
        / "demo"
    )
    assert (skill_dir / "SKILL.md").read_text(encoding="utf-8") == updated_md
    assert (skill_dir / "notes.txt").read_text(encoding="utf-8") == "hello"
    assert (skill_dir / "references" / "guide.md").read_text(encoding="utf-8") == "# Guide"


async def test_create_package_skill_files_overwrite_replaces_stale_siblings(env: Any) -> None:
    client, server, auth = env
    package_id = (
        await client.post(
            "/api/skill-packages",
            headers=auth,
            json={"name": "Zip Bundle"},
        )
    ).json()["id"]
    first = await client.post(
        f"/api/skill-packages/{package_id}/skills",
        headers=auth,
        json={
            "name": "zip-demo",
            "files": [
                {"path": "SKILL.md", "content_base64": _b64(SAMPLE_SKILL)},
                {"path": "stale.txt", "content_base64": _b64("old")},
            ],
        },
    )
    assert first.status_code == 200, first.text

    updated_md = "---\nname: zip-demo\ndescription: replaced\n---\n\n# New\n"
    second = await client.post(
        f"/api/skill-packages/{package_id}/skills",
        headers=auth,
        json={
            "name": "zip-demo",
            "files": [
                {"path": "SKILL.md", "content_base64": _b64(updated_md)},
                {"path": "fresh.txt", "content_base64": _b64("new")},
            ],
            "overwrite": True,
        },
    )
    assert second.status_code == 200, second.text

    from octop.infra.skills.skill_package_store import SkillPackageStore

    skill_dir = (
        SkillPackageStore(
            repo=server.services.skill_package_repo,
            root=server.paths.skill_packages_dir,
        ).package_skills_dir(package_id)
        / "zip-demo"
    )
    assert (skill_dir / "SKILL.md").read_text(encoding="utf-8") == updated_md
    assert (skill_dir / "fresh.txt").read_text(encoding="utf-8") == "new"
    assert not (skill_dir / "stale.txt").exists()


async def test_create_package_skill_rejects_invalid_base64_files(env: Any) -> None:
    client, _server, auth = env
    package_id = (
        await client.post(
            "/api/skill-packages",
            headers=auth,
            json={"name": "Zip Bundle"},
        )
    ).json()["id"]
    response = await client.post(
        f"/api/skill-packages/{package_id}/skills",
        headers=auth,
        json={
            "name": "bad-b64",
            "files": [{"path": "SKILL.md", "content_base64": "%%%not-base64%%%"}],
        },
    )
    assert response.status_code == 400, response.text
