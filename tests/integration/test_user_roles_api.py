"""Role templates supply defaults and do not own user rows."""

from __future__ import annotations

from tests.support.auth import TEST_PASSWORD, bearer, login


async def test_builtin_roles_invite_reads_role_at_redeem(env):
    c, _srv, auth = env
    listed = await c.get("/api/users/roles", headers=auth)
    assert listed.status_code == 200, listed.text
    by_id = {row["user_role_id"]: row for row in listed.json()}
    assert by_id["admin"]["deletable"] is False
    assert by_id["admin"]["immutable"] is True
    assert by_id["admin"]["policies"] == []
    assert by_id["admin"]["system_role"] == "admin"
    assert "channels" in by_id["user"]["permissions"]
    assert by_id["user"]["policies"] == []

    denied = await c.delete("/api/users/roles/admin", headers=auth)
    assert denied.status_code == 403

    created = await c.post(
        "/api/users/roles",
        headers=auth,
        json={
            "user_role_name": "分析师",
            "description": "只读分析工作",
            "permissions": ["browser"],
            "policies": [{"name": "token_quota", "value": "1000"}],
        },
    )
    assert created.status_code == 201, created.text
    role = created.json()
    assert role["description"] == "只读分析工作"
    assert role["policies"] == [{"name": "token_quota", "value": "1000"}]
    assert role["workspace_root_dir"] is None
    assert role["max_agents"] is None

    user = await c.post(
        "/api/users",
        headers=auth,
        json={
            "username": "carol",
            "password": "TestPass12",
            "role": "user",
            "permissions": ["browser"],
            "role_name": "分析师",
            "user_role_id": role["user_role_id"],
            "token_quota": 1000,
        },
    )
    assert user.status_code == 201, user.text
    assert user.json()["role_name"] == "分析师"
    assert user.json()["user_role_id"] == role["user_role_id"]
    uid = user.json()["id"]

    renamed = await c.patch(
        f"/api/users/roles/{role['user_role_id']}",
        headers=auth,
        json={
            "user_role_name": "分析",
            "permissions": ["desktop"],
            "policies": [{"name": "token_quota", "value": "5"}],
        },
    )
    assert renamed.status_code == 200, renamed.text
    kept = await c.get(f"/api/users/{uid}", headers=auth)
    assert kept.json()["role_name"] == "分析师"
    assert kept.json()["permissions"] == ["browser"]
    assert kept.json()["token_quota"] == 1000

    deleted = await c.delete(f"/api/users/roles/{role['user_role_id']}", headers=auth)
    assert deleted.status_code == 204
    kept = await c.get(f"/api/users/{uid}", headers=auth)
    assert kept.json()["role_name"] == "分析师"
    assert kept.json()["token_quota"] == 1000

    invite = await c.post(
        "/api/users/invites",
        headers=auth,
        json={"user_role_id": "user", "note": "later"},
    )
    assert invite.status_code == 201, invite.text
    assert invite.json()["role_name"] == "用户"
    assert invite.json()["user_role_id"] == "user"
    assert "system_role" not in invite.json()

    patched = await c.patch(
        "/api/users/roles/user",
        headers=auth,
        json={"user_role_name": "普通用户", "permissions": ["browser"]},
    )
    assert patched.status_code == 200, patched.text

    redeem = await c.post(
        "/api/auth/invite/redeem",
        json={
            "code": invite.json()["code"],
            "username": "invited_one",
            "password": "InvitePass12",
        },
    )
    assert redeem.status_code == 200, redeem.text
    assert redeem.json()["user"]["role"] == "user"
    assert redeem.json()["user"]["permissions"] == ["browser"]

    invited = await c.get("/api/users", headers=auth)
    row = next(item for item in invited.json() if item["username"] == "invited_one")
    assert row["role_name"] == "普通用户"
    assert row["user_role_id"] == "user"
    assert row["permissions"] == ["browser"]

    me = await c.get("/api/auth/me", headers=auth)
    admin_id = me.json()["id"]
    admin_row = next(item for item in invited.json() if item["id"] == admin_id)
    assert admin_row["role_name"] in (None, "")


async def test_role_patch_without_policies_keeps_existing_policies(env):
    c, _srv, auth = env
    created = await c.post(
        "/api/users/roles",
        headers=auth,
        json={
            "user_role_name": "限额",
            "permissions": ["browser"],
            "policies": [
                {"name": "token_quota", "value": "1000"},
                {"name": "max_agents", "value": "3"},
            ],
        },
    )
    assert created.status_code == 201, created.text
    role_id = created.json()["user_role_id"]

    patched = await c.patch(
        f"/api/users/roles/{role_id}",
        headers=auth,
        json={"permissions": ["desktop"]},
    )
    assert patched.status_code == 200, patched.text
    names = {item["name"]: item["value"] for item in patched.json()["policies"]}
    assert names == {"token_quota": "1000", "max_agents": "3"}


