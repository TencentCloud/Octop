"""Mounted-package skills must reject every agent-workspace write path.

``test_agent_skill_packages.py`` pins the ``403`` for create / update / delete /
push-to-package. These cases cover the three write paths that can still land a
workspace copy over a slug the agent only gets from a mounted skill package:
``skills/copy``, ``skills/import`` and ``skills/hub/install``.
"""

from __future__ import annotations

from typing import Any

import pytest

SLUG = "guard-demo"

PACKAGE_SKILL = f"""---
name: {SLUG}
description: Supplied only by a mounted package
---
# Guard demo
"""

FOREIGN_SKILL = f"""---
name: {SLUG}
description: Foreign content from another source
---
# Foreign
"""

MANIFEST = f"skills/{SLUG}/SKILL.md"


async def _mount_package_skill(client: Any, auth: dict[str, str], agent_id: str) -> str:
    package = await client.post(
        "/api/skill-packages",
        headers=auth,
        json={"name": "Guard source"},
    )
    assert package.status_code == 200, package.text
    package_id = package.json()["id"]
    created = await client.post(
        f"/api/skill-packages/{package_id}/skills",
        headers=auth,
        json={"name": SLUG, "content": PACKAGE_SKILL},
    )
    assert created.status_code == 200, created.text
    mounted = await client.put(
        f"/api/agents/{agent_id}/skill-packages",
        headers=auth,
        json={"package_ids": [package_id]},
    )
    assert mounted.status_code == 200, mounted.text
    return package_id


async def _assert_still_package_only(client: Any, auth: dict[str, str], agent_id: str) -> None:
    rows = (await client.get(f"/api/agents/{agent_id}/skills", headers=auth)).json()
    row = next(item for item in rows if item["slug"] == SLUG)
    assert row["kind"] == "package", rows


async def test_copy_from_agent_rejects_package_only_slug(env_with_agent: Any) -> None:
    client, srv, auth, agent_id = env_with_agent
    await _mount_package_skill(client, auth, agent_id)

    source = await client.post(
        "/api/agents/from-expert/default",
        headers=auth,
        json={"name": "guard-src"},
    )
    assert source.status_code == 201, source.text
    src_id = source.json()["agent_id"]
    src_ws = srv.app_runtime.agent_registry.workspace_for_agent(src_id)
    if src_ws is None:  # pragma: no cover - mirrors the existing copy test
        pytest.skip("workspace not available before bootstrap")
    await src_ws.aupload_many([(MANIFEST, FOREIGN_SKILL.encode("utf-8"))])

    for overwrite in (False, True):
        copied = await client.post(
            f"/api/agents/{agent_id}/skills/copy",
            headers=auth,
            json={"source_agent_id": src_id, "slug": SLUG, "overwrite": overwrite},
        )
        assert copied.status_code == 403, copied.text
        assert copied.json()["error"]["code"] == "FORBIDDEN"

    dest = srv.app_runtime.agent_registry.get_agent(agent_id)
    assert await dest.workspace.aread_text(MANIFEST) is None
    await _assert_still_package_only(client, auth, agent_id)


async def test_url_import_rejects_package_only_slug(
    env_with_agent: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, srv, auth, agent_id = env_with_agent
    from octop.infra.skills import skills_hub

    await _mount_package_skill(client, auth, agent_id)

    def _fake_resolve(**_kwargs: object) -> skills_hub.BundleResolveResult:
        return skills_hub.BundleResolveResult(
            name=SLUG,
            uploads=[(MANIFEST, FOREIGN_SKILL.encode("utf-8"))],
            source_url="https://github.com/example/repo",
        )

    monkeypatch.setattr(skills_hub, "resolve_bundle_from_url", _fake_resolve)

    imported = await client.post(
        f"/api/agents/{agent_id}/skills/import",
        headers=auth,
        json={"bundle_url": "https://github.com/example/repo", "overwrite": False},
    )
    assert imported.status_code == 403, imported.text
    assert imported.json()["error"]["code"] == "FORBIDDEN"

    agent = srv.app_runtime.agent_registry.get_agent(agent_id)
    assert await agent.workspace.aread_text(MANIFEST) is None
    await _assert_still_package_only(client, auth, agent_id)


async def test_hub_install_rejects_package_only_slug(
    env_with_agent: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, srv, auth, agent_id = env_with_agent
    from octop.infra.skills import skillhub_market

    await _mount_package_skill(client, auth, agent_id)

    async def fake_download(
        slug: str,
        *,
        host: str | None = None,
        timeout: float = 30.0,
    ) -> list[tuple[str, bytes]]:
        assert slug == SLUG
        return [(MANIFEST.removeprefix(f"skills/{SLUG}/"), FOREIGN_SKILL.encode("utf-8"))]

    monkeypatch.setattr(skillhub_market, "download_skillhub_package", fake_download)

    installed = await client.post(
        f"/api/agents/{agent_id}/skills/hub/install",
        headers=auth,
        json={"skill_name": SLUG, "enable": True},
    )
    assert installed.status_code == 403, installed.text
    assert installed.json()["error"]["code"] == "FORBIDDEN"

    agent = srv.app_runtime.agent_registry.get_agent(agent_id)
    assert await agent.workspace.aread_text(MANIFEST) is None
    await _assert_still_package_only(client, auth, agent_id)


async def test_hub_install_allows_slug_once_copied_from_its_package(
    env_with_agent: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The sanctioned materialize-then-write flow must keep working."""
    client, srv, auth, agent_id = env_with_agent
    from octop.infra.skills import skillhub_market

    package_id = await _mount_package_skill(client, auth, agent_id)
    copied = await client.post(
        f"/api/agents/{agent_id}/skill-packages/{package_id}/copy",
        headers=auth,
        json={"skill_slugs": [SLUG]},
    )
    assert copied.status_code == 200, copied.text

    async def fake_download(
        slug: str,
        *,
        host: str | None = None,
        timeout: float = 30.0,
    ) -> list[tuple[str, bytes]]:
        assert slug == SLUG
        return [("SKILL.md", FOREIGN_SKILL.encode("utf-8"))]

    monkeypatch.setattr(skillhub_market, "download_skillhub_package", fake_download)

    installed = await client.post(
        f"/api/agents/{agent_id}/skills/hub/install",
        headers=auth,
        json={"skill_name": SLUG, "enable": True},
    )
    assert installed.status_code == 201, installed.text

    agent = srv.app_runtime.agent_registry.get_agent(agent_id)
    raw = await agent.workspace.aread_text(MANIFEST)
    assert raw is not None
    assert "Foreign content" in raw
