"""tests/integration/test_users_api.py"""

from __future__ import annotations


async def test_create_list_get_delete(env):
    c, srv, auth = env
    r = await c.post(
        "/api/users",
        headers=auth,
        json={"username": "alice", "password": "TestPass12", "role": "user"},
    )
    assert r.status_code == 201
    uid = r.json()["id"]

    r = await c.get("/api/users", headers=auth)
    usernames = [u["username"] for u in r.json()]
    assert "alice" in usernames

    r = await c.get(f"/api/users/{uid}", headers=auth)
    assert r.json()["username"] == "alice"
    assert r.json()["email"] is None
    assert r.json()["has_password"] is True
    assert r.json()["sso_linked"] is False
    assert r.json()["login_locked"] is False
    assert r.json()["login_retry_after_seconds"] == 0
    assert isinstance(r.json()["created_at"], int)
    assert r.json()["created_at"] > 0

    r = await c.delete(f"/api/users/{uid}", headers=auth)
    assert r.status_code == 204
    r = await c.get(f"/api/users/{uid}", headers=auth)
    assert r.status_code == 404


async def test_admin_can_save_own_account_with_empty_permissions(env):
    """Admin accounts store permissions as []. Saving that list must not 403."""
    c, _srv, auth = env
    me = (await c.get("/api/auth/me", headers=auth)).json()
    saved = await c.patch(
        f"/api/users/{me['id']}",
        headers=auth,
        json={
            "display_name": "Root",
            "role": "admin",
            "permissions": [],
        },
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["display_name"] == "Root"
    assert saved.json()["role"] == "admin"


async def test_non_admin_gets_403(env):
    c, srv, _ = env
    admin_auth = env[2]
    await c.post(
        "/api/users",
        headers=admin_auth,
        json={"username": "bob", "password": "TestPass12", "role": "user"},
    )
    tok = (
        await c.post("/api/auth/login", json={"username": "bob", "password": "TestPass12"})
    ).json()["access_token"]
    user_auth = {"Authorization": f"Bearer {tok}"}
    r = await c.get("/api/users", headers=user_auth)
    assert r.status_code == 403


async def test_admin_cannot_delete_self(env):
    c, srv, auth = env
    me = (await c.get("/api/auth/me", headers=auth)).json()
    r = await c.delete(f"/api/users/{me['id']}", headers=auth)
    assert r.status_code == 403


async def test_admin_cannot_demote_self(env):
    c, srv, auth = env
    me = (await c.get("/api/auth/me", headers=auth)).json()
    r = await c.patch(f"/api/users/{me['id']}", headers=auth, json={"role": "user"})
    assert r.status_code == 403


async def test_admin_can_enable_disabled_user(env):
    c, srv, auth = env
    r = await c.post(
        "/api/users",
        headers=auth,
        json={"username": "disabled_user", "password": "TestPass12", "role": "user"},
    )
    assert r.status_code == 201
    uid = r.json()["id"]

    r = await c.patch(f"/api/users/{uid}", headers=auth, json={"disabled": True})
    assert r.status_code == 200
    assert r.json()["disabled"] is True

    r = await c.patch(f"/api/users/{uid}", headers=auth, json={"disabled": False})
    assert r.status_code == 200
    assert r.json()["disabled"] is False


async def test_admin_can_unlock_login(env):
    c, srv, auth = env
    r = await c.post(
        "/api/users",
        headers=auth,
        json={"username": "lock_user", "password": "TestPass12", "role": "user"},
    )
    uid = r.json()["id"]
    max_attempts = srv.services.config.login_max_attempts
    for _ in range(max_attempts):
        await c.post("/api/auth/login", json={"username": "lock_user", "password": "bad"})
    r = await c.get(f"/api/users/{uid}", headers=auth)
    assert r.json()["login_locked"] is True

    r = await c.post(f"/api/users/{uid}/unlock-login", headers=auth)
    assert r.status_code == 204
    r = await c.get(f"/api/users/{uid}", headers=auth)
    assert r.json()["login_locked"] is False

    r = await c.post("/api/auth/login", json={"username": "lock_user", "password": "TestPass12"})
    assert r.status_code == 200


async def test_admin_can_create_user_with_resource_policy(env, tmp_path, monkeypatch):
    monkeypatch.setenv("OCTOP_IN_CONTAINER", "0")
    c, _srv, auth = env
    jail = tmp_path / "jail"
    jail.mkdir()

    r = await c.post(
        "/api/users",
        headers=auth,
        json={
            "username": "policy_create",
            "password": "TestPass12",
            "role": "user",
            "workspace_root_dir": jail.as_posix(),
            "token_quota": 2000,
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["workspace_root_dir"] == jail.resolve().as_posix()
    assert body["token_quota"] == 2000

    listed = (await c.get("/api/users", headers=auth)).json()
    row = next(u for u in listed if u["username"] == "policy_create")
    assert row["workspace_root_dir"] == jail.resolve().as_posix()
    assert row["token_quota"] == 2000


async def test_create_user_rejects_workspace_root_in_container(env, tmp_path, monkeypatch):
    monkeypatch.setenv("OCTOP_IN_CONTAINER", "1")
    c, _srv, auth = env
    jail = tmp_path / "jail"
    jail.mkdir()

    r = await c.post(
        "/api/users",
        headers=auth,
        json={
            "username": "policy_container",
            "password": "TestPass12",
            "role": "user",
            "workspace_root_dir": jail.as_posix(),
        },
    )
    assert r.status_code == 400, r.text
    assert r.json()["error"]["code"] == "WORKSPACE_ROOT_CONTAINER_UNSUPPORTED"
    listed = (await c.get("/api/users", headers=auth)).json()
    assert "policy_container" not in [u["username"] for u in listed]


async def test_create_user_rejects_invalid_workspace_root(env, tmp_path, monkeypatch):
    monkeypatch.setenv("OCTOP_IN_CONTAINER", "0")
    c, _srv, auth = env
    missing = tmp_path / "no-such-dir"

    r = await c.post(
        "/api/users",
        headers=auth,
        json={
            "username": "bad_root",
            "password": "TestPass12",
            "role": "user",
            "workspace_root_dir": missing.as_posix(),
        },
    )
    assert r.status_code == 400, r.text
    listed = (await c.get("/api/users", headers=auth)).json()
    assert "bad_root" not in [u["username"] for u in listed]


async def test_admin_can_set_resource_policy(env, tmp_path, monkeypatch):
    monkeypatch.setenv("OCTOP_IN_CONTAINER", "0")
    from tests.support.auth import TEST_PASSWORD, create_user

    c, _srv, auth = env
    jail = tmp_path / "jail"
    nested = jail / "ok"
    outside = tmp_path / "outside"
    jail.mkdir()
    nested.mkdir()
    outside.mkdir()

    user_auth = await create_user(c, auth, username="policy_user", password=TEST_PASSWORD)
    listed = (await c.get("/api/users", headers=auth)).json()
    row = next(u for u in listed if u["username"] == "policy_user")
    uid = row["id"]
    assert row["workspace_root_dir"] is None
    assert row["token_quota"] is None

    r = await c.patch(
        f"/api/users/{uid}",
        headers=auth,
        json={"workspace_root_dir": jail.as_posix(), "token_quota": 1000},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["workspace_root_dir"] == jail.resolve().as_posix()
    assert body["token_quota"] == 1000

    ok = await c.post(
        "/api/agents",
        headers=user_auth,
        json={
            "name": "inside-root",
            "config": {
                "backend": {
                    "type": "local_shell",
                    "virtual_mode": True,
                    "root_dir": nested.as_posix(),
                }
            },
        },
    )
    assert ok.status_code == 201, ok.text

    denied = await c.post(
        "/api/agents",
        headers=user_auth,
        json={
            "name": "outside-root",
            "config": {
                "backend": {
                    "type": "local_shell",
                    "virtual_mode": True,
                    "root_dir": outside.as_posix(),
                }
            },
        },
    )
    assert denied.status_code == 400, denied.text
    assert denied.json()["error"]["code"] == "WORKSPACE_ROOT_RESTRICTED"

    r = await c.patch(
        f"/api/users/{uid}",
        headers=auth,
        json={"workspace_root_dir": None, "token_quota": None},
    )
    assert r.status_code == 200
    assert r.json()["workspace_root_dir"] is None
    assert r.json()["token_quota"] is None


async def test_batch_enable_disable_delete_and_token_quota(env):
    c, _srv, auth = env
    me = (await c.get("/api/auth/me", headers=auth)).json()

    created_ids: list[int] = []
    for name in ("batch_a", "batch_b", "batch_c"):
        r = await c.post(
            "/api/users",
            headers=auth,
            json={"username": name, "password": "TestPass12", "role": "user"},
        )
        assert r.status_code == 201, r.text
        created_ids.append(r.json()["id"])

    r = await c.post(
        "/api/users/batch",
        headers=auth,
        json={"user_ids": created_ids, "action": "disable"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["action"] == "disable"
    assert body["succeeded"] == 3
    assert body["failed"] == 0
    listed = {u["username"]: u for u in (await c.get("/api/users", headers=auth)).json()}
    assert listed["batch_a"]["disabled"] is True
    assert listed["batch_b"]["disabled"] is True

    r = await c.post(
        "/api/users/batch",
        headers=auth,
        json={"user_ids": created_ids[:2], "action": "enable"},
    )
    assert r.status_code == 200
    assert r.json()["succeeded"] == 2
    listed = {u["username"]: u for u in (await c.get("/api/users", headers=auth)).json()}
    assert listed["batch_a"]["disabled"] is False
    assert listed["batch_c"]["disabled"] is True

    r = await c.post(
        "/api/users/batch",
        headers=auth,
        json={
            "user_ids": created_ids,
            "action": "set_token_quota",
            "token_quota": 10_000_000,
        },
    )
    assert r.status_code == 200
    assert r.json()["succeeded"] == 3
    listed = {u["id"]: u for u in (await c.get("/api/users", headers=auth)).json()}
    for uid in created_ids:
        assert listed[uid]["token_quota"] == 10_000_000

    r = await c.post(
        "/api/users/batch",
        headers=auth,
        json={
            "user_ids": [created_ids[0]],
            "action": "set_token_quota",
            "token_quota": None,
        },
    )
    assert r.status_code == 200
    listed = {u["id"]: u for u in (await c.get("/api/users", headers=auth)).json()}
    assert listed[created_ids[0]]["token_quota"] is None

    # Self is skipped for delete; others succeed.
    r = await c.post(
        "/api/users/batch",
        headers=auth,
        json={"user_ids": [me["id"], *created_ids], "action": "delete"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["succeeded"] == 3
    assert body["failed"] == 1
    self_result = next(item for item in body["results"] if item["user_id"] == me["id"])
    assert self_result["ok"] is False
    assert self_result["code"] == "FORBIDDEN"
    listed = (await c.get("/api/users", headers=auth)).json()
    usernames = {u["username"] for u in listed}
    assert "batch_a" not in usernames
    assert me["username"] in usernames


async def test_batch_disable_skips_self(env):
    c, _srv, auth = env
    me = (await c.get("/api/auth/me", headers=auth)).json()
    r = await c.post(
        "/api/users",
        headers=auth,
        json={"username": "batch_other", "password": "TestPass12", "role": "user"},
    )
    other_id = r.json()["id"]

    r = await c.post(
        "/api/users/batch",
        headers=auth,
        json={"user_ids": [me["id"], other_id], "action": "disable"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["succeeded"] == 1
    assert body["failed"] == 1
    listed = {u["id"]: u for u in (await c.get("/api/users", headers=auth)).json()}
    assert listed[me["id"]]["disabled"] is False
    assert listed[other_id]["disabled"] is True


async def test_admin_can_set_max_agents_and_block_create(env):
    from tests.support.auth import TEST_PASSWORD, create_user

    c, _srv, auth = env
    user_auth = await create_user(c, auth, username="quota_user", password=TEST_PASSWORD)
    listed = (await c.get("/api/users", headers=auth)).json()
    uid = next(u["id"] for u in listed if u["username"] == "quota_user")

    r = await c.patch(
        f"/api/users/{uid}",
        headers=auth,
        json={"max_agents": 1},
    )
    assert r.status_code == 200, r.text
    assert r.json()["max_agents"] == 1

    first = await c.post(
        "/api/agents",
        headers=user_auth,
        json={"name": "expert-one"},
    )
    assert first.status_code == 201, first.text

    second = await c.post(
        "/api/agents",
        headers=user_auth,
        json={"name": "expert-two"},
    )
    assert second.status_code == 403, second.text
    assert second.json()["error"]["code"] == "AGENT_QUOTA_EXCEEDED"
    assert second.json()["error"]["details"] == {"used": 1, "quota": 1}

    r = await c.post(
        "/api/users/batch",
        headers=auth,
        json={"user_ids": [uid], "action": "set_max_agents", "max_agents": None},
    )
    assert r.status_code == 200
    assert r.json()["succeeded"] == 1
    listed = {u["id"]: u for u in (await c.get("/api/users", headers=auth)).json()}
    assert listed[uid]["max_agents"] is None

    third = await c.post(
        "/api/agents",
        headers=user_auth,
        json={"name": "expert-three"},
    )
    assert third.status_code == 201, third.text
