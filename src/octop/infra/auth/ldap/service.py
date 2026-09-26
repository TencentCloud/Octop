"""LDAP directory login: bind, provision, and role mapping."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from typing import Any

from octop.infra.auth.ldap.client import LdapClient, LdapIdentity, LdapProbeResult, LdapUnavailable
from octop.infra.auth.ldap.config import (
    EXTRA_FIELDS,
    LDAP_KIND,
    LdapConfig,
    config_from_row,
    merge_config,
)
from octop.infra.auth.sso.crypto import decrypt_secret, encrypt_secret
from octop.infra.db.repos.sso import SsoProviderRow
from octop.infra.db.services import SharedServices
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.users.email import normalize_email
from octop.infra.users.identity import Role, User
from octop.infra.users.manager import UserManager, allocate_username
from octop.infra.utils.locale import normalize_locale

logger = logging.getLogger(__name__)


class LdapAuthService:
    """Owns the single LDAP provider row and turns binds into Octop users."""

    def __init__(self, services: SharedServices, user_manager: UserManager) -> None:
        self._services = services
        self._user_manager = user_manager
        self._lock = asyncio.Lock()

    # ----- configuration -----

    def _row(self) -> SsoProviderRow | None:
        return self._services.sso_repo.get_by_kind(LDAP_KIND)

    def is_enabled(self) -> bool:
        """True when directory login is switched on and fully configured."""
        config = config_from_row(self._row())
        return bool(config.enabled and config.is_configured() and self._user_manager.count() > 0)

    def status(self) -> dict[str, bool | str]:
        """Public login-page payload — never exposes connection details."""
        config = config_from_row(self._row())
        return {
            "enabled": self.is_enabled(),
            "display_name": config.display_name,
        }

    def get_config_for_admin(self) -> dict[str, Any]:
        row = self._row()
        return config_from_row(row).to_admin_json(
            has_bind_password=row is not None and row.client_secret_enc is not None
        )

    def put_config(self, body: Mapping[str, object]) -> dict[str, Any]:
        """Layer an admin payload over the stored row and persist it."""
        row = self._row()
        payload = {name: body[name] for name in EXTRA_FIELDS if name in body}
        config = merge_config(
            row,
            payload,
            enabled=body.get("enabled"),
            display_name=body.get("display_name"),
        )
        config.validate(require_complete=config.enabled)
        password = body.get("bind_password")
        encrypted = (
            encrypt_secret(self._services.secret_repo, password)
            if isinstance(password, str) and password
            else None
        )
        saved = self._services.sso_repo.upsert_by_kind(
            LDAP_KIND,
            enabled=config.enabled,
            display_name=config.display_name or "LDAP",
            issuer="",
            client_id="",
            client_secret_enc=encrypted,
            scopes="",
            dashboard_origin=None,
            extra=config.to_extra(),
        )
        self._services.audit_repo.write(actor="user", action="sso.ldap_config", target=saved.kind)
        return config_from_row(saved).to_admin_json(
            has_bind_password=saved.client_secret_enc is not None
        )

    def test_connection(self) -> LdapProbeResult:
        """Bind against the directory with the stored settings. Raises on bad config."""
        row = self._row()
        if row is None:
            raise ValueError("LDAP is not configured")
        config = config_from_row(row)
        config.validate()
        return LdapClient(config, self._bind_password(row)).test()

    def _bind_password(self, row: SsoProviderRow | None) -> str:
        if row is None or row.client_secret_enc is None:
            return ""
        try:
            return decrypt_secret(self._services.secret_repo, row.client_secret_enc)
        except Exception:  # noqa: BLE001 - a rotated Fernet key must not break login
            logger.warning("could not decrypt the stored LDAP bind password")
            return ""

    # ----- authentication -----

    def directory_authenticate(self, username: str, password: str) -> LdapIdentity | None:
        """Blocking directory bind. Run this in an executor, never on the event loop."""
        row = self._row()
        if row is None:
            return None
        config = config_from_row(row)
        if not config.enabled or not config.is_configured():
            return None
        try:
            return LdapClient(config, self._bind_password(row)).authenticate(username, password)
        except LdapUnavailable as exc:
            raise OctopError(
                ErrorCode.LDAP_UNAVAILABLE,
                f"LDAP directory unavailable: {exc}",
            ) from exc

    async def resolve_user(self, identity: LdapIdentity) -> User:
        """Return the Octop user for a verified directory identity, provisioning if allowed."""
        row = self._row()
        if row is None:
            raise OctopError(ErrorCode.LDAP_UNAVAILABLE, "LDAP is not configured")
        config = config_from_row(row)
        async with self._lock:
            existing = self._services.user_repo.get_by_sso(row.id, identity.dn)
            if existing is not None:
                if existing.disabled:
                    raise OctopError(ErrorCode.USER_DISABLED, "user is disabled")
                self._services.user_repo.update_sso_profile(
                    existing.id,
                    email=self._claimable_email(identity.email, existing.id),
                    display_name=identity.display_name,
                )
                # The directory is authoritative for profile data only. Roles are set
                # once at provisioning time so group changes never silently move
                # privileges on an existing account.
                refreshed = self._services.user_repo.get(existing.id) or existing
                user = self._cached_or_row(refreshed)
                self._services.audit_repo.write(
                    actor=user.username, action="auth.ldap_login", target=user.username
                )
                return user
            if not config.auto_provision:
                raise OctopError(
                    ErrorCode.LDAP_USER_NOT_PROVISIONED,
                    "this directory account has no Octop account yet",
                )
            return self._provision(row, config, identity)

    def _provision(self, row: SsoProviderRow, config: LdapConfig, identity: LdapIdentity) -> User:
        role = Role.ADMIN if identity.is_member_of(config.admin_groups) else Role.USER
        username = allocate_username(
            self._services.user_repo,
            {"preferred_username": identity.username},
            identity.dn,
        )
        try:
            uid = self._services.user_repo.create(
                username=username,
                password_hash=None,
                role=role.value,
                display_name=identity.display_name,
                email=self._claimable_email(identity.email, None),
                sso_provider_id=row.id,
                sso_subject=identity.dn,
            )
        except Exception:
            concurrent = self._services.user_repo.get_by_sso(row.id, identity.dn)
            if concurrent is None:
                raise
            return self._cached_or_row(concurrent)
        self._services.user_repo.upsert_sso_identity(uid, provider_id=row.id, subject=identity.dn)
        user = User(
            id=uid,
            username=username,
            role=role,
            display_name=identity.display_name,
            permissions=[],
        )
        self._user_manager.register_cached_user(user)
        self._services.audit_repo.write(
            actor=username, action="user.ldap_create", target=username, payload=identity.dn
        )
        return user

    # ----- helpers -----

    def _claimable_email(self, email: str | None, owner_id: int | None) -> str | None:
        """Drop an email already owned by a different Octop account."""
        normalized = normalize_email(email)
        if normalized is None:
            return None
        owner = self._services.user_repo.get_by_email(normalized)
        if owner is not None and owner.id != owner_id:
            return None
        return normalized

    def _cached_or_row(self, row: Any) -> User:
        cached = self._user_manager.get(row.username)
        if cached is not None:
            # The display name is directory-owned and changes over time, so the
            # cached ``User`` must not keep serving the value captured when the
            # account was provisioned. Role, permissions and locale are
            # deliberately left alone.
            cached.display_name = row.display_name
            return cached
        user = User(
            id=row.id,
            username=row.username,
            role=Role(row.role),
            display_name=row.display_name,
            locale=normalize_locale(row.locale),
            permissions=list(row.permissions),
        )
        self._user_manager.register_cached_user(user)
        return user
