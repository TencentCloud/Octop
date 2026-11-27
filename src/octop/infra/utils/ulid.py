"""Tiny ULID generator (Crockford base32, monotonic within process)."""

from __future__ import annotations

import os
import threading
import time

_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_LOCK = threading.Lock()
_LAST_MS: int = 0
_LAST_RAND: int = 0


def new_short_id(length: int = 6) -> str:
    """Random Crockford base32 id (default 6 chars, ~1B combinations)."""
    return "".join(_ALPHABET[b & 0x1F] for b in os.urandom(length))


def new_cron_id() -> str:
    """Short human-friendly cron job id, e.g. ``cA1B2C3``."""
    return f"c{new_short_id(6)}"


def new_ulid() -> str:
    global _LAST_MS, _LAST_RAND
    with _LOCK:
        # Keep the timestamp prefix non-decreasing if the wall clock steps back.
        ms = max(int(time.time() * 1000), _LAST_MS)
        if ms == _LAST_MS:
            _LAST_RAND += 1
            rand = _LAST_RAND
        else:
            _LAST_MS = ms
            rand = int.from_bytes(os.urandom(10), "big")
            _LAST_RAND = rand
        return _encode(ms, 10) + _encode(rand, 16)


def _encode(value: int, length: int) -> str:
    out: list[str] = []
    for _ in range(length):
        out.append(_ALPHABET[value & 0x1F])
        value >>= 5
    return "".join(reversed(out))
