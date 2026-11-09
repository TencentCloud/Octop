"""Team HTTP API."""

from __future__ import annotations

import pytest

_LEAD = "/experts/avatars/team-lead.svg"
_CIRCLE = "/experts/avatars/team-circle.svg"


@pytest.fixture
async def env(env_with_provider):
    yield env_with_provider


async def _expert(c, auth, name: str) -> str:
    created = await c.post("/api/agents", headers=auth, json={"name": name})
    assert created.status_code == 201, created.text
    return created.json()["agent_id"]


async def test_patch_team_icon_url_persists_sample_portrait(env):
    c, _, auth = env
    alpha = await _expert(c, auth, "alpha")
    beta = await _expert(c, auth, "beta")
    created = await c.post(
        "/api/teams",
        headers=auth,
        json={
            "name": "squad",
            "member_ids": [alpha, beta],
            "icon_url": _LEAD,
        },
    )
    assert created.status_code == 200, created.text
    team_id = created.json()["agent_id"]
    assert created.json()["icon_url"] == _LEAD

    renamed = await c.patch(
        f"/api/teams/{team_id}",
        headers=auth,
        json={"name": "squad renamed"},
    )
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["name"] == "squad renamed"
    assert renamed.json()["icon_url"] == _LEAD

    patched = await c.patch(
        f"/api/teams/{team_id}",
        headers=auth,
        json={"icon_url": _CIRCLE},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["icon_url"] == _CIRCLE

    listed = await c.get("/api/agents", headers=auth)
    assert listed.status_code == 200, listed.text
    row = next(item for item in listed.json() if item["agent_id"] == team_id)
    assert row["icon_url"] == _CIRCLE
