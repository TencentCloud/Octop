"""tests/unit/test_password.py"""

from __future__ import annotations

import pytest

from octop.infra.errors import ErrorCode, OctopError
from octop.infra.users.password import (
    hash_password,
    validate_password_policy,
    verify_password,
)


def test_hash_and_verify_roundtrip():
    h = hash_password("secret")
    assert verify_password("secret", h)
    assert not verify_password("wrong", h)


def test_hashes_are_unique_per_call():
    h1 = hash_password("secret")
    h2 = hash_password("secret")
    assert h1 != h2
    assert verify_password("secret", h1)
    assert verify_password("secret", h2)


def test_empty_password_rejected():
    with pytest.raises(ValueError):
        hash_password("")


def test_verify_handles_corrupt_hash():
    assert not verify_password("anything", "not-a-valid-hash")


def test_validate_password_policy_accepts_strong_password():
    validate_password_policy("Str0ngPass!")


def test_validate_password_policy_rejects_same_as_old():
    with pytest.raises(OctopError) as ei:
        validate_password_policy("Str0ngPass!", old_password="Str0ngPass!")
    assert ei.value.code is ErrorCode.PASSWORD_SAME_AS_OLD


def test_validate_password_policy_rejects_too_short():
    with pytest.raises(OctopError) as ei:
        validate_password_policy("Ab1")
    assert ei.value.code is ErrorCode.PASSWORD_TOO_WEAK


def test_validate_password_policy_rejects_letters_only():
    with pytest.raises(OctopError) as ei:
        validate_password_policy("abcdefgh")
    assert ei.value.code is ErrorCode.PASSWORD_TOO_WEAK


def test_validate_password_policy_rejects_digits_only():
    with pytest.raises(OctopError) as ei:
        validate_password_policy("12345678")
    assert ei.value.code is ErrorCode.PASSWORD_TOO_WEAK


def test_validate_password_policy_rejects_common_password():
    with pytest.raises(OctopError) as ei:
        validate_password_policy("password1")
    assert ei.value.code is ErrorCode.PASSWORD_TOO_WEAK