async def test_redeem_fails_when_named_role_is_gone(env):
    c, _srv, auth = env
    invite = await c.post(
        "/api/users/invites",
        headers=auth,
        json={"user_role_id": "user"},
    )
    assert invite.status_code == 201, invite.text
    deleted = await c.delete("/api/users/roles/user", headers=auth)
    assert deleted.status_code == 204, deleted.text

    redeem = await c.post(
        "/api/auth/invite/redeem",
        json={
            "code": invite.json()["code"],
            "username": "missing_role",
            "password": "InvitePass12",
        },
    )
    assert redeem.status_code == 409, redeem.text
    assert redeem.json()["error"]["code"] == "INVITE_ROLE_MISSING"
    listed = await c.get("/api/users", headers=auth)
    assert all(item["username"] != "missing_role" for item in listed.json())


async def test_non_admin_cannot_grant_administrator(env):
    c, _srv, auth = env
    created = await c.post(
        "/api/users",
        headers=auth,
        json={
            "username": "clerk",
            "password": TEST_PASSWORD,
            "role": "user",
            "permissions": ["users"],
        },
    )
    assert created.status_code == 201, created.text
    clerk = bearer(await login(c, username="clerk", password=TEST_PASSWORD))

    denied_user = await c.post(
        "/api/users",
        headers=clerk,
        json={"username": "boss", "password": TEST_PASSWORD, "role": "admin"},
    )
    assert denied_user.status_code == 403, denied_user.text

    denied_invite = await c.post(
        "/api/users/invites",
        headers=clerk,
        json={"user_role_id": "admin"},
    )
    assert denied_invite.status_code == 403, denied_invite.text

    target = created.json()["id"]
    denied_patch = await c.patch(
        f"/api/users/{target}",
        headers=clerk,
        json={"role": "admin"},
    )
    assert denied_patch.status_code == 403, denied_patch.text


_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


async def test_user_and_role_avatars_roundtrip(env):
    c, _srv, auth = env
    me = await c.get("/api/auth/me", headers=auth)
    user_id = me.json()["id"]
    uploaded = await c.post(
        f"/api/users/{user_id}/avatar",
        headers=auth,
        files={"file": ("avatar.png", _PNG, "image/png")},
    )
    assert uploaded.status_code == 201, uploaded.text
    avatar_url = uploaded.json()["avatar_url"]
    assert avatar_url.startswith(f"/api/users/{user_id}/avatar?v=")
    fetched = await c.get(f"/api/users/{user_id}/avatar", headers=auth)
    assert fetched.status_code == 200
    assert fetched.headers["content-type"].startswith("image/png")
    assert fetched.content == _PNG

    role = await c.post(
        "/api/users/roles",
        headers=auth,
        json={"user_role_name": "带头像", "permissions": ["browser"]},
    )
    assert role.status_code == 201, role.text
    role_id = role.json()["user_role_id"]
    role_upload = await c.post(
        f"/api/users/roles/{role_id}/avatar",
        headers=auth,
        files={"file": ("avatar.png", _PNG, "image/png")},
    )
    assert role_upload.status_code == 201, role_upload.text
    listed = await c.get("/api/users/roles", headers=auth)
    saved = next(item for item in listed.json() if item["user_role_id"] == role_id)
    assert saved["avatar_url"].startswith(f"/api/users/roles/{role_id}/avatar?v=")

    chosen = await c.patch(
        f"/api/users/roles/{role_id}",
        headers=auth,
        json={"avatar_icon": "admin"},
    )
    assert chosen.status_code == 200, chosen.text
    assert chosen.json()["avatar_icon"] == "admin"
    assert chosen.json()["avatar_url"] is None
    cleared = await c.get(f"/api/users/roles/{role_id}/avatar", headers=auth)
    assert cleared.status_code == 404

    user_icon = await c.patch(
        f"/api/users/{user_id}",
        headers=auth,
        json={"avatar_icon": "curly"},
    )
    assert user_icon.status_code == 200, user_icon.text
    assert user_icon.json()["avatar_icon"] == "curly"
    assert user_icon.json()["avatar_url"] is None
    invalid = await c.patch(
        f"/api/users/{user_id}",
        headers=auth,
        json={"avatar_icon": "Not A Icon"},
    )
    assert invalid.status_code == 400

    removed = await c.delete(f"/api/users/roles/{role_id}", headers=auth)
    assert removed.status_code == 204
    gone = await c.get(f"/api/users/roles/{role_id}/avatar", headers=auth)
    assert gone.status_code == 404
