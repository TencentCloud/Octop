"""LdapClient behaviour over a faked ``ldap3.Connection`` boundary."""

from __future__ import annotations

import pytest
from tests.support.ldap_fake import FakeLdapDirectory, FakeLdapGroup, fake_user

from octop.infra.auth.ldap.client import (
    _SEARCH_SIZE_LIMIT,
    LdapClient,
    LdapUnavailable,
)
from octop.infra.auth.ldap.config import LdapConfig

BASE_DN = "dc=example,dc=org"
SERVICE_DN = f"uid=svc-octop,cn=users,{BASE_DN}"
ADMIN_GROUP_DN = f"cn=admin,ou=groups,{BASE_DN}"


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
            groups=(ADMIN_GROUP_DN,),
            extra={"entryUUID": ["uuid-alice"]},
        )
    )
    fake.add(
        fake_user(
            "bob",
            "bobpw",
            email="bob@example.org",
            display_name="Bob Brown",
            extra={"entryUUID": ["uuid-bob"]},
        )
    )
    return fake.install(monkeypatch)


def _config(**overrides: object) -> LdapConfig:
    base: dict[str, object] = {
        "enabled": True,
        "server_url": "ldaps://directory.example.org",
        "bind_dn": SERVICE_DN,
        "user_base_dn": BASE_DN,
        "admin_groups": ("admin",),
        # Blank is the shipped default and would key accounts on the DN; these
        # cases exercise the directory-stable key explicitly.
        "subject_attribute": "entryUUID",
    }
    base.update(overrides)
    return LdapConfig(**base)  # type: ignore[arg-type]


def _client(**overrides: object) -> LdapClient:
    return LdapClient(_config(**overrides), "bindpw")


def test_successful_login_returns_directory_identity(directory: FakeLdapDirectory):
    identity = _client().authenticate("alice", "alicepw")
    assert identity is not None
    assert identity.dn == f"uid=alice,cn=admin,{BASE_DN}"
    assert identity.username == "alice"
    assert identity.email == "alice@example.org"
    assert identity.display_name == "Alice Anderson"
    assert identity.subject == "uuid-alice"
    assert identity.subject_is_dn_fallback is False
    assert identity.is_member_of(("admin",)) is True
    assert identity.is_member_of(("engineering",)) is False
    # Service bind + the user's own bind.
    assert directory.binds == [(SERVICE_DN, "bindpw"), (identity.dn, "alicepw")]


def test_subject_falls_back_to_the_dn_when_the_attribute_is_missing(
    directory: FakeLdapDirectory,
):
    """A directory without entryUUID/objectGUID must still be usable."""
    directory.add(fake_user("dave", "davepw", email="dave@example.org"))
    identity = _client().authenticate("dave", "davepw")
    assert identity is not None
    assert identity.subject == identity.dn
    assert identity.subject_is_dn_fallback is True


def test_object_guid_bytes_are_hex_encoded(directory: FakeLdapDirectory):
    """AD returns objectGUID as raw bytes; the key must stay printable and stable."""
    directory.add(
        fake_user(
            "carol",
            "carolpw",
            extra={"objectGUID": [bytes.fromhex("0102030a0b0c")]},
        )
    )
    identity = _client(subject_attribute="objectGUID").authenticate("carol", "carolpw")
    assert identity is not None
    assert identity.subject == "0102030a0b0c"
    assert identity.subject_is_dn_fallback is False


def test_wrong_password_and_unknown_user_are_rejected(directory: FakeLdapDirectory):
    client = _client()
    assert client.authenticate("alice", "wrongpw") is None
    assert client.authenticate("nobody", "alicepw") is None
    assert client.authenticate("", "alicepw") is None
    assert client.authenticate("alice", "") is None
    # Every connection is released, including the rejected ones.
    assert directory.unbound == directory.opened


