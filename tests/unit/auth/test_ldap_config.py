"""LDAP configuration parsing, validation, and group matching."""

from __future__ import annotations

import pytest

from octop.infra.auth.ldap.client import LdapIdentity, normalize_group_name
from octop.infra.auth.ldap.config import (
    DEFAULT_DISPLAY_NAME_ATTRIBUTE,
    DEFAULT_EMAIL_ATTRIBUTE,
    DEFAULT_GROUP_ATTRIBUTE,
    DEFAULT_USER_FILTER,
    DEFAULT_USERNAME_ATTRIBUTE,
    LdapConfig,
    config_from_row,
    merge_config,
)
from octop.infra.db.repos.sso import SsoProviderRow


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
        "server_url": "ldap://directory.example.org",
        "user_base_dn": "dc=example,dc=org",
    }
    base.update(overrides)
    return LdapConfig(**base)  # type: ignore[arg-type]


def test_server_url_parsing_applies_scheme_default_ports():
    assert (_config().host, _config().port, _config().use_ssl) == (
        "directory.example.org",
        389,
        False,
    )
    secure = _config(server_url="ldaps://directory.example.org")
    assert (secure.host, secure.port, secure.use_ssl, secure.scheme) == (
        "directory.example.org",
        636,
        True,
        "ldaps",
    )
    explicit = _config(server_url="ldap://directory.example.org:1389")
    assert explicit.port == 1389


def test_anonymous_bind_when_no_bind_dn():
    assert _config().uses_anonymous_bind
    assert not _config(bind_dn="uid=svc,dc=example,dc=org").uses_anonymous_bind


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"server_url": "http://directory.example.org"}, "ldap:// or ldaps://"),
        ({"server_url": ""}, "ldap:// or ldaps://"),
        ({"server_url": "ldap://"}, "must include a host"),
        ({"server_url": "ldaps://host", "start_tls": True}, "StartTLS"),
        ({"user_base_dn": ""}, "user base DN is required"),
        ({"user_filter": "(uid=someone)"}, "{username}"),
        ({"username_attribute": "1bad"}, "not a valid LDAP attribute name"),
        ({"timeout_seconds": 0}, "timeout must be between"),
        ({"timeout_seconds": 600}, "timeout must be between"),
    ],
)
def test_validation_rejects_bad_configuration(overrides: dict[str, object], expected: str):
    with pytest.raises(ValueError, match=expected):
        _config(**overrides).validate()
    assert _config(**overrides).is_configured() is False


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
    assert config.group_attribute == DEFAULT_GROUP_ATTRIBUTE
    assert config.timeout_seconds == 10
    assert config.verify_tls is True
    assert config.admin_groups == ()

    restored = config_from_row(_row(**config.to_extra()))
    assert restored.to_extra() == config.to_extra()
    assert restored.enabled is True
    assert restored.display_name == "Corp Directory"


def test_config_from_missing_row_is_inert():
    config = config_from_row(None)
    assert config.enabled is False
    assert config.is_configured() is False


def test_admin_json_never_exposes_the_bind_password():
    payload = config_from_row(_row(**{**_config().to_extra(), "bind_dn": "cn=svc"})).to_admin_json(
        has_bind_password=True
    )
    assert payload["has_bind_password"] is True
    assert "bind_password" not in payload
    assert payload["bind_dn"] == "cn=svc"


def test_merge_config_keeps_stored_values_for_absent_fields():
    merged = merge_config(_row(**{**_config().to_extra(), "server_url": "ldaps://kept"}), {})
    assert merged.server_url == "ldaps://kept"
    assert merged.enabled is True
    assert merged.display_name == "Corp Directory"
    overridden = merge_config(
        _row(**{**_config().to_extra(), "server_url": "ldaps://kept"}),
        {"server_url": "ldap://new"},
    )
    assert overridden.server_url == "ldap://new"


def test_admin_groups_accepts_comma_string_and_list():
    assert merge_config(None, {"admin_groups": "admin, cn=ops,ou=groups,dc=x"}).admin_groups == (
        "admin",
        "cn=ops,ou=groups,dc=x",
    )
    assert merge_config(None, {"admin_groups": ["admin", " ops "]}).admin_groups == ("admin", "ops")
    assert merge_config(None, {"admin_groups": 5}).admin_groups == ()


def test_group_membership_compares_cn_and_full_dn():
    identity = LdapIdentity(
        dn="uid=alice,cn=admin,dc=example,dc=org",
        username="alice",
        email=None,
        display_name=None,
        groups=("cn=admin,ou=groups,dc=example,dc=org",),
    )
    assert identity.is_member_of(("admin",))
    assert identity.is_member_of(("cn=ADMIN,ou=groups,dc=example,dc=org",))
    assert not identity.is_member_of(("engineering",))
    assert not identity.is_member_of(())


def test_normalize_group_name_strips_ldap_prefix():
    assert normalize_group_name("cn=Engineering") == "engineering"
    assert normalize_group_name("ou=Ops,dc=x") == "ops"
    assert normalize_group_name("plain") == "plain"
