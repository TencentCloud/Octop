"""LDAP configuration parsing, validation, warnings, and group matching."""

from __future__ import annotations

import pytest

from octop.infra.auth.ldap.client import LdapIdentity, rdn_value
from octop.infra.auth.ldap.config import (
    DEFAULT_DISPLAY_NAME_ATTRIBUTE,
    DEFAULT_EMAIL_ATTRIBUTE,
    DEFAULT_GROUP_ATTRIBUTE,
    DEFAULT_SUBJECT_ATTRIBUTE,
    DEFAULT_USER_FILTER,
    DEFAULT_USERNAME_ATTRIBUTE,
    LdapConfig,
    config_from_row,
    merge_config,
)
from octop.infra.db.repos.sso import SsoProviderRow

SECURE_URL = "ldaps://directory.example.org"
PLAIN_URL = "ldap://directory.example.org"


def _row(**extra: object) -> SsoProviderRow:
    return SsoProviderRow(
        id=7,
        enabled=1,
        display_name="Corp Directory",
        issuer="",
        client_id="",
        client_secret_enc=None,
        scopes="",
        dashboard_origin=None,
        created_at=0,
        updated_at=0,
        kind="ldap",
        extra=dict(extra),
    )


def _config(**overrides: object) -> LdapConfig:
    base: dict[str, object] = {
        "enabled": True,
        "server_url": SECURE_URL,
        "user_base_dn": "dc=example,dc=org",
    }
    base.update(overrides)
    return LdapConfig(**base)  # type: ignore[arg-type]


def test_server_url_parsing_applies_scheme_default_ports():
    secure = _config()
    assert (secure.host, secure.port, secure.use_ssl, secure.scheme) == (
        "directory.example.org",
        636,
        True,
        "ldaps",
    )
    plain = _config(server_url=PLAIN_URL, start_tls=True)
    assert (plain.port, plain.use_ssl) == (389, False)
    explicit = _config(server_url="ldaps://directory.example.org:1636")
    assert explicit.port == 1636


def test_anonymous_bind_when_no_bind_dn():
    assert _config().uses_anonymous_bind
    assert not _config(bind_dn="uid=svc,dc=example,dc=org").uses_anonymous_bind


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"server_url": "http://directory.example.org"}, "ldap:// or ldaps://"),
        ({"server_url": ""}, "ldap:// or ldaps://"),
        ({"server_url": "ldap://"}, "must include a host"),
        ({"server_url": SECURE_URL, "start_tls": True}, "StartTLS"),
        ({"user_base_dn": ""}, "user base DN is required"),
        ({"user_filter": "(uid=someone)"}, "{username}"),
        ({"username_attribute": "1bad"}, "not a valid LDAP attribute name"),
        ({"subject_attribute": "9bad"}, "not a valid LDAP attribute name"),
        ({"group_attribute": ""}, "group attribute is required"),
        ({"timeout_seconds": 0}, "timeout must be between"),
        ({"timeout_seconds": 600}, "timeout must be between"),
    ],
)
def test_validation_rejects_bad_configuration(overrides: dict[str, object], expected: str):
    with pytest.raises(ValueError, match=expected):
        _config(**overrides).validate()
    assert _config(**overrides).is_configured() is False


def test_enabling_plain_ldap_without_starttls_is_refused():
    """Passwords would cross the wire in clear text."""
    with pytest.raises(ValueError, match="requires StartTLS"):
        _config(server_url=PLAIN_URL, start_tls=False).validate()

    # The same URL is fine once the provider stays disabled, so a draft can be saved.
    _config(enabled=False, server_url=PLAIN_URL, start_tls=False).validate()
    # …and fine when StartTLS is on.
    _config(server_url=PLAIN_URL, start_tls=True).validate()


def test_partial_configuration_saves_while_disabled():
    draft = _config(enabled=False, server_url="", user_base_dn="")
    with pytest.raises(ValueError):
        draft.validate()
    draft.validate(require_complete=False)  # a disabled draft may be incomplete


def test_defaults_and_round_trip_through_extra():
    config = _config()
    assert config.user_filter == DEFAULT_USER_FILTER
    assert config.username_attribute == DEFAULT_USERNAME_ATTRIBUTE
    assert config.email_attribute == DEFAULT_EMAIL_ATTRIBUTE
    assert config.display_name_attribute == DEFAULT_DISPLAY_NAME_ATTRIBUTE
    # Blank by default: the right value is directory-specific, and guessing
    # wrong would silently key accounts on the mutable entry DN.
    assert config.subject_attribute == DEFAULT_SUBJECT_ATTRIBUTE == ""
    assert config.group_attribute == DEFAULT_GROUP_ATTRIBUTE
    assert config.timeout_seconds == 10
    assert config.verify_tls is True
    assert config.admin_groups == ()
    assert config.allowed_groups == ()
    assert config.group_search is False
    # Provisioning is opt-in: a directory account should not silently gain an
    # Octop account just because it matches the filter.
    assert config.auto_provision is False

    restored = config_from_row(_row(**config.to_extra()))
    assert restored.to_extra() == config.to_extra()
    assert restored.enabled is True
    assert restored.display_name == "Corp Directory"


