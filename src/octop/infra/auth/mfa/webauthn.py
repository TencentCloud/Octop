"""WebAuthn registration and authentication via Duo py_webauthn."""

from __future__ import annotations

import hashlib
import logging
import time
from typing import Any

from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from octop.infra.auth.mfa.settings import assert_origin_allowed
from octop.infra.db.repos.auth_challenges import (
    KIND_WEBAUTHN_ASSERT,
    KIND_WEBAUTHN_LOGIN,
    KIND_WEBAUTHN_REGISTER,
    AuthChallengeRepo,
)
from octop.infra.db.repos.settings import SettingsRepo
from octop.infra.db.repos.user_webauthn import UserWebauthnRepo
from octop.infra.errors import ErrorCode, OctopError

logger = logging.getLogger(__name__)

CHALLENGE_TTL_SECONDS = 300
RP_NAME = "Octop"
_USER_HANDLE_NAMESPACE = b"octop.webauthn.user_handle.v1:"


def _b64url(data: bytes) -> str:
    return bytes_to_base64url(data)


def _stable_user_handle(user_id: int) -> bytes:
    """Opaque 32-byte WebAuthn user.id — stable for the lifetime of the account.

    Must match between ``registration_options`` and ``verify_registration``.
    A previous bug minted independent random handles for each step, so the
    authenticator stored handle A while the DB stored handle B and every
    subsequent assertion failed the userHandle check.
    """
    return hashlib.sha256(_USER_HANDLE_NAMESPACE + str(user_id).encode("utf-8")).digest()


def _ensure_user_handle(webauthn_repo: UserWebauthnRepo, user_id: int) -> bytes:
    existing = webauthn_repo.user_handle_for(user_id)
    if existing:
        return base64url_to_bytes(existing)
    return _stable_user_handle(user_id)


def registration_options(
    *,
    settings_repo: SettingsRepo,
    challenge_repo: AuthChallengeRepo,
    webauthn_repo: UserWebauthnRepo,
    user_id: int,
    username: str,
    display_name: str | None,
    origin: str,
) -> dict[str, Any]:
    rp_id, _origins = assert_origin_allowed(settings_repo, origin)
    user_handle = _ensure_user_handle(webauthn_repo, user_id)
    exclude = [
        PublicKeyCredentialDescriptor(id=base64url_to_bytes(row.credential_id))
        for row in webauthn_repo.list_for_user(user_id)
    ]
    options = generate_registration_options(
        rp_id=rp_id,
        rp_name=RP_NAME,
        user_name=username,
        user_id=user_handle,
        user_display_name=display_name or username,
        exclude_credentials=exclude or None,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED,
            user_verification=UserVerificationRequirement.PREFERRED,
        ),
    )
    challenge_b64 = _b64url(options.challenge)
    expires = int(time.time()) + CHALLENGE_TTL_SECONDS
    challenge_repo.insert(
        kind=KIND_WEBAUTHN_REGISTER,
        challenge=challenge_b64,
        user_id=user_id,
        expires_at=expires,
    )
    return json_loads_options(options_to_json(options))


