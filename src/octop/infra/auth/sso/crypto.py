"""Fernet encryption for OIDC single sign-on secrets."""

from __future__ import annotations

from cryptography.fernet import Fernet

from octop.infra.db.repos.secrets import SecretRepo

_FERNET_KEY = "sso_fernet"


def _get_fernet(secret_repo: SecretRepo) -> Fernet:
    raw = secret_repo.get_or_create(_FERNET_KEY, Fernet.generate_key)
    return Fernet(raw)


def encrypt_secret(secret_repo: SecretRepo, plain: str) -> bytes:
    """Encrypt an SSO secret using the installation-specific Fernet key."""
    return _get_fernet(secret_repo).encrypt(plain.encode("utf-8"))


def decrypt_secret(secret_repo: SecretRepo, encrypted: bytes) -> str:
    """Decrypt an SSO secret using the installation-specific Fernet key."""
    return _get_fernet(secret_repo).decrypt(encrypted).decode("utf-8")