def test_credentials_with_untrusted_dn_are_never_bound(directory: FakeLdapDirectory):
    """A user cannot authenticate as the service account by typing its DN."""
    directory.binds.clear()
    assert _client().authenticate(SERVICE_DN, "bindpw") is None
    # Not merely "refused": the supplied credentials were never sent as a bind.
    # Only the configured service bind may appear, never a second one.
    assert directory.binds == [(SERVICE_DN, "bindpw")], (
        "the typed DN must not be used as a bind identity"
    )


def test_filter_placeholder_is_escaped_against_injection(directory: FakeLdapDirectory):
    client = _client()
    assert client.authenticate("*", "alicepw") is None
    assert client.authenticate("alice", "alicepw") is not None
    lookup = directory.searches[-1][1]
    assert "{username}" not in lookup
    assert "alice" in lookup


def test_mail_login_matches_the_default_filter(directory: FakeLdapDirectory):
    identity = _client().authenticate("alice@example.org", "alicepw")
    assert identity is not None
    assert identity.username == "alice"


def test_user_lookup_prefers_the_exact_username_match(directory: FakeLdapDirectory):
    directory.add(
        fake_user("alice2", "otherpw", email="alice2@example.org", display_name="Alice Two")
    )
    identity = _client(user_filter="(uid=alice*)").authenticate("alice", "alicepw")
    assert identity is not None
    assert identity.username == "alice"


def test_ambiguous_match_without_an_exact_hit_is_refused(directory: FakeLdapDirectory):
    """A broad filter must never verify the password against somebody else."""
    directory.add(fake_user("a1", "pw1", email="shared@example.org"))
    directory.add(fake_user("a2", "pw2", email="shared@example.org"))
    # Both entries match the mail clause, but neither uid equals the input.
    client = _client(user_filter="(mail={username})")
    assert client.authenticate("shared@example.org", "pw1") is None
    assert client.authenticate("shared@example.org", "pw2") is None
    # Only service binds happened; no user bind was attempted against either entry.
    assert {dn for dn, _ in directory.binds} == {SERVICE_DN}


def test_a_partial_username_never_signs_anyone_in(directory: FakeLdapDirectory):
    """A broad filter must not turn a fuzzy hit into a login.

    With ``(uid={username}*)`` the input ``al`` matches exactly one entry, but no
    identifier equals it, so accepting it would silently sign the caller in as
    ``alice``.
    """
    directory.binds.clear()
    assert _client(user_filter="(uid={username}*)").authenticate("al", "alicepw") is None
    assert {dn for dn, _ in directory.binds} <= {SERVICE_DN}


def test_email_is_an_exact_identifier(directory: FakeLdapDirectory):
    """Mail login works because the email attribute counts as an exact match."""
    identity = _client(user_filter="(mail={username})").authenticate("alice@example.org", "alicepw")
    assert identity is not None
    assert identity.username == "alice"


def test_lookup_caps_the_result_set(directory: FakeLdapDirectory):
    """A broad filter must be capped server-side, not materialised then filtered."""
    for index in range(6):
        directory.add(fake_user(f"user{index}", "pw", email="dupe@example.org"))
    assert _client(user_filter="(mail={username})").authenticate("dupe@example.org", "pw") is None
    assert len(directory.searches) == 1
    # The cap is what stops a wide filter from pulling a whole subtree into memory.
    assert directory.size_limits == [_SEARCH_SIZE_LIMIT]


def test_search_failure_is_an_outage_not_a_wrong_password(directory: FakeLdapDirectory):
    """A broken base DN or missing read rights must not read as bad credentials.

    Reporting it as ``None`` would tell the user their password is wrong and spend
    their brute-force budget on an operational fault.
    """
    directory.search_allowed = False
    with pytest.raises(LdapUnavailable):
        _client().authenticate("alice", "alicepw")


def test_zero_match_user_search_is_still_a_credential_verdict(
    directory: FakeLdapDirectory,
):
    """A successful search that matched nobody is "wrong user", not an outage."""
    assert _client().authenticate("no-such-user", "whatever") is None