def verify_registration(
    *,
    settings_repo: SettingsRepo,
    challenge_repo: AuthChallengeRepo,
    webauthn_repo: UserWebauthnRepo,
    user_id: int,
    credential: dict[str, Any] | str,
    origin: str,
    name: str | None = None,
) -> Any:
    rp_id, origins = assert_origin_allowed(settings_repo, origin)
    # Pull challenge from the credential response when possible; otherwise
    # require the pending row for this user.
    challenge_b64 = _extract_client_challenge(credential)
    row = None
    if challenge_b64:
        row = challenge_repo.get_by_challenge(challenge_b64)
    if row is None or row.kind != KIND_WEBAUTHN_REGISTER or row.user_id != user_id:
        raise OctopError(ErrorCode.MFA_INVALID, "invalid or expired webauthn challenge")
    if row.consumed_at is not None or row.expires_at < int(time.time()):
        raise OctopError(ErrorCode.MFA_INVALID, "invalid or expired webauthn challenge")
    consumed = challenge_repo.try_consume_id(row.id)
    if consumed is None:
        raise OctopError(ErrorCode.MFA_INVALID, "invalid or expired webauthn challenge")
    try:
        verified = verify_registration_response(
            credential=credential,
            expected_challenge=base64url_to_bytes(row.challenge or ""),
            expected_rp_id=rp_id,
            expected_origin=origins,
        )
    except Exception as exc:  # noqa: BLE001 - library raises varied types
        raise OctopError(ErrorCode.MFA_INVALID, "webauthn registration failed") from exc
    # Must equal the user.id sent in registration_options (stable or prior row).
    handle = webauthn_repo.user_handle_for(user_id) or _b64url(_stable_user_handle(user_id))
    cred_id = _b64url(verified.credential_id)
    transports: list[str] = []
    if isinstance(credential, dict):
        response = credential.get("response")
        raw_t = None
        if isinstance(response, dict):
            raw_t = response.get("transports")
        if raw_t is None:
            raw_t = credential.get("transports")
        if isinstance(raw_t, list):
            transports = [str(t) for t in raw_t]
    return webauthn_repo.insert(
        credential_id=cred_id,
        user_id=user_id,
        public_key=verified.credential_public_key,
        user_handle=handle,
        rp_id=rp_id,
        aaguid=str(verified.aaguid) if verified.aaguid else None,
        sign_count=int(verified.sign_count or 0),
        name=name,
        transports=transports,
    )


def assertion_options_for_user(
    *,
    settings_repo: SettingsRepo,
    challenge_repo: AuthChallengeRepo,
    webauthn_repo: UserWebauthnRepo,
    user_id: int,
    origin: str,
    kind: str = KIND_WEBAUTHN_ASSERT,
) -> dict[str, Any]:
    rp_id, _origins = assert_origin_allowed(settings_repo, origin)
    allow = [
        PublicKeyCredentialDescriptor(id=base64url_to_bytes(row.credential_id))
        for row in webauthn_repo.list_for_user(user_id)
    ]
    options = generate_authentication_options(
        rp_id=rp_id,
        allow_credentials=allow or None,
        user_verification=UserVerificationRequirement.PREFERRED,
    )
    challenge_b64 = _b64url(options.challenge)
    expires = int(time.time()) + CHALLENGE_TTL_SECONDS
    challenge_repo.insert(
        kind=kind,
        challenge=challenge_b64,
        user_id=user_id,
        expires_at=expires,
    )
    return json_loads_options(options_to_json(options))


def passwordless_options(
    *,
    settings_repo: SettingsRepo,
    challenge_repo: AuthChallengeRepo,
    origin: str,
) -> dict[str, Any]:
    """Discoverable-credential options (no allowCredentials). Enumeration-safe."""
    rp_id, _origins = assert_origin_allowed(settings_repo, origin)
    options = generate_authentication_options(
        rp_id=rp_id,
        allow_credentials=None,
        user_verification=UserVerificationRequirement.PREFERRED,
    )
    challenge_b64 = _b64url(options.challenge)
    expires = int(time.time()) + CHALLENGE_TTL_SECONDS
    challenge_repo.insert(
        kind=KIND_WEBAUTHN_LOGIN,
        challenge=challenge_b64,
        user_id=None,
        expires_at=expires,
    )
    return json_loads_options(options_to_json(options))


