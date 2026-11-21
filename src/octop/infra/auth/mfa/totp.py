"""TOTP enroll / verify with Fernet-sealed secrets and step replay protection."""

from __future__ import annotations

import time

import pyotp
from cryptography.fernet import InvalidToken

from octop.infra.crypto.fernet import PURPOSE_MFA, decrypt_bytes, encrypt_bytes
from octop.infra.db.repos.secrets import SecretRepo
from octop.infra.db.repos.user_totp import UserTotpRepo
from octop.infra.errors import ErrorCode, OctopError

PENDING_TTL_SECONDS = 600
TOTP_VALID_WINDOW = 1  # ±1 timestep


def generate_secret() -> str:
    return pyotp.random_base32()


def seal_secret(secret_repo: SecretRepo, plain: str) -> bytes:
    return encrypt_bytes(secret_repo, PURPOSE_MFA, plain.encode("utf-8"))


def open_secret(secret_repo: SecretRepo, blob: bytes) -> str:
    """Strict Fernet open — never fall through to a raw blob on InvalidToken."""
    try:
        return decrypt_bytes(secret_repo, PURPOSE_MFA, blob).decode("utf-8")
    except (InvalidToken, ValueError, UnicodeDecodeError) as exc:
        raise OctopError(ErrorCode.MFA_INVALID, "invalid MFA secret") from exc


def otpauth_uri(*, secret: str, username: str, issuer: str = "Octop") -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=username, issuer_name=issuer)


def current_step(*, now: int | None = None) -> int:
    ts = now if now is not None else int(time.time())
    return ts // 30


def verify_code(
    secret: str,
    code: str,
    *,
    last_used_step: int | None,
    now: int | None = None,
) -> int | None:
    """Return the matched timestep on success, else None.

    Rejects reuse of ``last_used_step`` (replay).
    """
    cleaned = (code or "").strip().replace(" ", "")
    if not cleaned.isdigit() or len(cleaned) != 6:
        return None
    totp = pyotp.TOTP(secret)
    ts = now if now is not None else int(time.time())
    # Check current ± window explicitly so we learn which step matched.
    for offset in range(-TOTP_VALID_WINDOW, TOTP_VALID_WINDOW + 1):
        step = (ts // 30) + offset
        if last_used_step is not None and step <= last_used_step:
            continue
        if totp.at(step * 30) == cleaned:
            return step
    return None


def begin_enroll(
    totp_repo: UserTotpRepo,
    secret_repo: SecretRepo,
    user_id: int,
    *,
    username: str,
    now: int | None = None,
) -> dict[str, str | int]:
    ts = now if now is not None else int(time.time())
    plain = generate_secret()
    blob = seal_secret(secret_repo, plain)
    expires = ts + PENDING_TTL_SECONDS
    totp_repo.upsert_pending(user_id, secret_enc=blob, pending_expires_at=expires)
    return {
        "secret": plain,
        "otpauth_uri": otpauth_uri(secret=plain, username=username),
        "pending_expires_at": expires,
    }


def confirm_enroll(
    totp_repo: UserTotpRepo,
    secret_repo: SecretRepo,
    user_id: int,
    code: str,
    *,
    now: int | None = None,
) -> bool:
    row = totp_repo.get_by_user(user_id)
    if row is None or row.is_verified:
        return False
    ts = now if now is not None else int(time.time())
    if row.pending_expires_at is not None and row.pending_expires_at < ts:
        totp_repo.delete(user_id)
        return False
    plain = open_secret(secret_repo, row.secret_enc)
    # Enroll must not consume last_used_step — otherwise the same 30s code
    # cannot be used immediately for the first post-enroll login.
    step = verify_code(plain, code, last_used_step=None, now=ts)
    if step is None:
        return False
    confirmed = totp_repo.confirm(user_id, verified_at=ts)
    return confirmed is not None and confirmed.is_verified


def verify_for_user(
    totp_repo: UserTotpRepo,
    secret_repo: SecretRepo,
    user_id: int,
    code: str,
    *,
    now: int | None = None,
) -> bool:
    row = totp_repo.get_by_user(user_id)
    if row is None or not row.is_verified:
        return False
    plain = open_secret(secret_repo, row.secret_enc)
    step = verify_code(plain, code, last_used_step=row.last_used_step, now=now)
    if step is None:
        return False
    return totp_repo.set_last_used_step(user_id, step)
