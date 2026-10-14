"""LDAP directory configuration stored in ``sso_providers`` (``kind = 'ldap'``).

The provider row owns ``enabled``, ``display_name`` and the encrypted bind
password; every other field lives in the row's ``extra`` JSON document.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from octop.infra.db.repos.sso import SsoProviderRow

LDAP_KIND = "ldap"

USERNAME_PLACEHOLDER = "{username}"
DEFAULT_USER_FILTER = "(|(uid={username})(sAMAccountName={username})(mail={username}))"
DEFAULT_USERNAME_ATTRIBUTE = "uid"
DEFAULT_EMAIL_ATTRIBUTE = "mail"
DEFAULT_DISPLAY_NAME_ATTRIBUTE = "cn"
DEFAULT_GROUP_ATTRIBUTE = "memberOf"
#: Directory-stable identity key. Blank by default: the right value depends on the
#: directory (``entryUUID`` on OpenLDAP, ``objectGUID`` on AD), and guessing wrong
#: silently falls back to the entry DN, so renames would mint duplicate accounts.
#: ``/auth/ldap/config/test`` reports which of the two the directory exposes.
DEFAULT_SUBJECT_ATTRIBUTE = ""
DEFAULT_GROUP_MEMBER_ATTRIBUTE = "member"
DEFAULT_TIMEOUT_SECONDS = 10
MIN_TIMEOUT_SECONDS = 1
MAX_TIMEOUT_SECONDS = 60

_ALLOWED_SCHEMES = ("ldap", "ldaps")
_DEFAULT_PORTS = {"ldap": 389, "ldaps": 636}
_ATTRIBUTE_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9.-]*$")

#: Config fields persisted in the provider row's ``extra`` JSON document.
EXTRA_FIELDS = (
    "server_url",
    "start_tls",
    "verify_tls",
    "bind_dn",
    "user_base_dn",
    "user_filter",
    "username_attribute",
    "email_attribute",
    "display_name_attribute",
    "subject_attribute",
    "group_attribute",
    "group_search",
    "group_search_base",
    "group_member_attribute",
    "admin_groups",
    "allowed_groups",
    "auto_provision",
    "timeout_seconds",
)

_ATTRIBUTE_LABELS = (
    ("username attribute", "username_attribute"),
    ("email attribute", "email_attribute"),
    ("display name attribute", "display_name_attribute"),
)

#: Validated when non-empty; blank means "not configured", not "invalid".
_OPTIONAL_ATTRIBUTE_LABELS = (("identity key attribute", "subject_attribute"),)


@dataclass(frozen=True)
class LdapConfig:
    """Resolved LDAP settings for one installation (single provider row)."""

    enabled: bool = False
    display_name: str = ""
    server_url: str = ""
    start_tls: bool = False
    verify_tls: bool = True
    bind_dn: str = ""
    user_base_dn: str = ""
    user_filter: str = DEFAULT_USER_FILTER
    username_attribute: str = DEFAULT_USERNAME_ATTRIBUTE
    email_attribute: str = DEFAULT_EMAIL_ATTRIBUTE
    display_name_attribute: str = DEFAULT_DISPLAY_NAME_ATTRIBUTE
    subject_attribute: str = DEFAULT_SUBJECT_ATTRIBUTE
    group_attribute: str = DEFAULT_GROUP_ATTRIBUTE
    group_search: bool = False
    group_search_base: str = ""
    group_member_attribute: str = DEFAULT_GROUP_MEMBER_ATTRIBUTE
    admin_groups: tuple[str, ...] = ()
    allowed_groups: tuple[str, ...] = ()
    auto_provision: bool = False
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS

    @property
    def scheme(self) -> str:
        return urlparse(self.server_url).scheme.lower()

    @property
    def use_ssl(self) -> bool:
        return self.scheme == "ldaps"

    @property
    def host(self) -> str:
        return urlparse(self.server_url).hostname or ""

    @property
    def port(self) -> int:
        parsed = urlparse(self.server_url)
        try:
            explicit = parsed.port
        except ValueError:
            explicit = None
        if explicit:
            return explicit
        return _DEFAULT_PORTS.get(self.scheme, 389)

    @property
    def uses_anonymous_bind(self) -> bool:
        return not self.bind_dn.strip()

    @property
    def effective_group_search_base(self) -> str:
        """Groups are searched under their own base when set, else the user base."""
        return self.group_search_base.strip() or self.user_base_dn.strip()

    def is_configured(self) -> bool:
        """True when the settings are complete enough to attempt a login."""
        try:
            self.validate()
        except ValueError:
            return False
        return True

    def warnings(self) -> list[str]:
        """Non-blocking risks worth surfacing in the admin UI and test result."""
        notes: list[str] = []
        if self.enabled and not self.verify_tls:
            notes.append("tls_verification_disabled")
        if not self.admin_groups:
            notes.append("no_admin_groups")
        if self.enabled and not self.allowed_groups and self.auto_provision:
            notes.append("auto_provision_open")
        if self.enabled and self.auto_provision and not self.subject_attribute.strip():
            # New accounts will be keyed on their DN, so moving or renaming a user
            # in the directory produces a second Octop account.
            notes.append("identity_key_is_dn")
        return notes

    def validate(self, *, require_complete: bool = True) -> None:
        """Raise ``ValueError`` describing the first invalid field.

        ``require_complete=False`` only rejects malformed fields, so a partially
        filled form can be saved while the provider stays disabled.
        """
        enclosing = bool(self.enabled)
        scheme = urlparse(self.server_url).scheme.lower()
        if self.server_url.strip() or require_complete:
            if scheme not in _ALLOWED_SCHEMES:
                raise ValueError("server URL must start with ldap:// or ldaps://")
            parsed = urlparse(self.server_url)
            if not parsed.hostname:
                raise ValueError("server URL must include a host")
            try:
                _ = parsed.port
            except ValueError as exc:
                raise ValueError("server URL has an invalid port") from exc
            if self.start_tls and scheme == "ldaps":
                raise ValueError("StartTLS cannot be combined with an ldaps:// server URL")
            # Enabling an unencrypted connection would put user passwords on the
            # wire in clear text; refuse it rather than trusting the operator.
            if enclosing and scheme == "ldap" and not self.start_tls:
                raise ValueError(
                    "enabling LDAP over ldap:// requires StartTLS; otherwise use an ldaps:// URL"
                )
        if not self.user_base_dn.strip() and require_complete:
            raise ValueError("user base DN is required")
        if (self.user_filter.strip() or require_complete) and (
            USERNAME_PLACEHOLDER not in self.user_filter
        ):
            raise ValueError(f"user filter must contain the {USERNAME_PLACEHOLDER} placeholder")
        for label, field in _ATTRIBUTE_LABELS:
            value = getattr(self, field)
            if not value.strip():
                if require_complete:
                    raise ValueError(f"{label} is required")
                continue
            if not _ATTRIBUTE_NAME.match(value.strip()):
                raise ValueError(f"{label} is not a valid LDAP attribute name")
        for label, field in _OPTIONAL_ATTRIBUTE_LABELS:
            # Blank is a deliberate choice: key accounts on the entry DN instead.
            value = getattr(self, field).strip()
            if value and not _ATTRIBUTE_NAME.match(value):
                raise ValueError(f"{label} is not a valid LDAP attribute name")
        # ``group_attribute`` is only read in memberOf mode; searching replaces it.
        if not self.group_search:
            if not self.group_attribute.strip():
                if require_complete:
                    raise ValueError("group attribute is required")
            elif not _ATTRIBUTE_NAME.match(self.group_attribute.strip()):
                raise ValueError("group attribute is not a valid LDAP attribute name")
        elif self.group_member_attribute.strip() and not _ATTRIBUTE_NAME.match(
            self.group_member_attribute.strip()
        ):
            raise ValueError("group member attribute is not a valid LDAP attribute name")
        if self.group_search and require_complete and not self.effective_group_search_base:
            raise ValueError("group search needs a base DN")
        if not MIN_TIMEOUT_SECONDS <= self.timeout_seconds <= MAX_TIMEOUT_SECONDS:
            raise ValueError(
                f"timeout must be between {MIN_TIMEOUT_SECONDS} and {MAX_TIMEOUT_SECONDS} seconds"
            )

    def to_extra(self) -> dict[str, Any]:
        """Return the ``extra`` JSON payload stored on the provider row."""
        return {
            "server_url": self.server_url,
            "start_tls": self.start_tls,
            "verify_tls": self.verify_tls,
            "bind_dn": self.bind_dn,
            "user_base_dn": self.user_base_dn,
            "user_filter": self.user_filter,
            "username_attribute": self.username_attribute,
            "email_attribute": self.email_attribute,
            "display_name_attribute": self.display_name_attribute,
            "subject_attribute": self.subject_attribute,
            "group_attribute": self.group_attribute,
            "group_search": self.group_search,
            "group_search_base": self.group_search_base,
            "group_member_attribute": self.group_member_attribute,
            "admin_groups": list(self.admin_groups),
            "allowed_groups": list(self.allowed_groups),
            "auto_provision": self.auto_provision,
            "timeout_seconds": self.timeout_seconds,
        }

    def to_admin_json(self, *, has_bind_password: bool) -> dict[str, Any]:
        """Return the admin-facing payload; the bind password is never included."""
        return {
            "enabled": self.enabled,
            "display_name": self.display_name,
            **self.to_extra(),
            "admin_groups": ", ".join(self.admin_groups),
            "allowed_groups": ", ".join(self.allowed_groups),
            "has_bind_password": has_bind_password,
            "warnings": self.warnings(),
        }


def config_from_row(row: SsoProviderRow | None) -> LdapConfig:
    """Build a config from the stored provider row (``None`` yields defaults)."""
    if row is None:
        return LdapConfig()
    return merge_config(row, row.extra)


def merge_config(
    row: SsoProviderRow | None,
    extra: Mapping[str, object],
    *,
    enabled: object = None,
    display_name: object = None,
) -> LdapConfig:
    """Layer a payload over the stored row; absent keys keep their stored value."""
    stored: dict[str, object] = dict(row.extra) if row is not None else {}
    values: dict[str, object] = {**stored, **extra}
    return LdapConfig(
        enabled=_as_bool(enabled, bool(row.enabled) if row is not None else False),
        display_name=_as_text(display_name, row.display_name if row is not None else ""),
        server_url=_as_text(values.get("server_url"), ""),
        start_tls=_as_bool(values.get("start_tls"), False),
        verify_tls=_as_bool(values.get("verify_tls"), True),
        bind_dn=_as_text(values.get("bind_dn"), ""),
        user_base_dn=_as_text(values.get("user_base_dn"), ""),
        user_filter=_as_text(values.get("user_filter"), DEFAULT_USER_FILTER),
        username_attribute=_as_text(values.get("username_attribute"), DEFAULT_USERNAME_ATTRIBUTE),
        email_attribute=_as_text(values.get("email_attribute"), DEFAULT_EMAIL_ATTRIBUTE),
        display_name_attribute=_as_text(
            values.get("display_name_attribute"), DEFAULT_DISPLAY_NAME_ATTRIBUTE
        ),
        subject_attribute=_as_text(values.get("subject_attribute"), DEFAULT_SUBJECT_ATTRIBUTE),
        group_attribute=_as_text(values.get("group_attribute"), DEFAULT_GROUP_ATTRIBUTE),
        group_search=_as_bool(values.get("group_search"), False),
        group_search_base=_as_text(values.get("group_search_base"), ""),
        group_member_attribute=_as_text(
            values.get("group_member_attribute"), DEFAULT_GROUP_MEMBER_ATTRIBUTE
        ),
        admin_groups=_as_groups(values.get("admin_groups")),
        allowed_groups=_as_groups(values.get("allowed_groups")),
        auto_provision=_as_bool(values.get("auto_provision"), False),
        timeout_seconds=_as_int(values.get("timeout_seconds"), DEFAULT_TIMEOUT_SECONDS),
    )


def _as_text(value: object, default: str) -> str:
    if isinstance(value, str):
        return value.strip()
    return default


def _as_bool(value: object, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    return default


def _as_int(value: object, default: int) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return int(value.strip())
        except ValueError:
            return default
    return default


def _as_groups(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        parts = _split_groups(value)
    elif isinstance(value, list | tuple):
        parts = [item for item in value if isinstance(item, str)]
    else:
        return ()
    return tuple(part.strip() for part in parts if part.strip())


def _split_groups(raw: str) -> list[str]:
    """Split a comma/newline list of group names or DNs into entries.

    A new entry starts at a fragment with no ``=`` (a bare group CN such as
    ``admin``) or at one whose attribute is ``cn`` (the RDN that names a group
    entry, e.g. ``cn=ops,ou=groups,dc=example,dc=org``). Any other fragment
    continues the current DN. So ``"admin, cn=ops,ou=groups,dc=x"`` yields two
    entries while a single multi-part DN stays intact.
    """
    entries: list[str] = []
    for chunk in raw.replace("\n", ",").replace(";", ",").split(","):
        fragment = chunk.strip()
        if not fragment:
            continue
        if entries and not _starts_group_entry(fragment):
            entries[-1] = f"{entries[-1]},{fragment}"
            continue
        entries.append(fragment)
    return entries


def _starts_group_entry(fragment: str) -> bool:
    attribute, separator, _ = fragment.partition("=")
    if not separator:
        return True
    return attribute.strip().lower() == "cn"