def verify_assertion(
    *,
    settings_repo: SettingsRepo,
    challenge_repo: AuthChallengeRepo,
    webauthn_repo: UserWebauthnRepo,
    credential: dict[str, Any] | str,
    origin: str,
    expected_user_id: int | None = None,
    expected_kinds: tuple[str, ...] = (KIND_WEBAUTHN_ASSERT, KIND_WEBAUTHN_LOGIN),
) -> tuple[int, Any]:
    """Verify an assertion. Returns ``(user_id, credential_row)``."""
    rp_id, origins = assert_origin_allowed(settings_repo, origin)
    challenge_b64 = _extract_client_challenge(credential)
    if not challenge_b64:
        raise OctopError(ErrorCode.MFA_INVALID, "invalid or expired webauthn challenge")
    row = challenge_repo.get_by_challenge(challenge_b64)
    if row is None or row.kind not in expected_kinds:
        raise OctopError(ErrorCode.MFA_INVALID, "invalid or expired webauthn challenge")
    if row.consumed_at is not None or row.expires_at < int(time.time()):
        raise OctopError(ErrorCode.MFA_INVALID, "invalid or expired webauthn challenge")
    cred_id_b64 = _extract_credential_id(credential)
    if not cred_id_b64:
        raise OctopError(ErrorCode.MFA_INVALID, "invalid webauthn credential")
    stored = webauthn_repo.get_by_credential_id(cred_id_b64)
    if stored is None:
        raise OctopError(ErrorCode.MFA_INVALID, "unknown webauthn credential")
    if expected_user_id is not None and stored.user_id != expected_user_id:
        raise OctopError(ErrorCode.MFA_INVALID, "webauthn credential user mismatch")
    if row.user_id is not None and row.user_id != stored.user_id:
        raise OctopError(ErrorCode.MFA_INVALID, "webauthn credential user mismatch")
    # Defer userHandle check until after crypto — possession of the private key
    # is the real proof. Mismatches are healed (registration used to mint two
    # independent random handles for options vs DB insert).
    asserted_handle = _extract_user_handle(credential)
    consumed = challenge_repo.try_consume_id(row.id)
    if consumed is None:
        raise OctopError(ErrorCode.MFA_INVALID, "invalid or expired webauthn challenge")
    try:
        verified = verify_authentication_response(
            credential=credential,
            expected_challenge=base64url_to_bytes(row.challenge or ""),
            expected_rp_id=rp_id,
            expected_origin=origins,
            credential_public_key=stored.public_key,
            credential_current_sign_count=stored.sign_count,
        )
    except Exception as exc:  # noqa: BLE001
        logger.info("webauthn assertion crypto failed: %s", exc)
        raise OctopError(ErrorCode.MFA_INVALID, "webauthn assertion failed") from exc
    if asserted_handle and asserted_handle != stored.user_handle:
        logger.info(
            "healing webauthn user_handle for user_id=%s credential=%s",
            stored.user_id,
            stored.credential_id,
        )
        webauthn_repo.set_user_handle_for_user(stored.user_id, asserted_handle)
    new_count = int(verified.new_sign_count or 0)
    if new_count > 0 and new_count <= stored.sign_count:
        logger.warning(
            "webauthn sign_count did not increase for credential %s (stored=%s new=%s)",
            stored.credential_id,
            stored.sign_count,
            new_count,
        )
    # Synced passkeys may stay at 0 — do not hard-fail; still bump last_used.
    webauthn_repo.update_sign_count(
        stored.credential_id,
        sign_count=max(new_count, stored.sign_count),
    )
    return stored.user_id, stored


def json_loads_options(raw: str) -> dict[str, Any]:
    import json

    data = json.loads(raw)
    if not isinstance(data, dict):
        raise OctopError(ErrorCode.INTERNAL_ERROR, "invalid webauthn options")
    return data


def _extract_client_challenge(credential: dict[str, Any] | str) -> str | None:
    if isinstance(credential, str):
        return None
    response = credential.get("response")
    if not isinstance(response, dict):
        return None
    client_data = response.get("clientDataJSON")
    if not isinstance(client_data, str):
        return None
    try:
        import json

        raw = base64url_to_bytes(client_data)
        data = json.loads(raw.decode("utf-8"))
        ch = data.get("challenge")
        return str(ch) if ch else None
    except Exception:  # noqa: BLE001
        return None


def _extract_credential_id(credential: dict[str, Any] | str) -> str | None:
    if isinstance(credential, str):
        return None
    raw = credential.get("id") or credential.get("rawId")
    if isinstance(raw, str) and raw:
        return raw
    return None


def _extract_user_handle(credential: dict[str, Any] | str) -> str | None:
    if isinstance(credential, str):
        return None
    response = credential.get("response")
    if not isinstance(response, dict):
        return None
    handle = response.get("userHandle")
    if isinstance(handle, str) and handle:
        return handle
    return None
