"""Email normalization and light validation for local users."""

from __future__ import annotations

import re

from octop.infra.errors import ErrorCode, OctopError

# Practical address shape (not full RFC 5322).
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalize_email(raw: str | None) -> str | None:
    """Strip and lowercase; empty / whitespace-only becomes ``None``."""
    if raw is None:
        return None
    cleaned = raw.strip().lower()
    return cleaned or None


def validate_email_format(email: str) -> None:
    """Raise ``OctopError(EMAIL_INVALID)`` when *email* is not a plausible address."""
    if not _EMAIL_RE.match(email):
        raise OctopError(ErrorCode.EMAIL_INVALID, "invalid email address", status=400)


def parse_optional_email(raw: str | None, *, required_valid: bool = True) -> str | None:
    """Normalize optional email input; optionally validate non-empty values."""
    email = normalize_email(raw)
    if email is None:
        return None
    if required_valid:
        validate_email_format(email)
    return email