def test_probe_reports_the_identity_attribute_the_directory_exposes(
    directory: FakeLdapDirectory,
):
    """Lets an admin pick entryUUID vs objectGUID instead of guessing."""
    probe = _client().test()
    assert probe.ok is True
    assert probe.detected_subject_attribute == "entryUUID"


def test_probe_detects_object_guid_on_an_ad_shaped_directory(
    directory: FakeLdapDirectory,
):
    directory.users.clear()
    directory.add(fake_user("ann", "annpw", extra={"objectGUID": [bytes.fromhex("0a0b0c")]}))
    probe = _client(subject_attribute="objectGUID").test()
    assert probe.detected_subject_attribute == "objectGUID"


def test_probe_reports_no_identity_attribute_when_absent(directory: FakeLdapDirectory):
    directory.users.clear()
    directory.add(fake_user("plain", "plainpw"))  # no entryUUID / objectGUID
    probe = _client().test()
    assert probe.ok is True
    assert probe.detected_subject_attribute is None


def test_blank_identity_attribute_falls_back_to_the_dn(directory: FakeLdapDirectory):
    """The shipped default: no attribute configured keys accounts on the DN."""
    identity = _client(subject_attribute="").authenticate("alice", "alicepw")
    assert identity is not None
    assert identity.subject == identity.dn
    assert identity.subject_is_dn_fallback is True


def test_unreachable_server_raises_instead_of_rejecting_credentials(
    directory: FakeLdapDirectory,
):
    directory.reachable = False
    with pytest.raises(LdapUnavailable):
        _client().authenticate("alice", "alicepw")
    probe = _client().test()
    assert probe.ok is False
    assert probe.code == "unreachable"


def test_outage_during_the_user_bind_is_not_a_wrong_password(
    directory: FakeLdapDirectory,
):
    """The search succeeded; the user bind could not connect.

    Reporting that as a rejected password would tell the user their credentials
    are wrong while the directory is simply down.
    """
    directory.outage_after_opens(1)  # service bind ok, user bind cannot connect
    with pytest.raises(LdapUnavailable):
        _client().authenticate("alice", "alicepw")


def test_rejected_service_bind_is_reported_as_unavailable(directory: FakeLdapDirectory):
    client = LdapClient(_config(), "wrong-bind-password")
    probe = client.test()
    assert probe.ok is False
    assert probe.code == "bind_failed"
    with pytest.raises(LdapUnavailable):
        client.authenticate("alice", "alicepw")


def test_probe_reports_search_failures(directory: FakeLdapDirectory):
    directory.search_allowed = False
    probe = _client().test()
    assert probe.ok is False
    assert probe.code == "search_failed"


def test_anonymous_bind_when_no_service_account_is_configured(
    directory: FakeLdapDirectory, monkeypatch: pytest.MonkeyPatch
):
    anonymous = FakeLdapDirectory(bind_dn="", bind_password="")
    anonymous.add(fake_user("carol", "carolpw", display_name="Carol"))
    anonymous.install(monkeypatch)
    identity = LdapClient(_config(bind_dn=""), "").authenticate("carol", "carolpw")
    assert identity is not None
    assert identity.username == "carol"
    assert anonymous.binds[0] == ("", "")


def test_probe_succeeds_against_a_reachable_directory(directory: FakeLdapDirectory):
    probe = _client().test()
    assert probe.ok is True
    assert probe.code == "ok"
    assert probe.detail == "ldaps://directory.example.org"


def test_lookup_raises_when_the_service_account_password_no_longer_works(
    directory: FakeLdapDirectory,
):
    """Rotating the bind password must surface as an outage, not a bad password."""
    directory.bind_password = "rotated"
    with pytest.raises(LdapUnavailable):
        _client().authenticate("alice", "alicepw")


def test_start_tls_failure_is_surfaced(directory: FakeLdapDirectory):
    directory.start_tls_supported = False
    probe = _client(server_url="ldap://host", start_tls=True).test()
    assert probe.ok is False
    assert probe.code == "unreachable"


