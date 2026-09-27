"""A rejected ``PATCH /api/users/{id}`` must not leave a partial write behind.

``create_user`` validates the resource-policy fields before it writes anything,
and ``tests/integration/test_users_api.py`` pins that ("400 and no such user").
``patch_user`` writes role / role_name / permissions / template policies first and
validates the body's policy fields last, so a request that ends in 400 has
already re-roled the target account.
"""

from __future__ import annotations

import shutil

from tests.support.auth import TEST_PASSWORD, create_user


async def _role_id_with_policies(c, auth, *, permissions, policies):
    created = await c.post(
        "/api/users/roles",
        headers=auth,
        json={
            "user_role_name": "report-reader",
            "permissions": permissions,
            "policies": policies,
        },
    )
    assert created.status_code == 201, created.text
    return created.json()["user_role_id"]


async def _row_by_username(c, auth, username):
    listed = await c.get("/api/users", headers=auth)
    assert listed.status_code == 200, listed.text
    return next(u for u in listed.json() if u["username"] == username)


async def test_rejected_patch_leaves_role_and_permissions_untouched(env, tmp_path, monkeypatch):
    monkeypatch.setenv("OCTOP_IN_CONTAINER", "0")
    c, _srv, auth = env
    role_id = await _role_id_with_policies(c, auth, permissions=["browser"], policies=[])
    await create_user(c, auth, username="rerole_target", password=TEST_PASSWORD)
    before = await _row_by_username(c, auth, "rerole_target")
    assert before["role"] == "user"
    assert "browser" not in before["permissions"]

    missing = tmp_path / "no-such-dir"
    r = await c.patch(
        f"/api/users/{before['id']}",
        headers=auth,
        json={"role": role_id, "workspace_root_dir": missing.as_posix()},
    )
    assert r.status_code == 400, r.text

    after = await _row_by_username(c, auth, "rerole_target")
    assert after["role"] == before["role"], after
    assert after["permissions"] == before["permissions"], after
    assert after["role_name"] == before["role_name"], after
    assert after["workspace_root_dir"] is None


async def test_rejected_patch_leaves_earlier_fields_untouched(env, tmp_path, monkeypatch):
    monkeypatch.setenv("OCTOP_IN_CONTAINER", "0")
    c, _srv, auth = env
    await create_user(c, auth, username="rename_target", password=TEST_PASSWORD)
    before = await _row_by_username(c, auth, "rename_target")

    missing = tmp_path / "also-missing"
    r = await c.patch(
        f"/api/users/{before['id']}",
        headers=auth,
        json={"display_name": "renamed", "workspace_root_dir": missing.as_posix()},
    )
    assert r.status_code == 400, r.text

    after = await _row_by_username(c, auth, "rename_target")
    assert after["display_name"] == before["display_name"], after
    assert after["workspace_root_dir"] is None


async def test_rejected_patch_from_stale_template_root_leaves_role_untouched(
    env, tmp_path, monkeypatch
):
    monkeypatch.setenv("OCTOP_IN_CONTAINER", "0")
    c, _srv, auth = env
    jail = tmp_path / "template-root"
    jail.mkdir()
    role_id = await _role_id_with_policies(
        c,
        auth,
        permissions=["browser"],
        policies=[{"name": "workspace_root_dir", "value": jail.as_posix()}],
    )
    shutil.rmtree(jail)

    await create_user(c, auth, username="stale_root_target", password=TEST_PASSWORD)
    before = await _row_by_username(c, auth, "stale_root_target")

    r = await c.patch(f"/api/users/{before['id']}", headers=auth, json={"role": role_id})
    assert r.status_code == 400, r.text

    after = await _row_by_username(c, auth, "stale_root_target")
    assert after["role"] == before["role"], after
    assert after["permissions"] == before["permissions"], after


async def test_valid_patch_applies_role_and_policy_together(env, tmp_path, monkeypatch):
    monkeypatch.setenv("OCTOP_IN_CONTAINER", "0")
    c, _srv, auth = env
    role_id = await _role_id_with_policies(c, auth, permissions=["browser"], policies=[])
    await create_user(c, auth, username="valid_target", password=TEST_PASSWORD)
    before = await _row_by_username(c, auth, "valid_target")
    jail = tmp_path / "jail"
    jail.mkdir()

    r = await c.patch(
        f"/api/users/{before['id']}",
        headers=auth,
        json={"role": role_id, "workspace_root_dir": jail.as_posix()},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["role"] == role_id
    assert body["permissions"] == ["browser"]
    assert body["workspace_root_dir"] == jail.resolve().as_posix()
