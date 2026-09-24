"""LdapClient behaviour over a faked ``ldap3.Connection`` boundary."""

from __future__ import annotations

import pytest
from tests.support.ldap_fake import FakeLdapDirectory, fake_user

from octop.infra.auth.ldap.client import LdapClient, LdapUnavailable
from octop.infra.auth.ldap.config import LdapConfig

BASE_DN = "dc=example,dc=org"
SERVICE_DN = f"uid=svc-octop,cn=users,{BASE_DN}"


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
    fake.add(fake_user("bob", "bobpw", email="bob@example.org", display_name="Bob Brown"))
    return fake.install(monkeypatch)


def _config(**overrides: object) -> LdapConfig:
    base: dict[str, object] = {
        "enabled": True,
        "server_url": "ldap://directory.example.org",
        "bind_dn": SERVICE_DN,
        "user_base_dn": BASE_DN,
        "admin_groups": ("admin",),
    }
    base.update(overrides)
    return LdapConfig(**base)  # type: ignore[arg-type]


def _client(directory: FakeLdapDirectory, **overrides: object) -> LdapClient:
    del directory
    return LdapClient(_config(**overrides), "bindpw")


def test_successful_login_returns_directory_identity(directory: FakeLdapDirectory):
    identity = _client(directory).authenticate("alice", "alicepw")
    assert identity is not None
    assert identity.dn == f"uid=alice,cn=admin,{BASE_DN}"
    assert identity.username == "alice"
    assert identity.email == "alice@example.org"
    assert identity.display_name == "Alice Anderson"
    assert identity.is_member_of(("admin",)) is True
    assert identity.is_member_of(("engineering",)) is False
    # Service bind + the user's own bind.
    assert directory.binds == [(SERVICE_DN, "bindpw"), (identity.dn, "alicepw")]


def test_wrong_password_and_unknown_user_are_rejected(directory: FakeLdapDirectory):
    client = _client(directory)
    assert client.authenticate("alice", "wrongpw") is None
    assert client.authenticate("nobody", "alicepw") is None
    assert client.authenticate("", "alicepw") is None
    assert client.authenticate("alice", "") is None
    # Every connection is released, including the rejected ones.
    assert directory.unbound == directory.opened


def test_credentials_with_untrusted_dn_are_never_bound(directory: FakeLdapDirectory):
    """A user cannot authenticate as the service account by typing its DN."""
    assert _client(directory).authenticate(SERVICE_DN, "bindpw") is None


def test_filter_placeholder_is_escaped_against_injection(directory: FakeLdapDirectory):
    client = _client(directory)
    assert client.authenticate("*", "alicepw") is None
    assert client.authenticate("alice", "alicepw") is not None
    lookup = directory.searches[-1][1]
    assert "{username}" not in lookup
    assert "alice" in lookup


def test_mail_login_matches_the_default_filter(directory: FakeLdapDirectory):
    identity = _client(directory).authenticate("alice@example.org", "alicepw")
    assert identity is not None
    assert identity.username == "alice"


def test_user_lookup_prefers_the_exact_username_match(directory: FakeLdapDirectory):
    directory.add(
        fake_user("alice2", "otherpw", email="alice2@example.org", display_name="Alice Two")
    )
    identity = _client(directory, user_filter="(uid=alice*)").authenticate("alice", "alicepw")
    assert identity is not None
    assert identity.username == "alice"


def test_unreachable_server_raises_instead_of_rejecting_credentials(
    directory: FakeLdapDirectory,
):
    directory.reachable = False
    with pytest.raises(LdapUnavailable):
        _client(directory).authenticate("alice", "alicepw")
    probe = _client(directory).test()
    assert probe.ok is False
    assert probe.code == "unreachable"


def test_rejected_service_bind_is_reported_as_unavailable(directory: FakeLdapDirectory):
    client = LdapClient(_config(), "wrong-bind-password")
    probe = client.test()
    assert probe.ok is False
    assert probe.code == "bind_failed"
    with pytest.raises(LdapUnavailable):
        client.authenticate("alice", "alicepw")


def test_probe_reports_search_failures(directory: FakeLdapDirectory):
    directory.search_allowed = False
    probe = _client(directory).test()
    assert probe.ok is False
    assert probe.code == "search_failed"


def test_anonymous_bind_when_no_service_account_is_configured(
    directory: FakeLdapDirectory, monkeypatch: pytest.MonkeyPatch
):
    anonymous = FakeLdapDirectory(bind_dn="", bind_password="")
    anonymous.add(fake_user("carol", "carolpw", display_name="Carol"))
    monkeypatch.setattr("octop.infra.auth.ldap.client.Connection", anonymous._connection)
    identity = LdapClient(_config(bind_dn=""), "").authenticate("carol", "carolpw")
    assert identity is not None
    assert identity.username == "carol"
    assert anonymous.binds[0] == ("", "")


def test_probe_succeeds_against_a_reachable_directory(directory: FakeLdapDirectory):
    probe = _client(directory).test()
    assert probe.ok is True
    assert probe.code == "ok"
    assert probe.detail == "ldap://directory.example.org"


def test_lookup_raises_when_the_service_account_password_no_longer_works(
    directory: FakeLdapDirectory,
):
    """Rotating the bind password must surface as an outage, not a bad password."""
    directory.bind_password = "rotated"
    with pytest.raises(LdapUnavailable):
        _client(directory).authenticate("alice", "alicepw")


def test_start_tls_failure_is_surfaced(directory: FakeLdapDirectory):
    directory.start_tls_supported = False
    probe = _client(directory, server_url="ldap://host", start_tls=True).test()
    assert probe.ok is False
    assert probe.code == "unreachable"


def test_missing_directory_attributes_do_not_break_the_identity(
    directory: FakeLdapDirectory,
):
    directory.add(fake_user("dave", "davepw"))
    identity = _client(directory).authenticate("dave", "davepw")
    assert identity is not None
    assert identity.email is None
    assert identity.display_name is None
    assert identity.groups == ()


def test_entry_attributes_are_read_as_strings(monkeypatch: pytest.MonkeyPatch):
    """Attribute values of any ldap3 type are coerced to ``str``."""
    directory = FakeLdapDirectory(bind_dn=SERVICE_DN, bind_password="bindpw")
    directory.add(fake_user("erin", "erinpw", display_name="Erin"))
    directory.install(monkeypatch)
    identity = LdapClient(_config(), "bindpw").authenticate("erin", "erinpw")
    assert identity is not None
    assert isinstance(identity.username, str)
    assert isinstance(identity.dn, str)