def test_every_extra_field_survives_a_round_trip():
    config = _config(
        subject_attribute="objectGUID",
        group_search=True,
        group_search_base="ou=groups,dc=example,dc=org",
        group_member_attribute="uniqueMember",
        allowed_groups=("staff",),
        auto_provision=True,
    )
    assert config_from_row(_row(**config.to_extra())).to_extra() == config.to_extra()


def test_config_from_missing_row_is_inert():
    config = config_from_row(None)
    assert config.enabled is False
    assert config.auto_provision is False
    assert config.is_configured() is False


def test_admin_json_never_exposes_the_bind_password():
    payload = config_from_row(_row(**{**_config().to_extra(), "bind_dn": "cn=svc"})).to_admin_json(
        has_bind_password=True
    )
    assert payload["has_bind_password"] is True
    assert "bind_password" not in payload
    assert payload["bind_dn"] == "cn=svc"
    assert "warnings" in payload


def test_warnings_flag_disabled_tls_verification():
    assert "tls_verification_disabled" not in _config().warnings()
    flagged = _config(verify_tls=False)
    assert "tls_verification_disabled" in flagged.warnings()
    # A disabled draft raises no runtime warning for TLS.
    assert "tls_verification_disabled" not in _config(enabled=False, verify_tls=False).warnings()


def test_warnings_flag_a_dn_keyed_identity():
    """Blank identity key + auto-provision means renames mint duplicate accounts."""
    assert "identity_key_is_dn" in _config(auto_provision=True).warnings()
    assert (
        "identity_key_is_dn"
        not in _config(auto_provision=True, subject_attribute="entryUUID").warnings()
    )
    # Only provisioning is affected, so a draft raises nothing.
    assert "identity_key_is_dn" not in _config(enabled=False, auto_provision=True).warnings()


def test_warnings_flag_open_auto_provision():
    assert "auto_provision_open" in _config(auto_provision=True).warnings()
    assert (
        "auto_provision_open"
        not in _config(auto_provision=True, allowed_groups=("staff",)).warnings()
    )


def test_merge_config_keeps_stored_values_for_absent_fields():
    merged = merge_config(_row(**{**_config().to_extra(), "server_url": "ldaps://kept"}), {})
    assert merged.server_url == "ldaps://kept"
    assert merged.enabled is True
    assert merged.display_name == "Corp Directory"
    overridden = merge_config(
        _row(**{**_config().to_extra(), "server_url": "ldaps://kept"}),
        {"server_url": "ldaps://new"},
    )
    assert overridden.server_url == "ldaps://new"


def test_group_lists_accept_comma_string_and_list():
    assert merge_config(None, {"admin_groups": "admin, cn=ops,ou=groups,dc=x"}).admin_groups == (
        "admin",
        "cn=ops,ou=groups,dc=x",
    )
    assert merge_config(None, {"admin_groups": ["admin", " ops "]}).admin_groups == ("admin", "ops")
    assert merge_config(None, {"admin_groups": 5}).admin_groups == ()
    assert merge_config(None, {"allowed_groups": "staff\ncontractors"}).allowed_groups == (
        "staff",
        "contractors",
    )


def _identity(*groups: str) -> LdapIdentity:
    return LdapIdentity(
        dn="uid=alice,cn=staff,dc=example,dc=org",
        username="alice",
        email=None,
        display_name=None,
        groups=tuple(groups),
        subject="uuid-alice",
    )


def test_group_membership_matches_bare_names():
    identity = _identity("cn=admin,ou=groups,dc=example,dc=org")
    assert identity.is_member_of(("admin",))
    assert not identity.is_member_of(("engineering",))
    assert not identity.is_member_of(())


def test_configured_full_dn_must_match_the_whole_dn():
    """A same-named group in another OU must not grant access."""
    identity = _identity("cn=admin,ou=staff,dc=example,dc=org")
    assert identity.is_member_of(("cn=admin,ou=staff,dc=example,dc=org",))
    assert not identity.is_member_of(("cn=admin,ou=contractors,dc=example,dc=org",))
    # …while the bare name still matches, which is the documented short-name risk.
    assert identity.is_member_of(("admin",))


def test_group_membership_is_case_and_space_insensitive():
    identity = _identity("CN=Admin, OU=Groups, DC=Example, DC=Org")
    assert identity.is_member_of(("cn=admin,ou=groups,dc=example,dc=org",))
    assert identity.is_member_of(("ADMIN",))


def test_rdn_value_extracts_first_rdn():
    assert rdn_value("cn=Engineering") == "engineering"
    assert rdn_value("ou=Ops,dc=x") == "ops"
    assert rdn_value("plain") == "plain"
