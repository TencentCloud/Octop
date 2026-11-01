"""tests/unit/test_jwt_tokens.py"""

from __future__ import annotations

import pytest

from octop.api.deps import InvalidToken, TokenExpired, decode_token, sign_token
from octop.infra.auth.tokens import PURPOSE_ACCESS, PURPOSE_MFA


def test_sign_and_decode_roundtrip():
    secret = b"x" * 32
    tok = sign_token(
        secret, sub=42, uname="alice", role="user", purpose=PURPOSE_ACCESS, ttl_seconds=60
    )
    payload = decode_token(secret, tok)
    assert payload["sub"] == 42
    assert payload["uname"] == "alice"
    assert payload["role"] == "user"
    assert payload["purpose"] == "access"
    assert payload["mfa_version"] == 0


def test_decode_rejects_wrong_signature():
    tok = sign_token(b"a" * 32, sub=1, uname="a", role="user", purpose=PURPOSE_ACCESS)
    with pytest.raises(InvalidToken):
        decode_token(b"b" * 32, tok)


def test_expired_token_raises_TokenExpired():
    secret = b"x" * 32
    tok = sign_token(secret, sub=1, uname="a", role="user", purpose=PURPOSE_ACCESS, ttl_seconds=-1)
    with pytest.raises(TokenExpired):
        decode_token(secret, tok)


def test_garbage_string_is_invalid():
    with pytest.raises(InvalidToken):
        decode_token(b"x" * 32, "not.a.token")


def test_sign_token_requires_purpose():
    with pytest.raises(TypeError):
        sign_token(b"x" * 32, sub=1, uname="a", role="user")  # type: ignore[call-arg]


def test_mfa_token_requires_amr():
    with pytest.raises(ValueError):
        sign_token(b"x" * 32, sub=1, uname="a", role="user", purpose=PURPOSE_MFA, ttl_seconds=60)
