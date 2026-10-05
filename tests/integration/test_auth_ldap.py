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
    "start_tls": True,
    "bind_dn": SERVICE_DN,
    "bind_password": "bindpw",
    "user_base_dn": BASE_DN,
    "admin_groups": "admin",
    # Explicit: the shipped default is blank (DN-keyed), which these cases do not
    # exercise — they assert the directory-stable key behaviour.
    "subject_attribute": "entryUUID",
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
            extra={"entryUUID": ["uuid-alice"]},
        )
    )
    fake.add(
        fake_user(
            "carol",
            "carolpw",
            email="carol@example.org",
            display_name="Carol Clark",
            groups=(f"cn=users,ou=groups,{BASE_DN}",),
            extra={"entryUUID": ["uuid-carol"]},
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
    assert row.sso_subject == "uuid-alice"  # entryUUID, not the DN
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


async def test_local_password_is_never_sent_to_the_directory(
    env, directory: FakeLdapDirectory
) -> None:
    """A mistyped local password must not reach the directory at all.

    Sending it would hand a local secret to another system and count towards the
    directory's own lockout policy for that account.
    """
    client, _srv, auth = env
    await _configure(client, auth)
    directory.binds.clear()

    response = await _login(client, "admin", "wrong-local-password")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_FAILED"
    # Not one bind — not even the service bind — should have happened.
    assert directory.binds == []

    # The local password still works, and the account is unaffected.
    assert (await _login(client, "admin", TEST_PASSWORD)).status_code == 200
    assert directory.binds == []


async def test_local_password_always_stops_at_the_local_check(
    env, directory: FakeLdapDirectory
) -> None:
    """A local password is terminal — even for an account linked to the directory.

    Once the identifier holds its own password, a wrong one is answered locally:
    the submitted value is never forwarded, so it cannot leak to the directory nor
    spend an attempt against the directory's lockout policy. The account itself
    keeps working through that local password.
    """
    client, srv, auth = env
    await _configure(client, auth)
    # Provision carol from the directory, then give her a local password too.
    assert (await _login(client, "carol", "carolpw")).status_code == 200
    await srv.user_manager.reset_password("carol", "LocalPass123")
    directory.binds.clear()

    # Her local password works, and nothing is sent anywhere.
    assert (await _login(client, "carol", "LocalPass123")).status_code == 200
    assert directory.binds == []

    # Her *directory* password no longer falls through, and, crucially, the
    # rejected value never reaches the directory either.
    response = await _login(client, "carol", "carolpw")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_FAILED"
    assert directory.binds == [], "a local-password account must not be bound against"


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

    # A disabled draft may be incomplete…
    draft = await _configure(client, auth, enabled=False, server_url="", user_base_dn="")
    assert draft.status_code == 200
    assert draft.json()["enabled"] is False
    # …but flipping that same incomplete draft to enabled must be refused. Send
    # only ``enabled`` so the stored (incomplete) values are what gets validated.
    enabling = await client.put("/api/auth/ldap/config", headers=auth, json={"enabled": True})
    assert enabling.status_code == 400
    assert enabling.json()["error"]["code"] == "LDAP_BAD_REQUEST"


async def test_config_test_reports_reachability(env, directory: FakeLdapDirectory) -> None:
    client, _srv, auth = env
    await _configure(client, auth)

    reachable = await client.post("/api/auth/ldap/config/test", headers=auth)
    assert reachable.status_code == 200
    assert reachable.json()["ok"] is True
    # ``detail`` embeds the probed address, so an unrelated success message
    # cannot pass this check.
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


async def test_new_directory_user_gets_the_preset_role_template(
    env, directory: FakeLdapDirectory
) -> None:
    """Provisioning must go through the role template, not a bare role string.

    Without the template a directory user can sign in but holds none of the
    baseline permissions (channels, connectors, knowledge) nor the role's
    policies.
    """
    client, srv, auth = env
    await _configure(client, auth)

    response = await _login(client, "carol", "carolpw")
    assert response.status_code == 200
    assert response.json()["user"]["role"] == "user"

    row = srv.services.user_repo.get_by_username("carol")
    assert row is not None
    assert row.role == "user"
    assert row.role_name is not None, "role_name should be copied from the template"
    assert row.permissions, "baseline permissions should come from the preset role"

    # Assert against the shipped preset values, not against a re-read of the same
    # helper the production path uses — otherwise a bug inside that helper is
    # invisible to this test.
    assert sorted(row.permissions) == [
        "channels",
        "connectors",
        "knowledge_bases",
        "skill_packages",
    ]
    # The preset user template defines no policies; nothing extra may be applied.
    assert srv.services.user_policy_repo.list_for_user(row.id) == []


async def test_admin_group_selects_the_admin_role_template(
    env, directory: FakeLdapDirectory
) -> None:
    client, srv, auth = env
    await _configure(client, auth)

    assert (await _login(client, "alice", "alicepw")).status_code == 200
    row = srv.services.user_repo.get_by_username("alice")
    assert row is not None
    assert row.role == "admin"
    assert row.role_name is not None


async def test_custom_role_ids_do_not_break_a_later_login(
    env, directory: FakeLdapDirectory
) -> None:
    """``users.role`` may hold a custom template id; the cache must not coerce it."""
    client, srv, auth = env
    await _configure(client, auth)
    assert (await _login(client, "carol", "carolpw")).status_code == 200

    created = await client.post(
        "/api/users/roles",
        headers=auth,
        json={"user_role_name": "Directory Ops", "permissions": [], "policies": []},
    )
    assert created.status_code == 201, created.text
    role_id = created.json()["user_role_id"]

    carol_id = await resolve_user_id(client, auth, username="carol")
    patched = await client.patch(f"/api/users/{carol_id}", headers=auth, json={"role": role_id})
    assert patched.status_code == 200

    # Drop the process cache so the next login re-reads the row.
    srv.user_manager._users.pop("carol", None)
    again = await _login(client, "carol", "carolpw")
    assert again.status_code == 200, again.text
    assert again.json()["user"]["role"] == role_id


async def test_allowed_groups_restrict_who_may_sign_in(env, directory: FakeLdapDirectory) -> None:
    client, srv, auth = env
    await _configure(client, auth, allowed_groups="engineering")

    response = await _login(client, "carol", "carolpw")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "LDAP_GROUP_NOT_ALLOWED"
    # A refused account is not provisioned either.
    assert srv.services.user_repo.get_by_username("carol") is None

    # A member of an allowed group still signs in.
    assert (await _configure(client, auth, allowed_groups="admin")).status_code == 200
    assert (await _login(client, "alice", "alicepw")).status_code == 200


async def test_outage_during_the_user_bind_is_unavailable_not_auth_failed(
    env, directory: FakeLdapDirectory
) -> None:
    """The search worked; the user bind could not connect."""
    client, _srv, auth = env
    await _configure(client, auth)

    directory.outage_after_opens(1)
    response = await _login(client, "alice", "alicepw")
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "LDAP_UNAVAILABLE"


async def test_enabling_plain_ldap_without_starttls_is_refused(
    env, directory: FakeLdapDirectory
) -> None:
    """Enabling ldap:// with no StartTLS would send passwords in clear text."""
    client, _srv, auth = env
    del directory

    response = await _configure(client, auth, server_url="ldap://d.example.org", start_tls=False)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "LDAP_BAD_REQUEST"

    # The same draft may be saved while the provider stays disabled.
    draft = await _configure(
        client, auth, enabled=False, server_url="ldap://d.example.org", start_tls=False
    )
    assert draft.status_code == 200
    # …and with StartTLS on, enabling is allowed again.
    assert (await _configure(client, auth, start_tls=True)).status_code == 200


async def test_account_survives_a_directory_rename(env, directory: FakeLdapDirectory) -> None:
    """The identity key is directory-stable, so moving an entry keeps the account."""
    client, srv, auth = env
    await _configure(client, auth)
    first = await _login(client, "carol", "carolpw")
    assert first.status_code == 200
    first_id = first.json()["user"]["id"]

    carol = next(item for item in directory.users if item.username == "carol")
    carol.dn = f"uid=carol,cn=staff,ou=people,{BASE_DN}"

    again = await _login(client, "carol", "carolpw")
    assert again.status_code == 200
    assert again.json()["user"]["id"] == first_id, "a rename must not mint a second account"
    assert srv.services.user_repo.count() == 2


async def test_config_test_reports_warnings(env, directory: FakeLdapDirectory) -> None:
    client, _srv, auth = env
    await _configure(client, auth, verify_tls=False, admin_groups="")
    del directory

    result = await client.post("/api/auth/ldap/config/test", headers=auth)
    assert result.status_code == 200
    warnings = result.json()["warnings"]
    assert "tls_verification_disabled" in warnings
    assert "no_admin_groups" in warnings


async def test_config_audit_records_the_acting_admin(env, directory: FakeLdapDirectory) -> None:
    """The audit trail must name the admin, not a literal placeholder."""
    client, srv, auth = env
    await _configure(client, auth)
    del directory

    entries = srv.services.audit_repo.query(action="sso.ldap_config", limit=50)
    assert entries, "no ldap config audit entry written"
    assert {row.actor for row in entries} == {"admin"}


async def test_blank_identity_key_keys_accounts_on_the_dn(
    env, directory: FakeLdapDirectory
) -> None:
    """The shipped default: no identity attribute, so the entry DN is the key.

    Documented consequence — a rename in the directory is indistinguishable from a
    new user, and provisions a second account. The admin opts out by setting
    ``subject_attribute`` (the probe reports what the directory offers).
    """
    client, srv, auth = env
    await _configure(client, auth, subject_attribute="", display_name_attribute="givenName")

    first = await _login(client, "carol", "carolpw")
    assert first.status_code == 200
    row = srv.services.user_repo.get_by_username("carol")
    assert row is not None
    assert row.sso_subject == f"uid=carol,cn=users,{BASE_DN}"

    carol = next(item for item in directory.users if item.username == "carol")
    carol.dn = f"uid=carol,cn=staff,ou=people,{BASE_DN}"

    again = await _login(client, "carol", "carolpw")
    assert again.status_code == 200
    assert again.json()["user"]["id"] != first.json()["user"]["id"], (
        "a DN-keyed account is expected to look like a new user after a rename"
    )
    assert srv.services.user_repo.count() == 3  # admin + two carol accounts
