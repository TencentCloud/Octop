"""Integration coverage for agent-mounted global skill packages."""

from __future__ import annotations

from typing import Any

PACKAGE_SKILL = """---
name: pdf-reader
description: Read PDF documents
---
# PDF Reader
"""


async def _create_package_with_skill(client: Any, auth: dict[str, str]) -> str:
    package = await client.post(
        "/api/skill-packages",
        headers=auth,
        json={"name": "Office"},
    )
    assert package.status_code == 200, package.text
    package_id = package.json()["id"]
    skill = await client.post(
        f"/api/skill-packages/{package_id}/skills",
        headers=auth,
        json={"name": "pdf-reader", "content": PACKAGE_SKILL},
    )
    assert skill.status_code == 200, skill.text
    return package_id


async def test_mount_package_lists_skills_and_allows_disabling(env_with_agent: Any) -> None:
    client, _server, auth, agent_id = env_with_agent
    package_id = await _create_package_with_skill(client, auth)

    mounted = await client.put(
        f"/api/agents/{agent_id}/skill-packages",
        headers=auth,
        json={"package_ids": [package_id]},
    )
    assert mounted.status_code == 200, mounted.text
    assert mounted.json() == {"package_ids": [package_id]}

    packages = await client.get(f"/api/agents/{agent_id}/skill-packages", headers=auth)
    assert packages.status_code == 200, packages.text
    assert packages.json() == {
        "package_ids": [package_id],
        "packages": [
            {
                "id": package_id,
                "name": "Office",
                "description": "",
                "skills": [
                    {
                        "slug": "pdf-reader",
                        "name": "pdf-reader",
                        "description": "Read PDF documents",
                        "path": "skills/pdf-reader/SKILL.md",
                        "kind": "package",
                        "package_id": package_id,
                    }
                ],
            }
        ],
    }

    skills = await client.get(f"/api/agents/{agent_id}/skills", headers=auth)
    assert skills.status_code == 200, skills.text
    assert any(skill["slug"] == "pdf-reader" for skill in skills.json()), skills.json()
    package_skill = next(skill for skill in skills.json() if skill["slug"] == "pdf-reader")
    assert package_skill["kind"] == "package"
    assert package_skill["enabled"] is True

    disabled = await client.post(
        f"/api/agents/{agent_id}/skills/pdf-reader/disable",
        headers=auth,
    )
    assert disabled.status_code == 204, disabled.text
    skills = await client.get(f"/api/agents/{agent_id}/skills", headers=auth)
    package_skill = next(skill for skill in skills.json() if skill["slug"] == "pdf-reader")
    assert package_skill["enabled"] is False


async def test_package_only_skill_rejects_workspace_writes(env_with_agent: Any) -> None:
    client, _server, auth, agent_id = env_with_agent
    package_id = await _create_package_with_skill(client, auth)
    mounted = await client.put(
        f"/api/agents/{agent_id}/skill-packages",
        headers=auth,
        json={"package_ids": [package_id]},
    )
    assert mounted.status_code == 200, mounted.text

    requests = [
        client.post(
            f"/api/agents/{agent_id}/skills",
            headers=auth,
            json={"name": "pdf-reader", "content": PACKAGE_SKILL},
        ),
        client.put(
            f"/api/agents/{agent_id}/skills/pdf-reader",
            headers=auth,
            json={"content": PACKAGE_SKILL},
        ),
        client.delete(f"/api/agents/{agent_id}/skills/pdf-reader", headers=auth),
    ]
    for request in requests:
        response = await request
        assert response.status_code == 403, response.text
        assert response.json()["error"]["code"] == "FORBIDDEN"
