"""Expert avatar upload HTTP surface."""

from __future__ import annotations

import pytest

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


@pytest.fixture
async def env(env_with_agent):
    yield env_with_agent


async def test_upload_get_delete_avatar(env):
    c, srv, auth, agent_id = env
    r = await c.post(
        f"/api/agents/{agent_id}/avatar",
        headers=auth,
        files={"file": ("face.png", PNG, "image/png")},
    )
    assert r.status_code == 201, r.text
    icon_url = r.json()["icon_url"]
    assert icon_url.startswith(f"/api/agents/{agent_id}/avatar?")
    assert "v=" in icon_url

    listed = (await c.get("/api/agents", headers=auth)).json()
    row = next(a for a in listed if a["agent_id"] == agent_id)
    assert row["icon_url"] == icon_url
    assert "avatar" not in (row.get("config") or {})

    got = await c.get(icon_url, headers=auth)
    assert got.status_code == 200
    assert got.content == PNG
    assert got.headers["content-type"].startswith("image/png")

    workspace = srv.app_runtime.agent_registry.workspace_for_agent(agent_id)
    assert workspace is not None
    stored = await workspace.adownload_bytes(".octop/avatar.png")
    assert stored == PNG

    deleted = await c.delete(f"/api/agents/{agent_id}/avatar", headers=auth)
    assert deleted.status_code == 204
    missing = await c.get(icon_url, headers=auth)
    assert missing.status_code == 404
    cleared = next(
        a for a in (await c.get("/api/agents", headers=auth)).json() if a["agent_id"] == agent_id
    )
    assert cleared["icon_url"] in (None, "")


async def test_reject_non_image_avatar(env):
    c, _srv, auth, agent_id = env
    r = await c.post(
        f"/api/agents/{agent_id}/avatar",
        headers=auth,
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "AVATAR_INVALID"
