"""Local CLI credential change-detection fingerprints (not auth storage)."""

from __future__ import annotations

import hashlib

_SALT = b"octop.cli-creds.fingerprint.v1"
# Cheap on purpose: equality marker only — secrets also live in CLI config files.
_ITERATIONS = 10_000


def credential_fingerprint(*parts: str) -> str:
    """Return a stable hex token for ``parts`` used as a local config dirty-check."""
    material = "\0".join(parts).encode("utf-8")
    return hashlib.pbkdf2_hmac("sha256", material, _SALT, _ITERATIONS).hex()
