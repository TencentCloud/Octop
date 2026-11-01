"""MFA orchestration: status, login challenge, verify, enroll, admin reset."""

from __future__ import annotations

import time
from typing import Any, Literal

from octop.infra.auth.mfa import reauth as reauth_mod
from octop.infra.auth.mfa import recovery as recovery_mod
from octop.infra.auth.mfa import totp as totp_mod
from octop.infra.auth.mfa import webauthn as webauthn_mod
from octop.infra.auth.tokens import (
    MFA_TOKEN_TTL_SECONDS,
    PURPOSE_ACCESS,
    PURPOSE_MFA,
    decode_token,
    sign_token,
    token_mfa_version,
    token_purpose,
)
from octop.infra.db.repos.auth_challenges import KIND_MFA, KIND_WEBAUTHN_ASSERT
from octop.infra.db.services import SharedServices
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.users.identity import User

MfaMethod = Literal["totp", "webauthn", "recovery"]
Amr = Literal["password", "ldap"]

MFA_MAX_ATTEMPTS = 5
MFA_LOCKOUT_SECONDS = 900


class MfaService:
    def __init__(self, services: SharedServices) -> None:
        self._s = services

    # --- status / factors -------------------------------------------------

    def has_verified_factor(self, user_id: int) -> bool:
        totp = self._s.user_totp_repo.get_by_user(user_id)
        if totp is not None and totp.is_verified:
            return True
        return self._s.user_webauthn_repo.count_for_user(user_id) > 0

    def methods_for(self, user_id: int) -> list[MfaMethod]:
        methods: list[MfaMethod] = []
        totp = self._s.user_totp_repo.get_by_user(user_id)
        if totp is not None and totp.is_verified:
            methods.append("totp")
        if self._s.user_webauthn_repo.count_for_user(user_id) > 0:
            methods.append("webauthn")
        if self._s.user_recovery_code_repo.count_unused(user_id) > 0:
            methods.append("recovery")
        return methods

    def status(self, user_id: int) -> dict[str, Any]:
        totp = self._s.user_totp_repo.get_by_user(user_id)
        passkeys = [
            {
                "credential_id": row.credential_id,
                "name": row.name,
                "created_at": row.created_at,
                "last_used_at": row.last_used_at,
            }
            for row in self._s.user_webauthn_repo.list_for_user(user_id)
        ]
        verified_count = (1 if totp is not None and totp.is_verified else 0) + len(passkeys)
        return {
            "totp": {
                "enabled": totp is not None and totp.is_verified,
                "pending": totp is not None and not totp.is_verified,
            },
            "passkeys": passkeys,
            "recovery_codes_remaining": self._s.user_recovery_code_repo.count_unused(user_id),
            "methods": self.methods_for(user_id),
            "is_last_factor": verified_count == 1,
            "mfa_version": self._mfa_version(user_id),
        }

    def verified_factor_count(self, user_id: int) -> int:
        totp = self._s.user_totp_repo.get_by_user(user_id)
        n = 1 if totp is not None and totp.is_verified else 0
        return n + self._s.user_webauthn_repo.count_for_user(user_id)

    # --- access / mfa tokens ----------------------------------------------

    def mint_access_token(self, user: User) -> tuple[str, int]:
        secret = self._s.secret_repo.get("jwt")
        if secret is None:
            raise OctopError(ErrorCode.INTERNAL_ERROR, "jwt secret missing")
        ttl = int(self._s.config.access_token_ttl_seconds)
        token = sign_token(
            secret,
            sub=user.id,
            uname=user.username,
            role=user.role,
            purpose=PURPOSE_ACCESS,
            ttl_seconds=ttl,
            mfa_version=self._mfa_version(user.id),
        )
        return token, ttl

    def issue_mfa_challenge(self, user: User, *, amr: Amr) -> dict[str, Any]:
        self._raise_if_mfa_locked(user.id)
        secret = self._s.secret_repo.get("jwt")
        if secret is None:
            raise OctopError(ErrorCode.INTERNAL_ERROR, "jwt secret missing")
        version = self._mfa_version(user.id)
        token = sign_token(
            secret,
            sub=user.id,
            uname=user.username,
            role=user.role,
            purpose=PURPOSE_MFA,
            ttl_seconds=MFA_TOKEN_TTL_SECONDS,
            mfa_version=version,
            amr=amr,
        )
        payload = decode_token(secret, token)
        jti = str(payload.get("jti") or "")
        expires = int(time.time()) + MFA_TOKEN_TTL_SECONDS
        self._s.auth_challenge_repo.insert(
            kind=KIND_MFA,
            jti=jti,
            user_id=user.id,
            expires_at=expires,
        )
        return {
            "mfa_required": True,
            "mfa_token": token,
            "methods": self.methods_for(user.id),
            "user_hint": user.username,
            "locale": user.locale,
        }

    def _decode_mfa_token(self, mfa_token: str) -> dict[str, Any]:
        secret = self._s.secret_repo.get("jwt")
        if secret is None:
            raise OctopError(ErrorCode.INTERNAL_ERROR, "jwt secret missing")
        try:
            payload = decode_token(secret, mfa_token)
        except Exception as exc:  # noqa: BLE001
            raise OctopError(ErrorCode.MFA_INVALID, "invalid MFA token") from exc
        try:
            purpose = token_purpose(payload)
        except Exception as exc:  # noqa: BLE001
            raise OctopError(ErrorCode.MFA_INVALID, "invalid MFA token") from exc
        if purpose != PURPOSE_MFA:
            raise OctopError(ErrorCode.MFA_INVALID, "invalid MFA token")
        return payload

    def _require_live_mfa_challenge(self, payload: dict[str, Any]) -> tuple[int, str, Any]:
        user_id = int(payload["sub"])
        jti = str(payload.get("jti") or "")
        self._raise_if_mfa_locked(user_id)
        claim_version = token_mfa_version(payload)
        current = self._mfa_version(user_id)
        if claim_version != current:
            if jti:
                self._s.auth_challenge_repo.burn_jti(jti)
            raise OctopError(ErrorCode.MFA_INVALID, "MFA challenge stale")
        row = self._s.auth_challenge_repo.get_by_jti(jti) if jti else None
        if (
            row is None
            or row.kind != KIND_MFA
            or row.user_id != user_id
            or row.consumed_at is not None
            or row.expires_at < int(time.time())
        ):
            raise OctopError(ErrorCode.MFA_INVALID, "invalid MFA challenge")
        return user_id, jti, row

    def _fail_mfa(self, user_id: int, challenge_id: int, *, actor: str) -> None:
        updated = self._s.auth_challenge_repo.increment_attempts(
            challenge_id, max_attempts=MFA_MAX_ATTEMPTS
        )
        retry_after = self._s.user_repo.record_mfa_failure(
            user_id, max_attempts=MFA_MAX_ATTEMPTS, lockout_seconds=MFA_LOCKOUT_SECONDS
        )
        self._s.audit_repo.write(actor=actor, action="auth.mfa_failed", target=str(user_id))
        if retry_after > 0 or (updated is not None and updated.consumed_at is not None):
            if retry_after <= 0:
                retry_after = MFA_LOCKOUT_SECONDS
            raise OctopError(
                ErrorCode.MFA_LOCKED,
                "too many MFA attempts",
                details={"retry_after_seconds": retry_after},
            )
        raise OctopError(ErrorCode.MFA_INVALID, "invalid MFA code")

    def verify_mfa(
        self,
        *,
        mfa_token: str,
        method: MfaMethod,
        code: str | None = None,
        credential: dict[str, Any] | str | None = None,
        origin: str | None = None,
        user_manager: Any,
    ) -> dict[str, Any]:
        payload = self._decode_mfa_token(mfa_token)
        user_id, jti, challenge = self._require_live_mfa_challenge(payload)
        user = user_manager.get_by_id(user_id)
        if user is None:
            raise OctopError(ErrorCode.USER_DISABLED, "user not active")
        ok = False
        if method == "totp":
            ok = totp_mod.verify_for_user(
                self._s.user_totp_repo,
                self._s.secret_repo,
                user_id,
                code or "",
            )
        elif method == "recovery":
            ok = recovery_mod.try_spend_code(self._s.user_recovery_code_repo, user_id, code or "")
            if ok:
                self._s.audit_repo.write(
                    actor=user.username, action="auth.mfa_recovery_used", target=str(user_id)
                )
        elif method == "webauthn":
            if credential is None or not origin:
                raise OctopError(ErrorCode.MFA_INVALID, "passkey assertion required")
            try:
                verified_uid, _cred = webauthn_mod.verify_assertion(
                    settings_repo=self._s.settings_repo,
                    challenge_repo=self._s.auth_challenge_repo,
                    webauthn_repo=self._s.user_webauthn_repo,
                    credential=credential,
                    origin=origin,
                    expected_user_id=user_id,
                    expected_kinds=(KIND_WEBAUTHN_ASSERT,),
                )
                ok = verified_uid == user_id
            except OctopError:
                self._fail_mfa(user_id, challenge.id, actor=user.username)
                raise
        else:
            raise OctopError(ErrorCode.MFA_INVALID, "unknown MFA method")
        if not ok:
            self._fail_mfa(user_id, challenge.id, actor=user.username)
        consumed = self._s.auth_challenge_repo.try_consume_jti(jti)
        if consumed is None:
            raise OctopError(ErrorCode.MFA_INVALID, "invalid MFA challenge")
        self._s.user_repo.clear_mfa_throttle(user_id)
        token, ttl = self.mint_access_token(user)
        return {
            "access_token": token,
            "token_type": "Bearer",
            "expires_in": ttl,
            "user": {
                "id": user.id,
                "username": user.username,
                "role": user.role,
                "display_name": user.display_name,
                "locale": user.locale,
            },
        }

    def mfa_passkey_options(self, *, mfa_token: str, origin: str) -> dict[str, Any]:
        payload = self._decode_mfa_token(mfa_token)
        user_id, _jti, _challenge = self._require_live_mfa_challenge(payload)
        return webauthn_mod.assertion_options_for_user(
            settings_repo=self._s.settings_repo,
            challenge_repo=self._s.auth_challenge_repo,
            webauthn_repo=self._s.user_webauthn_repo,
            user_id=user_id,
            origin=origin,
            kind=KIND_WEBAUTHN_ASSERT,
        )

    # --- passwordless -----------------------------------------------------

    def passkey_login_options(self, *, origin: str) -> dict[str, Any]:
        """Discoverable-credential options for Conditional UI / passwordless."""
        return webauthn_mod.passwordless_options(
            settings_repo=self._s.settings_repo,
            challenge_repo=self._s.auth_challenge_repo,
            origin=origin,
        )

    def passkey_login_verify(
        self,
        *,
        credential: dict[str, Any] | str,
        origin: str,
        user_manager: Any,
    ) -> dict[str, Any]:
        from octop.infra.db.repos.auth_challenges import KIND_WEBAUTHN_LOGIN

        user_id, _cred = webauthn_mod.verify_assertion(
            settings_repo=self._s.settings_repo,
            challenge_repo=self._s.auth_challenge_repo,
            webauthn_repo=self._s.user_webauthn_repo,
            credential=credential,
            origin=origin,
            expected_user_id=None,
            expected_kinds=(KIND_WEBAUTHN_LOGIN,),
        )
        row = self._s.user_repo.get(user_id)
        if row is None or row.disabled:
            raise OctopError(ErrorCode.USER_DISABLED, "user not active")
        if row.password_hash is None:
            raise OctopError(
                ErrorCode.PASSWORD_NOT_SET,
                "passwordless passkey requires a local password account",
            )
        # Respect login lockout (not MFA throttle).
        if int(row.login_locked_until or 0) > int(time.time()):
            retry = int(row.login_locked_until) - int(time.time())
            minutes = max(1, (retry + 59) // 60)
            raise OctopError(
                ErrorCode.LOGIN_LOCKED,
                "account temporarily locked",
                details={"retry_after_seconds": retry, "minutes": minutes},
            )
        user = user_manager.get_by_id(user_id)
        if user is None:
            raise OctopError(ErrorCode.USER_DISABLED, "user not active")
        self._s.audit_repo.write(
            actor=user.username, action="auth.passkey_login", target=str(user_id)
        )
        token, ttl = self.mint_access_token(user)
        return {
            "access_token": token,
            "token_type": "Bearer",
            "expires_in": ttl,
            "user": {
                "id": user.id,
                "username": user.username,
                "role": user.role,
                "display_name": user.display_name,
                "locale": user.locale,
            },
        }

    # --- enrollment (reauth-gated) ----------------------------------------

    def _require_reauth(self, user_id: int, reauth_token: str) -> str:
        return reauth_mod.validate_reauth_grant(self._s, user_id=user_id, reauth_token=reauth_token)

    def totp_begin(self, user: User, *, reauth_token: str) -> dict[str, Any]:
        self._require_reauth(user.id, reauth_token)
        return totp_mod.begin_enroll(
            self._s.user_totp_repo,
            self._s.secret_repo,
            user.id,
            username=user.username,
        )

    def totp_confirm(self, user: User, *, reauth_token: str, code: str) -> dict[str, Any]:
        jti = self._require_reauth(user.id, reauth_token)
        ok = totp_mod.confirm_enroll(self._s.user_totp_repo, self._s.secret_repo, user.id, code)
        if not ok:
            raise OctopError(ErrorCode.MFA_INVALID, "invalid TOTP code")
        reauth_mod.burn_reauth_grant(self._s.auth_challenge_repo, jti)
        codes: list[str] | None = None
        if self._s.user_recovery_code_repo.count_unused(user.id) == 0:
            codes = recovery_mod.issue_codes(self._s.user_recovery_code_repo, user.id)
        version = self._s.user_repo.bump_mfa_version(user.id)
        self._s.audit_repo.write(actor=user.username, action="auth.mfa_enrolled", target="totp")
        token, ttl = self.mint_access_token(user)
        out: dict[str, Any] = {
            "access_token": token,
            "token_type": "Bearer",
            "expires_in": ttl,
            "mfa_version": version,
        }
        if codes is not None:
            out["recovery_codes"] = codes
        return out

    def totp_disable(self, user: User, *, reauth_token: str) -> dict[str, Any]:
        jti = self._require_reauth(user.id, reauth_token)
        # Last-factor disable is allowed (turns off MFA after password reauth).
        self._s.user_totp_repo.delete(user.id)
        reauth_mod.burn_reauth_grant(self._s.auth_challenge_repo, jti)
        if not self.has_verified_factor(user.id):
            self._s.user_recovery_code_repo.delete_all_for_user(user.id)
        version = self._s.user_repo.bump_mfa_version(user.id)
        self._s.audit_repo.write(actor=user.username, action="auth.mfa_disabled", target="totp")
        token, ttl = self.mint_access_token(user)
        return {
            "access_token": token,
            "token_type": "Bearer",
            "expires_in": ttl,
            "mfa_version": version,
        }

    def passkey_register_options(
        self, user: User, *, reauth_token: str, origin: str
    ) -> dict[str, Any]:
        self._require_reauth(user.id, reauth_token)
        return webauthn_mod.registration_options(
            settings_repo=self._s.settings_repo,
            challenge_repo=self._s.auth_challenge_repo,
            webauthn_repo=self._s.user_webauthn_repo,
            user_id=user.id,
            username=user.username,
            display_name=user.display_name,
            origin=origin,
        )

    def passkey_register_verify(
        self,
        user: User,
        *,
        reauth_token: str,
        credential: dict[str, Any] | str,
        origin: str,
        name: str | None = None,
    ) -> dict[str, Any]:
        jti = self._require_reauth(user.id, reauth_token)
        webauthn_mod.verify_registration(
            settings_repo=self._s.settings_repo,
            challenge_repo=self._s.auth_challenge_repo,
            webauthn_repo=self._s.user_webauthn_repo,
            user_id=user.id,
            credential=credential,
            origin=origin,
            name=name,
        )
        reauth_mod.burn_reauth_grant(self._s.auth_challenge_repo, jti)
        codes: list[str] | None = None
        if self._s.user_recovery_code_repo.count_unused(user.id) == 0:
            codes = recovery_mod.issue_codes(self._s.user_recovery_code_repo, user.id)
        version = self._s.user_repo.bump_mfa_version(user.id)
        self._s.audit_repo.write(actor=user.username, action="auth.mfa_enrolled", target="passkey")
        token, ttl = self.mint_access_token(user)
        out: dict[str, Any] = {
            "access_token": token,
            "token_type": "Bearer",
            "expires_in": ttl,
            "mfa_version": version,
        }
        if codes is not None:
            out["recovery_codes"] = codes
        return out

    def passkey_delete(
        self, user: User, *, reauth_token: str, credential_id: str
    ) -> dict[str, Any]:
        jti = self._require_reauth(user.id, reauth_token)
        # Last passkey may be removed (turns off MFA when no other factor remains).
        if not self._s.user_webauthn_repo.delete(user.id, credential_id):
            raise OctopError(ErrorCode.NOT_FOUND, "passkey not found")
        reauth_mod.burn_reauth_grant(self._s.auth_challenge_repo, jti)
        if not self.has_verified_factor(user.id):
            self._s.user_recovery_code_repo.delete_all_for_user(user.id)
        version = self._s.user_repo.bump_mfa_version(user.id)
        self._s.audit_repo.write(actor=user.username, action="auth.mfa_disabled", target="passkey")
        token, ttl = self.mint_access_token(user)
        return {
            "access_token": token,
            "token_type": "Bearer",
            "expires_in": ttl,
            "mfa_version": version,
        }

    def recovery_regenerate(self, user: User, *, reauth_token: str) -> dict[str, Any]:
        jti = self._require_reauth(user.id, reauth_token)
        if not self.has_verified_factor(user.id):
            raise OctopError(
                ErrorCode.MFA_INVALID,
                "recovery codes require a verified MFA factor",
            )
        codes = recovery_mod.issue_codes(self._s.user_recovery_code_repo, user.id)
        reauth_mod.burn_reauth_grant(self._s.auth_challenge_repo, jti)
        version = self._s.user_repo.bump_mfa_version(user.id)
        token, ttl = self.mint_access_token(user)
        return {
            "access_token": token,
            "token_type": "Bearer",
            "expires_in": ttl,
            "mfa_version": version,
            "recovery_codes": codes,
        }

    def admin_reset(self, *, target_user_id: int, actor: str) -> None:
        self._s.user_totp_repo.delete(target_user_id)
        self._s.user_webauthn_repo.delete_all_for_user(target_user_id)
        self._s.user_recovery_code_repo.delete_all_for_user(target_user_id)
        self._s.user_repo.bump_mfa_version(target_user_id)
        self._s.audit_repo.write(actor=actor, action="admin.mfa_reset", target=str(target_user_id))

    def prune(self) -> None:
        self._s.auth_challenge_repo.prune_expired()
        self._s.user_totp_repo.prune_expired_pending()

    # --- helpers ----------------------------------------------------------

    def _mfa_version(self, user_id: int) -> int:
        row = self._s.user_repo.get(user_id)
        return int(row.mfa_version) if row is not None else 0

    def _raise_if_mfa_locked(self, user_id: int) -> None:
        retry = self._s.user_repo.mfa_retry_after(user_id)
        if retry > 0:
            raise OctopError(
                ErrorCode.MFA_LOCKED,
                "too many MFA attempts",
                details={"retry_after_seconds": retry},
            )
