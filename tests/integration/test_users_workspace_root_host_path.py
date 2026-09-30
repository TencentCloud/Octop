"""A rejected ``workspace_root_dir`` must answer 400 on every write path.

``normalize_workspace_root_dir()`` let ``assert_safe_host_path()``'s bare
``ValueError`` escape, so the global handler turned it into 500
``INTERNAL_ERROR`` and left a traceback in the log — while a neighbouring
input on the very same field (a path that is not a directory) already
answered 400.
"""

NUL = "a\x00b"


async def test_create_user_rejects_unsafe_workspace_root(env, monkeypatch) -> None:
    monkeypatch.setenv("OCTOP_IN_CONTAINER", "0")
    c, _srv, auth = env
    r = await c.post(
        "/api/users",
        headers=auth,
        json={
            "username": "unsafe_root",
            "password": "TestPass12",
            "role": "user",
            "workspace_root_dir": NUL,
        },
    )
    assert r.status_code == 400, r.text
    assert r.json()["error"]["code"] == "WORKSPACE_ROOT_RESTRICTED"
    listed = (await c.get("/api/users", headers=auth)).json()
    assert "unsafe_root" not in [u["username"] for u in listed]


async def test_patch_user_rejects_unsafe_workspace_root(env, monkeypatch) -> None:
    monkeypatch.setenv("OCTOP_IN_CONTAINER", "0")
    c, _srv, auth = env
    rows = (await c.get("/api/users", headers=auth)).json()
    admin = next(u for u in rows if u["username"] == "admin")

    r = await c.patch(f"/api/users/{admin['id']}", headers=auth, json={"workspace_root_dir": NUL})
    assert r.status_code == 400, r.text
    assert r.json()["error"]["code"] == "WORKSPACE_ROOT_RESTRICTED"
    after = (await c.get(f"/api/users/{admin['id']}", headers=auth)).json()
    assert after["workspace_root_dir"] is None


async def test_role_template_rejects_unsafe_workspace_root(env, monkeypatch) -> None:
    monkeypatch.setenv("OCTOP_IN_CONTAINER", "0")
    c, _srv, auth = env
    r = await c.post(
        "/api/users/roles",
        headers=auth,
        json={
            "user_role_name": "unsafe-root-role",
            "policies": [{"name": "workspace_root_dir", "value": NUL}],
        },
    )
    assert r.status_code == 400, r.text
    assert r.json()["error"]["code"] == "WORKSPACE_ROOT_RESTRICTED"
    roles = (await c.get("/api/users/roles", headers=auth)).json()
    assert "unsafe-root-role" not in [row["user_role_name"] for row in roles]
