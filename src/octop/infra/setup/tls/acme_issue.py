"""ACME v2 HTTP-01 certificate issuance (Let's Encrypt)."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC
from pathlib import Path

from acme import challenges, errors, messages
from acme.client import ClientNetwork, ClientV2
from acme.crypto_util import make_csr
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from josepy import JWKRSA  # type: ignore[attr-defined]

from octop.infra.setup.tls.challenge import challenge_store
from octop.infra.setup.tls.store import _atomic_write_bytes, account_key_path
from octop.infra.utils.paths import PathLayout

logger = logging.getLogger(__name__)

LE_DIRECTORY_PROD = "https://acme-v02.api.letsencrypt.org/directory"
LE_DIRECTORY_STAGING = "https://acme-staging-v02.api.letsencrypt.org/directory"

ProgressCallback = Callable[[str], None]


def _load_or_create_account_key(path: Path) -> JWKRSA:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        pem = path.read_bytes()
        key = serialization.load_pem_private_key(pem, password=None)
        return JWKRSA(key=key)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    _atomic_write_bytes(path, pem, mode=0o600)
    return JWKRSA(key=key)


def _expiry_from_cert_pem(cert_pem: bytes) -> str:
    cert = x509.load_pem_x509_certificate(cert_pem)
    not_after = cert.not_valid_after_utc
    if not_after.tzinfo is None:
        not_after = not_after.replace(tzinfo=UTC)
    return not_after.astimezone(UTC).replace(microsecond=0).isoformat()


def issue_certificate_http01(
    *,
    domain: str,
    paths: PathLayout,
    staging: bool,
    on_progress: ProgressCallback | None = None,
) -> tuple[bytes, bytes, str]:
    """Run synchronous ACME HTTP-01 flow; returns (cert_pem, key_pem, expires_at iso)."""

    def progress(step: str) -> None:
        logger.info("ACME: %s", step)
        if on_progress:
            on_progress(step)

    domain = domain.strip().lower().rstrip(".")
    directory_url = LE_DIRECTORY_STAGING if staging else LE_DIRECTORY_PROD
    account_key = _load_or_create_account_key(account_key_path(paths))

    progress("registering_acme_account")
    net = ClientNetwork(account_key, user_agent="octop/0.1")
    directory = messages.Directory.from_json(net.get(directory_url).json())
    client = ClientV2(directory, net=net)

    try:
        client.new_account(
            messages.NewRegistration.from_data(
                email=None,
                terms_of_service_agreed=True,
            )
        )
    except errors.ConflictError as exc:
        client.query_registration(
            messages.RegistrationResource(body=messages.Registration(), uri=exc.location)
        )

    progress("creating_order")
    cert_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    cert_key_pem = cert_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    csr_pem = make_csr(cert_key_pem, [domain])
    order = client.new_order(csr_pem)

    progress("preparing_http01_challenge")
    http01: tuple[messages.ChallengeResource, challenges.HTTP01] | None = None
    for authz in order.authorizations:
        for chall in authz.body.challenges:
            if isinstance(chall.chall, challenges.HTTP01):
                http01 = (chall, chall.chall)
                break
        if http01:
            break
    if http01 is None:
        msg = "no HTTP-01 challenge offered by CA"
        raise RuntimeError(msg)

    chall_res, http01_chall = http01
    response = http01_chall.response(account_key)
    # token is raw bytes decoded from base64url; use encode() to get the
    # URL-safe base64 string that the CA expects in the challenge path.
    token_str = http01_chall.encode("token")
    challenge_store.set(token_str, response.key_authorization)

    try:
        progress("answering_challenge")
        client.answer_challenge(chall_res, response)
        progress("waiting_for_validation")
        finalized = client.poll_and_finalize(order)
    finally:
        challenge_store.clear()

    if finalized.fullchain_pem is None:
        msg = "CA returned no certificate"
        raise RuntimeError(msg)

    cert_pem = finalized.fullchain_pem.encode("utf-8")
    expires_at = _expiry_from_cert_pem(cert_pem)
    return cert_pem, cert_key_pem, expires_at
