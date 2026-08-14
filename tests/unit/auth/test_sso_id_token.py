"""Tests for OIDC ID token verification."""

from __future__ import annotations

import json
import time

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from octop.infra.auth.sso.id_token import verify_id_token


@pytest.fixture
def signing_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def jwks_client(signing_key: rsa.RSAPrivateKey) -> httpx.Client:
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(signing_key.public_key()))
    jwk.update({"kid": "test-key", "use": "sig", "alg": "RS256"})

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://issuer.example/jwks"
        return httpx.Response(200, json={"keys": [jwk]})

    return httpx.Client(transport=httpx.MockTransport(handler))


def _token(
    signing_key: rsa.RSAPrivateKey, *, issuer: str = "https://issuer.example", nonce: str = "nonce"
) -> str:
    now = int(time.time())
    return jwt.encode(
        {
            "iss": issuer,
            "aud": ["octop-client", "other-client"],
            "exp": now + 300,
            "iat": now,
            "nonce": nonce,
            "sub": "user-1",
        },
        signing_key,
        algorithm="RS256",
        headers={"kid": "test-key"},
    )


def test_verify_id_token_rejects_wrong_issuer(
    signing_key: rsa.RSAPrivateKey, jwks_client: httpx.Client
) -> None:
    with pytest.raises(jwt.InvalidIssuerError):
        verify_id_token(
            _token(signing_key, issuer="https://other-issuer.example"),
            jwks_uri="https://issuer.example/jwks",
            issuer="https://issuer.example",
            client_id="octop-client",
            nonce="nonce",
            httpx=jwks_client,
        )


def test_verify_id_token_rejects_wrong_nonce(
    signing_key: rsa.RSAPrivateKey, jwks_client: httpx.Client
) -> None:
    with pytest.raises(jwt.InvalidTokenError, match="nonce"):
        verify_id_token(
            _token(signing_key, nonce="unexpected"),
            jwks_uri="https://issuer.example/jwks",
            issuer="https://issuer.example",
            client_id="octop-client",
            nonce="nonce",
            httpx=jwks_client,
        )


def test_verify_id_token_rejects_disallowed_algorithm(
    signing_key: rsa.RSAPrivateKey, jwks_client: httpx.Client
) -> None:
    now = int(time.time())
    hs_token = jwt.encode(
        {
            "iss": "https://issuer.example",
            "aud": "octop-client",
            "exp": now + 300,
            "iat": now,
            "nonce": "nonce",
            "sub": "user-1",
        },
        "symmetric-secret-at-least-32-bytes!!",
        algorithm="HS256",
        headers={"kid": "test-key"},
    )
    with pytest.raises(jwt.InvalidTokenError, match="not allowed"):
        verify_id_token(
            hs_token,
            jwks_uri="https://issuer.example/jwks",
            issuer="https://issuer.example",
            client_id="octop-client",
            nonce="nonce",
            httpx=jwks_client,
        )
