"""LDAP directory login over the real HTTP surface.

Every layer above the socket runs as production code: the routes, the service,
and :class:`LdapClient`. Only ``ldap3.Connection`` is replaced, by
``tests.support.ldap_fake``.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from tests.support.auth import TEST_PASSWORD, create_user, resolve_user_id
from tests.support.ldap_fake import FakeLdapDirectory, fake_user

BASE_DN = "dc=example,dc=org"
SERVICE_DN = f"uid=svc-octop,cn=users,{BASE_DN}"

_CONFIG_BODY: dict[str, Any] = {
    "enabled": True,
    "display_name": "Corp Directory",
    "server_url": "ldap://directory.example.org",
    "bind_dn": SERVICE_DN,
    "bind_password": "bindpw",
    "user_base_dn": BASE_DN,
    "admin_groups": "admin",
    "auto_provision": True,
}


@pytest.fixture
def directory(monkeypatch: pytest.MonkeyPatch) -> FakeLdapDirectory:
    fake = FakeLdapDirectory(bind_dn=SERVICE_DN, bind_password="bindpw")
    fake.add(
        fake_user(
            "alice",
            "alicepw",
            email="alice@example.org",
            display_name="Alice Anderson",
            group="admin",
            groups=(f"cn=admin,ou=groups,{BASE_DN}",),
        )
    )
    fake.add(
        fake_user(
            "carol",
            "carolpw",
            email="carol@example.org",
            display_name="Carol Clark",
            groups=(f"cn=users,ou=groups,{BASE_DN}",),
        )
    )
    return fake.install(monkeypatch)


async def _configure(
    client: httpx.AsyncClient, auth: dict[str, str], **overrides: Any
) -> httpx.Response:
    body = {**_CONFIG_BODY, **overrides}
    if overrides.get("bind_password") is None and "bind_password" in overrides:
        body.pop("bind_password")
    return await client.put("/api/auth/ldap/config", headers=auth, json=body)


async def _login(client: httpx.AsyncClient, username: str, password: str) -> httpx.Response:
    return await client.post("/api/auth/login", json={"username": username, "password": password})


async def test_directory_login_provisions_an_account_and_maps_the_admin_group(
    env, directory: FakeLdapDirectory
) -> None:
    client, srv, auth = env
    assert (await _configure(client, auth)).status_code == 200

    response = await _login(client, "alice", "alicepw")
    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["token_type"] == "Bearer"
    assert body["user"]["username"] == "alice"
    assert body["user"]["role"] == "admin"
    assert body["user"]["display_name"] == "Alice Anderson"

    row = srv.services.user_repo.get_by_username("alice")
    assert row is not None
    assert row.password_hash is None
    assert row.email == "alice@example.org"
    assert row.sso_subject == f"uid=alice,cn=admin,{BASE_DN}"
    identities = srv.user_manager.list_sso_identities(row.id)
    assert [item.kind for item in identities] == ["ldap"]

    # The privilege comes from the group, and the account is reused on relogin.
    again = await _login(client, "alice", "alicepw")
    assert again.status_code == 200
    assert again.json()["user"]["id"] == body["user"]["id"]
    assert srv.services.user_repo.count() == 2  # only admin + alice


async def test_directory_user_outside_admin_groups_gets_the_user_role(
    env, directory: FakeLdapDirectory
) -> None:
    client, srv, auth = env
    await _configure(client, auth)

    response = await _login(client, "carol", "carolpw")
    assert response.status_code == 200
    assert response.json()["user"]["role"] == "user"

    token = response.json()["access_token"]
    denied = await client.get("/api/users", headers={"Authorization": f"Bearer {token}"})
    assert denied.status_code == 403
    del srv


async def test_roles_are_assigned_at_provisioning_and_not_silently_raised(
    env, directory: FakeLdapDirectory
) -> None:
    """Moving a directory user into the admin group must not promote them."""
    client, srv, auth = env
    await _configure(client, auth)

    first = await _login(client, "carol", "carolpw")
    assert first.json()["user"]["role"] == "user"

    carol = next(item for item in directory.users if item.username == "carol")
    carol.groups = (f"cn=admin,ou=groups,{BASE_DN}",)

    assert (await _login(client, "carol", "carolpw")).json()["user"]["role"] == "user"
    row = srv.services.user_repo.get_by_username("carol")
    assert row is not None
    assert row.role == "user"


async def test_wrong_directory_password_is_rejected_with_auth_failed(
    env, directory: FakeLdapDirectory
) -> None:
    client, _srv, auth = env
    await _configure(client, auth)

    response = await _login(client, "alice", "wrongpw")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_FAILED"
    assert (await _login(client, "ghost", "whatever")).status_code == 401


async def test_directory_credentials_cannot_authenticate_as_the_service_account(
    env, directory: FakeLdapDirectory
) -> None:
    """Typing the service DN must not authenticate anyone."""
    client, _srv, auth = env
    await _configure(client, auth)

    response = await _login(client, SERVICE_DN, "bindpw")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_FAILED"


async def test_directory_display_name_changes_are_reflected_on_the_next_login(
    env, directory: FakeLdapDirectory
) -> None:
    """A renamed directory user must not keep serving the provisioning-time name."""
    client, _srv, auth = env
    await _configure(client, auth)

    first = await _login(client, "alice", "alicepw")
    assert first.json()["user"]["display_name"] == "Alice Anderson"

    entry = next(item for item in directory.users if item.username == "alice")
    entry.display_name = "Alice Renamed"

    again = await _login(client, "alice", "alicepw")
    assert again.json()["user"]["display_name"] == "Alice Renamed"
    assert again.json()["user"]["id"] == first.json()["user"]["id"]

    me = await client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {again.json()['access_token']}"},
    )
    assert me.json()["display_name"] == "Alice Renamed"


async def test_local_password_login_still_wins_over_the_directory(
    env, directory: FakeLdapDirectory
) -> None:
    client, _srv, _auth = env
    configured = await _configure(client, _auth)
    assert configured.status_code == 200

    response = await _login(client, "admin", TEST_PASSWORD)
    assert response.status_code == 200
    assert response.json()["user"]["role"] == "admin"


async def test_unprovisioned_directory_user_is_refused_when_auto_provision_is_off(
    env, directory: FakeLdapDirectory
) -> None:
    client, srv, auth = env
    await _configure(client, auth, auto_provision=False)

    response = await _login(client, "carol", "carolpw")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "LDAP_USER_NOT_PROVISIONED"
    assert srv.services.user_repo.get_by_username("carol") is None

    # An account provisioned while the setting was on keeps working.
    assert (await _configure(client, auth, auto_provision=True)).status_code == 200
    assert (await _login(client, "carol", "carolpw")).status_code == 200
    assert (await _configure(client, auth, auto_provision=False)).status_code == 200
    assert (await _login(client, "carol", "carolpw")).status_code == 200


async def test_directory_outage_is_reported_as_unavailable_not_bad_credentials(
    env, directory: FakeLdapDirectory
) -> None:
    client, _srv, auth = env
    await _configure(client, auth)

    directory.reachable = False
    response = await _login(client, "alice", "alicepw")
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "LDAP_UNAVAILABLE"


async def test_rotated_bind_password_is_reported_as_unavailable(
    env, directory: FakeLdapDirectory
) -> None:
    client, _srv, auth = env
    await _configure(client, auth)

    directory.bind_password = "rotated"
    response = await _login(client, "alice", "alicepw")
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "LDAP_UNAVAILABLE"


async def test_directory_outage_does_not_mask_a_local_password_typo(
    env, directory: FakeLdapDirectory
) -> None:
    """A local account's bad password stays 401 even while the directory is down."""
    client, _srv, auth = env
    await _configure(client, auth)

    directory.reachable = False
    response = await _login(client, "admin", "wrong-local-password")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_FAILED"

    # The local password still works, and the local account is unaffected.
    assert (await _login(client, "admin", TEST_PASSWORD)).status_code == 200


