"""Slot-name rules for chat-collected agent secrets."""

from __future__ import annotations

import re

# A slot becomes an environment variable in the agent's command executions, so
# its name must be a portable env-var identifier. Uppercase is the convention;
# lowercase is accepted and normalized to upper so one slot cannot appear twice
# under different casings on case-insensitive filesystems/OSes.
_SLOT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")

# Slots are injected as env vars next to the platform's own identity variables;
# shadowing these would break command execution or leak across concerns.
_RESERVED_SLOT_NAMES = frozenset(
    {
        "PATH",
        "HOME",
        "USER",
        "LOGNAME",
        "SHELL",
        "PWD",
        "TMPDIR",
        "TEMP",
        "TMP",
        "LANG",
        "LC_ALL",
        "TERM",
        "HOSTNAME",
        "SSL_CERT_FILE",
        "REQUESTS_CA_BUNDLE",
    }
)
_RESERVED_SLOT_PREFIXES = ("OCTOP_",)

# One slot per named secret; keep a bounded, auditable set per agent.
AGENT_SECRET_MAX_SLOTS = 32
# Submitted values are short credentials, not file payloads.
AGENT_SECRET_MAX_VALUE_CHARS = 8192


def normalize_slot_name(raw: object) -> str | None:
    """Return the canonical slot name, or ``None`` when the name is invalid.

    Canonical form is upper-case. Reserved platform names and the ``OCTOP_``
    prefix (platform identity namespace) are rejected.
    """
    if not isinstance(raw, str):
        return None
    name = raw.strip()
    if not _SLOT_RE.match(name):
        return None
    upper = name.upper()
    if upper in _RESERVED_SLOT_NAMES or upper.startswith(_RESERVED_SLOT_PREFIXES):
        return None
    return upper


__all__ = [
    "AGENT_SECRET_MAX_SLOTS",
    "AGENT_SECRET_MAX_VALUE_CHARS",
    "normalize_slot_name",
]
