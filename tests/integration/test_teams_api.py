"""Team HTTP API."""

from __future__ import annotations

import pytest

from tests.support.auth import create_user, resolve_user_id

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


async def test_team_workspace_dir_on_host_root(env):
    c, srv, auth = env
    assert srv.app_runtime is not None
    alpha = await _expert(c, auth, "alpha-ws")
    beta = await _expert(c, auth, "beta-ws")
    home = srv.app_runtime.agent_registry.paths.root
    picked = home / "team-picked-ws"
    created = await c.post(
        "/api/teams",
        headers=auth,
        json={
            "name": "squad-ws",
            "member_ids": [alpha, beta],
            "config": {
                "backend": {"type": "filesystem", "virtual_mode": True, "root_dir": "/"},
                "workspace_dir": str(picked),
            },
        },
    )
    assert created.status_code == 200, created.text
    team_id = created.json()["agent_id"]
    detail = (await c.get(f"/api/agents/{team_id}", headers=auth)).json()
    assert detail["config"]["workspace_dir"] == str(picked)
    assert picked.is_dir()

    patched = await c.patch(
        f"/api/teams/{team_id}",
        headers=auth,
        json={"name": "squad-ws", "config": {"workspace_dir": str(home / "team-moved-ws")}},
    )
    assert patched.status_code == 200, patched.text
    again = (await c.get(f"/api/agents/{team_id}", headers=auth)).json()
    assert again["config"]["workspace_dir"] == str(picked)


def _team_ids(payload: list[dict]) -> set[str]:
    return {item["agent_id"] for item in payload if item.get("kind") == "team"}


async def test_share_team_with_everyone_and_a_group(env):
    c, _, admin_auth = env
    owner_auth = await create_user(c, admin_auth, username="team_owner")
    peer_auth = await create_user(c, admin_auth, username="team_peer")
    outsider_auth = await create_user(c, admin_auth, username="team_out")
    alpha = await _expert(c, owner_auth, "alpha-share")
    beta = await _expert(c, owner_auth, "beta-share")

    denied = await c.post(
        "/api/teams",
        headers=owner_auth,
        json={
            "name": "closed squad",
            "member_ids": [alpha, beta],
            "visibility": "groups",
            "group_ids": [],
        },
    )
    assert denied.status_code == 400, denied.text
    assert _team_ids((await c.get("/api/teams", headers=owner_auth)).json()) == set()

    created = await c.post(
        "/api/teams",
        headers=owner_auth,
        json={"name": "squad", "member_ids": [alpha, beta], "visibility": "owner"},
    )
    assert created.status_code == 200, created.text
    team_id = created.json()["agent_id"]
    assert created.json()["visibility"] == "owner"
    assert created.json()["is_shared"] is False
    assert created.json()["is_owner"] is True

    hidden = await c.get("/api/agents", headers=peer_auth)
    assert team_id not in _team_ids(hidden.json())
    assert (await c.get(f"/api/teams/{team_id}", headers=peer_auth)).status_code == 403

    shared = await c.patch(
        f"/api/teams/{team_id}",
        headers=owner_auth,
        json={"visibility": "all"},
    )
    assert shared.status_code == 200, shared.text
    assert shared.json()["visibility"] == "all"
    assert shared.json()["is_shared"] is True

    peer_list = await c.get("/api/agents", headers=peer_auth)
    assert peer_list.status_code == 200, peer_list.text
    peer_row = next(item for item in peer_list.json() if item["agent_id"] == team_id)
    assert peer_row["is_owner"] is False
    assert peer_row["visibility"] == "all"
    assert {item["name"] for item in peer_row["members"]} == {"alpha-share", "beta-share"}

    peer_team = await c.get(f"/api/teams/{team_id}", headers=peer_auth)
    assert peer_team.status_code == 200, peer_team.text
    assert peer_team.json()["is_owner"] is False
    assert {item["agent_id"] for item in peer_team.json()["members"]} == {alpha, beta}
    assert team_id in _team_ids((await c.get("/api/teams", headers=peer_auth)).json())

    forbidden = await c.patch(
        f"/api/teams/{team_id}",
        headers=peer_auth,
        json={"name": "hijack"},
    )
    assert forbidden.status_code == 403, forbidden.text

    peer_id = await resolve_user_id(c, admin_auth, "team_peer")
    group = await c.post("/api/user-groups", headers=admin_auth, json={"name": "crew"})
    assert group.status_code == 201, group.text
    group_id = group.json()["user_group_id"]
    members = await c.put(
        f"/api/user-groups/{group_id}/members",
        headers=admin_auth,
        json={"user_ids": [peer_id]},
    )
    assert members.status_code == 200, members.text

    narrowed = await c.patch(
        f"/api/teams/{team_id}",
        headers=owner_auth,
        json={"visibility": "groups", "group_ids": [group_id]},
    )
    assert narrowed.status_code == 200, narrowed.text
    assert narrowed.json()["visibility"] == "groups"
    assert narrowed.json()["group_ids"] == [group_id]

    assert team_id in _team_ids((await c.get("/api/agents", headers=peer_auth)).json())
    assert team_id not in _team_ids((await c.get("/api/agents", headers=outsider_auth)).json())
    assert (await c.get(f"/api/teams/{team_id}", headers=outsider_auth)).status_code == 403
