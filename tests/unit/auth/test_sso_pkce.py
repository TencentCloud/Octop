"""Tests for OIDC PKCE helpers."""

from __future__ import annotations

import base64
import hashlib

from octop.infra.auth.sso.pkce import new_pkce_pair


def test_new_pkce_pair_uses_sha256_urlsafe_challenge() -> None:
    verifier, challenge = new_pkce_pair()

    expected = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest())
        .rstrip(b"=")
        .decode("ascii")
    )

    assert verifier
    assert challenge == expected
