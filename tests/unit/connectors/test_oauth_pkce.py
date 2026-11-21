"""PKCE S256 uses the RFC 7636 test vector, not a password hash."""

from __future__ import annotations

from octop.infra.connectors.oauth.pkce import new_pkce_pair, s256_challenge

# RFC 7636 Appendix B.
_VERIFIER = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
_CHALLENGE = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"


def test_s256_challenge_matches_rfc7636() -> None:
    assert s256_challenge(_VERIFIER) == _CHALLENGE


def test_new_pkce_pair_returns_urlsafe_challenge() -> None:
    verifier, challenge = new_pkce_pair()
    assert verifier
    assert challenge
    assert "=" not in challenge
    assert verifier != challenge
