"""Integration coverage for global skill package HTTP routes."""

from __future__ import annotations

import base64
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
        json={"name": "Office", "description": ""},
    )

    assert created.status_code == 200, created.text
    package_id = created.json()["id"]

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