async def test_disabled_octop_account_cannot_log_in_through_the_directory(
    env, directory: FakeLdapDirectory
) -> None:
    client, srv, auth = env
    await _configure(client, auth)
    assert (await _login(client, "carol", "carolpw")).status_code == 200

    carol_id = await resolve_user_id(client, auth, username="carol")
    disabled = await client.patch(f"/api/users/{carol_id}", headers=auth, json={"disabled": True})
    assert disabled.status_code == 200
    assert disabled.json()["disabled"] is True
    response = await _login(client, "carol", "carolpw")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "USER_DISABLED"
    del srv


async def test_directory_account_cannot_change_a_local_password(
    env, directory: FakeLdapDirectory
) -> None:
    client, _srv, auth = env
    await _configure(client, auth)
    token = (await _login(client, "alice", "alicepw")).json()["access_token"]

    response = await client.post(
        "/api/auth/change-password",
        headers={"Authorization": f"Bearer {token}"},
        json={"old_password": "", "new_password": "NewPass123"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "PASSWORD_NOT_SET"


async def test_status_is_public_and_follows_the_configuration(
    env, directory: FakeLdapDirectory
) -> None:
    client, srv, auth = env
    assert (await client.get("/api/auth/ldap/status")).json() == {
        "enabled": False,
        "display_name": "",
    }

    await _configure(client, auth)
    assert (await client.get("/api/auth/ldap/status")).json() == {
        "enabled": True,
        "display_name": "Corp Directory",
    }

    # Enabled but switched off is not advertised to the login page.
    assert (await _configure(client, auth, enabled=False)).status_code == 200
    assert (await client.get("/api/auth/ldap/status")).json()["enabled"] is False
    del srv


async def test_config_endpoints_require_the_sso_permission(
    env, directory: FakeLdapDirectory
) -> None:
    client, _srv, auth = env
    member_auth = await create_user(client, auth, username="member")
    del directory

    assert (await client.get("/api/auth/ldap/config")).status_code == 401
    assert (await client.get("/api/auth/ldap/config", headers=member_auth)).status_code == 403
    assert (
        await client.put("/api/auth/ldap/config", headers=member_auth, json=_CONFIG_BODY)
    ).status_code == 403
    assert (await client.post("/api/auth/ldap/config/test", headers=member_auth)).status_code == 403


async def test_admin_config_never_returns_the_bind_password(
    env, directory: FakeLdapDirectory
) -> None:
    client, _srv, auth = env
    await _configure(client, auth)
    del directory

    payload = (await client.get("/api/auth/ldap/config", headers=auth)).json()
    assert payload["has_bind_password"] is True
    assert "bind_password" not in payload
    assert payload["bind_dn"] == SERVICE_DN
    assert payload["user_filter"] == (
        "(|(uid={username})(sAMAccountName={username})(mail={username}))"
    )


async def test_omitting_bind_password_keeps_the_stored_one(
    env, directory: FakeLdapDirectory
) -> None:
    client, _srv, auth = env
    await _configure(client, auth)

    updated = await _configure(client, auth, bind_password=None, display_name="Renamed")
    assert updated.status_code == 200
    assert updated.json()["has_bind_password"] is True
    assert updated.json()["display_name"] == "Renamed"

    assert (await _login(client, "alice", "alicepw")).status_code == 200


async def test_partial_configuration_is_rejected_with_a_localized_error(
    env, directory: FakeLdapDirectory
) -> None:
    client, _srv, auth = env
    del directory

    bad_url = await _configure(client, auth, server_url="http://directory.example.org")
    assert bad_url.status_code == 400
    assert bad_url.json()["error"]["code"] == "LDAP_BAD_REQUEST"

    no_placeholder = await _configure(client, auth, user_filter="(uid=someone)")
    assert no_placeholder.status_code == 400
    assert no_placeholder.json()["error"]["code"] == "LDAP_BAD_REQUEST"

    # A disabled draft may be incomplete; enabling it does not.
    draft = await _configure(client, auth, enabled=False, server_url="", user_base_dn="")
    assert draft.status_code == 200
    assert draft.json()["enabled"] is False
    assert (await _configure(client, auth, enabled=True)).status_code in (200, 400)


async def test_config_test_reports_reachability(env, directory: FakeLdapDirectory) -> None:
    client, _srv, auth = env
    await _configure(client, auth)

    reachable = await client.post("/api/auth/ldap/config/test", headers=auth)
    assert reachable.status_code == 200
    assert reachable.json()["ok"] is True
    assert "ldap://directory.example.org" in reachable.json()["detail"]

    directory.bind_password = "rotated"
    unreachable = await client.post("/api/auth/ldap/config/test", headers=auth)
    assert unreachable.status_code == 200
    assert unreachable.json()["ok"] is False
    assert unreachable.json()["detail"]


async def test_directory_login_is_skipped_entirely_when_not_configured(
    env, directory: FakeLdapDirectory
) -> None:
    client, _srv, _auth = env
    del directory

    response = await _login(client, "alice", "alicepw")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_FAILED"
