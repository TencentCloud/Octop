"""Argon2id password hashing and change-password policy checks."""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from octop.infra.errors import ErrorCode, OctopError

_HASHER = PasswordHasher()

MIN_PASSWORD_LENGTH = 8

# Case-insensitive denylist for change-password (and shared policy) checks.
_COMMON_PASSWORDS = frozenset(
    {
        "password",
        "password1",
        "password12",
        "password123",
        "12345678",
        "123456789",
        "qwerty123",
        "admin123",
        "welcome1",
        "letmein1",
        "changeme1",
        "octop123",
        "abc12345",
        "iloveyou1",
    }
)


def hash_password(plain: str) -> str:
    if not plain:
        raise ValueError("password must not be empty")
    return _HASHER.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _HASHER.verify(hashed, plain)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def validate_password_policy(password: str, *, old_password: str | None = None) -> None:
    """Raise ``OctopError`` when ``password`` is too weak or equals ``old_password``.

    Rules: at least ``MIN_PASSWORD_LENGTH`` chars, include a letter and a digit,
    not in a small common-password denylist, and not identical to the current password
    when ``old_password`` is provided.
    """
    if old_password is not None and password == old_password:
        raise OctopError(
            ErrorCode.PASSWORD_SAME_AS_OLD,
            "new password must differ from current password",
        )
    if len(password) < MIN_PASSWORD_LENGTH:
        raise OctopError(ErrorCode.PASSWORD_TOO_WEAK, "password too short")
    has_letter = any(c.isalpha() for c in password)
    has_digit = any(c.isdigit() for c in password)
    if not (has_letter and has_digit):
        raise OctopError(
            ErrorCode.PASSWORD_TOO_WEAK,
            "password must include letters and digits",
        )
    if password.lower() in _COMMON_PASSWORDS:
        raise OctopError(ErrorCode.PASSWORD_TOO_WEAK, "password is too common")
