"""Recovery codes: generate, argon2id hash, atomic single-spend."""

from __future__ import annotations

import secrets
import string

from octop.infra.db.repos.user_recovery_codes import UserRecoveryCodeRepo
from octop.infra.users.password import hash_password, verify_password

RECOVERY_CODE_COUNT = 10
_ALPHABET = string.ascii_uppercase + string.digits


def _one_code() -> str:
    # Dash-grouped: XXXX-XXXX
    raw = "".join(secrets.choice(_ALPHABET) for _ in range(8))
    return f"{raw[:4]}-{raw[4:]}"


def generate_codes(count: int = RECOVERY_CODE_COUNT) -> list[str]:
    return [_one_code() for _ in range(count)]


def normalize_code(code: str) -> str:
    return (code or "").strip().upper().replace(" ", "").replace("-", "")


def codes_match(submitted: str, stored: str) -> bool:
    return normalize_code(submitted) == normalize_code(stored)


def issue_codes(repo: UserRecoveryCodeRepo, user_id: int) -> list[str]:
    """Replace unused codes and return the plaintext set once."""
    plain = generate_codes()
    hashes = [hash_password(normalize_code(c)) for c in plain]
    repo.replace_all(user_id, hashes)
    return plain


def try_spend_code(repo: UserRecoveryCodeRepo, user_id: int, code: str) -> bool:
    """Verify against unused hashes and atomically spend the matching row."""
    needle = normalize_code(code)
    if not needle:
        return False
    for row in repo.list_unused(user_id):
        if verify_password(needle, row.code_hash):
            return repo.try_spend(row.id, user_id)
    return False