def test_missing_directory_attributes_do_not_break_the_identity(
    directory: FakeLdapDirectory,
):
    directory.add(fake_user("dave", "davepw"))
    identity = _client().authenticate("dave", "davepw")
    assert identity is not None
    assert identity.email is None
    assert identity.display_name is None
    assert identity.groups == ()


def test_referral_chasing_is_disabled(directory: FakeLdapDirectory):
    """Following a referral could hand the bind password to another server."""
    _client().test()
    assert directory.connections
    assert all(conn.auto_referrals is False for conn in directory.connections)


def test_group_search_mode_resolves_membership_from_group_entries(
    directory: FakeLdapDirectory,
):
    """Directories without the memberOf overlay keep members on the group."""
    directory.add_group(
        FakeLdapGroup(
            dn=ADMIN_GROUP_DN,
            name="admin",
            members=(f"uid=alice,cn=admin,{BASE_DN}",),
        )
    )
    directory.add_group(
        FakeLdapGroup(
            dn=f"cn=ops,ou=groups,{BASE_DN}",
            name="ops",
            members=(f"uid=bob,cn=users,{BASE_DN}",),
            member_attribute="uniqueMember",
        )
    )
    client = _client(
        group_search=True,
        group_search_base=f"ou=groups,{BASE_DN}",
        group_member_attribute="member",
    )
    alice = client.authenticate("alice", "alicepw")
    assert alice is not None
    assert alice.groups == (ADMIN_GROUP_DN,)
    assert alice.is_member_of(("admin",)) is True
    assert alice.is_member_of(("ops",)) is False


def test_group_search_returns_no_groups_for_a_non_member(directory: FakeLdapDirectory):
    directory.add_group(FakeLdapGroup(dn=ADMIN_GROUP_DN, name="admin", members=()))
    client = _client(group_search=True, group_search_base=f"ou=groups,{BASE_DN}")
    identity = client.authenticate("bob", "bobpw")
    assert identity is not None
    assert identity.groups == ()
    assert identity.is_member_of(("admin",)) is False


def test_group_search_matches_a_username_valued_member_attribute(
    directory: FakeLdapDirectory,
):
    """``memberUid`` (classic OpenLDAP posixGroup) holds the bare username.

    Verified against a real glauth directory: ``(memberUid=<user DN>)`` matches
    nothing there, so searching only by DN silently drops every group.
    """
    directory.add_group(
        FakeLdapGroup(
            dn=f"cn=admin,ou=users,{BASE_DN}",
            name="admin",
            members=("alice",),  # username, not a DN
            member_attribute="memberUid",
        )
    )
    client = _client(
        group_search=True,
        group_search_base=f"ou=users,{BASE_DN}",
        group_member_attribute="memberUid",
    )
    identity = client.authenticate("alice", "alicepw")
    assert identity is not None
    assert identity.groups == (f"cn=admin,ou=users,{BASE_DN}",)
    assert identity.is_member_of(("admin",)) is True


def test_group_search_matches_a_dn_valued_member_attribute(directory: FakeLdapDirectory):
    """``member``/``uniqueMember`` hold the member's DN instead."""
    directory.add_group(
        FakeLdapGroup(
            dn=f"cn=admin,ou=groups,{BASE_DN}",
            name="admin",
            members=(f"uid=alice,cn=admin,{BASE_DN}",),
            member_attribute="uniqueMember",
        )
    )
    identity = _client(
        group_search=True,
        group_search_base=f"ou=groups,{BASE_DN}",
        group_member_attribute="uniqueMember",
    ).authenticate("alice", "alicepw")
    assert identity is not None
    assert identity.is_member_of(("admin",)) is True


def test_group_search_base_defaults_to_the_user_base(directory: FakeLdapDirectory):
    directory.add_group(
        FakeLdapGroup(dn=ADMIN_GROUP_DN, name="admin", members=(f"uid=alice,cn=admin,{BASE_DN}",))
    )
    config = _config(group_search=True)
    assert config.effective_group_search_base == BASE_DN
    identity = LdapClient(config, "bindpw").authenticate("alice", "alicepw")
    assert identity is not None
    assert identity.is_member_of(("admin",))
