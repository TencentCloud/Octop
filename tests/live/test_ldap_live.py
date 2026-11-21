"""Live LDAP login against a real directory.

Drives the production HTTP surface (``POST /api/auth/login`` plus the admin
``/api/auth/ldap/config`` routes) against a real LDAP server, so a green run
proves the configured directory credentials actually reach the directory and
that group-derived roles are mapped onto an Octop account.

Point it at any directory — a local :program:`glauth` instance is the reference
setup (see ``docs/ldap.md`` §3.1)::

    OCTOP_LDAP_TEST_URL=ldap://127.0.0.1:3893 \
    OCTOP_LDAP_TEST_BIND_DN='uid=svc-octop,cn=users,dc=example,dc=org' \
    OCTOP_LDAP_TEST_BIND_PASSWORD=bindpw \
    OCTOP_LDAP_TEST_BASE_DN='dc=example,dc=org' \
    OCTOP_LDAP_TEST_USER=alice \
    OCTOP_LDAP_TEST_PASSWORD=alicepw \
    OCTOP_LDAP_TEST_ADMIN_GROUP=admin \
    uv run pytest tests/live/test_ldap_live.py -m live -v
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from tests.support.app import octop_client
from tests.support.auth import bootstrap_admin
from tests.support.secrets import optional_env, require_env

from octop.infra.server import OctopServer

pytestmark = pytest.mark.live


@pytest.fixture
async def client(tmp_octop_home: Path) -> AsyncIterator[tuple[httpx.AsyncClient, OctopServer]]:
    async with octop_client(tmp_octop_home) as (http, srv):
        await bootstrap_admin(http, tmp_octop_home)
        yield http, srv


def _config_body() -> dict[str, object]:
    """Directory settings for the live run.

    Enabling a plain ``ldap://`` URL now requires StartTLS, and a self-signed
    test server needs certificate verification off — both are env-driven so a
    real CA-signed directory can keep verification on.
    """
    start_tls = optional_env("OCTOP_LDAP_TEST_START_TLS", "1") not in ("0", "false", "no")
    verify_tls = optional_env("OCTOP_LDAP_TEST_VERIFY_TLS", "0") in ("1", "true", "yes")
    return {
        "enabled": True,
        "display_name": "Live Directory",
        "server_url": require_env("OCTOP_LDAP_TEST_URL"),
        "start_tls": start_tls,
        "verify_tls": verify_tls,
        "bind_dn": require_env("OCTOP_LDAP_TEST_BIND_DN"),
        "bind_password": require_env("OCTOP_LDAP_TEST_BIND_PASSWORD"),
        "user_base_dn": require_env("OCTOP_LDAP_TEST_BASE_DN"),
        "admin_groups": require_env("OCTOP_LDAP_TEST_ADMIN_GROUP"),
        # Blank keeps the DN as the identity key, matching this fixture.
        "subject_attribute": optional_env("OCTOP_LDAP_TEST_SUBJECT_ATTRIBUTE", "") or "",
        "auto_provision": True,
        "timeout_seconds": 10,
    }


async def test_live_directory_login_and_role_mapping(client) -> None:
    http, srv = client
    username = require_env("OCTOP_LDAP_TEST_USER")
    password = require_env("OCTOP_LDAP_TEST_PASSWORD")

    admin_token = (
        await http.post("/api/auth/login", json={"username": "admin", "password": "TestPass12"})
    ).json()["access_token"]
    auth = {"Authorization": f"Bearer {admin_token}"}

    configured = await http.put("/api/auth/ldap/config", headers=auth, json=_config_body())
    assert configured.status_code == 200, configured.text
    assert configured.json()["has_bind_password"] is True

    probe = await http.post("/api/auth/ldap/config/test", headers=auth)
    assert probe.status_code == 200, probe.text
    assert probe.json()["ok"] is True, probe.json()

    assert (await http.get("/api/auth/ldap/status")).json() == {
        "enabled": True,
        "display_name": "Live Directory",
    }

    login = await http.post("/api/auth/login", json={"username": username, "password": password})
    assert login.status_code == 200, login.text
    body = login.json()
    assert body["user"]["username"] == username
    assert body["user"]["role"] == optional_env("OCTOP_LDAP_TEST_EXPECTED_ROLE", "admin")

    # The JWT issued from a directory login is a normal Octop token.
    me = await http.get("/api/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200
    assert me.json()["username"] == username
    assert me.json()["has_password"] is False

    row = srv.services.user_repo.get_by_username(username)
    assert row is not None
    assert row.password_hash is None
    assert [item.kind for item in srv.user_manager.list_sso_identities(row.id)] == ["ldap"]

    # A wrong directory password is rejected as ordinary bad credentials.
    rejected = await http.post(
        "/api/auth/login", json={"username": username, "password": password + "-wrong"}
    )
    assert rejected.status_code == 401
    assert rejected.json()["error"]["code"] == "AUTH_FAILED"
