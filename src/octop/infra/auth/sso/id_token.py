"""OpenID Connect ID token verification."""

from __future__ import annotations

from typing import Any

import httpx as httpx_module
import jwt

# Only asymmetric algorithms used by mainstream OIDC IdPs.
_ALLOWED_ALGORITHMS = ("RS256", "ES256")


def _signing_key(id_token: str, *, jwks_uri: str, httpx: httpx_module.Client) -> jwt.PyJWK:
    header = jwt.get_unverified_header(id_token)
    alg = header.get("alg")
    if alg not in _ALLOWED_ALGORITHMS:
        raise jwt.InvalidTokenError(f"ID token algorithm {alg!r} is not allowed")
    key_id = header.get("kid")
    if not isinstance(key_id, str):
        raise jwt.InvalidTokenError("ID token is missing a key ID")

    response = httpx.get(jwks_uri)
    response.raise_for_status()
    jwks = response.json()
    keys = jwks.get("keys") if isinstance(jwks, dict) else None
    if not isinstance(keys, list):
        raise jwt.InvalidTokenError("JWKS response has no keys")

    for key_data in keys:
        if isinstance(key_data, dict) and key_data.get("kid") == key_id:
            return jwt.PyJWK.from_dict(key_data)
    raise jwt.InvalidTokenError("ID token signing key was not found")


def verify_id_token(
    id_token: str,
    *,
    jwks_uri: str,
    issuer: str,
    client_id: str,
    nonce: str,
    httpx: httpx_module.Client,
) -> dict[str, Any]:
    """Verify an OIDC ID token and return its claims."""
    signing_key = _signing_key(id_token, jwks_uri=jwks_uri, httpx=httpx)
    claims = jwt.decode(
        id_token,
        signing_key.key,
        algorithms=list(_ALLOWED_ALGORITHMS),
        audience=client_id,
        issuer=issuer,
        leeway=60,
        options={"require": ["exp", "iat"]},
    )
    if claims.get("nonce") != nonce:
        raise jwt.InvalidTokenError("ID token nonce does not match")
    return claims
