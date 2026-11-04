"""In-process backoff for LDAP binds.

Local account lockout (``users.login_failed_count``) only covers identifiers that
already have a row in Octop, so a directory account that has never signed in can
be brute-forced without limit — and every attempt consumes one try against the
directory's own lockout policy. This module throttles *before* the bind.

State is per-process and deliberately small: failures are counted per
``(identifier, client ip)`` pair, plus a coarser per-IP total that stops one
source from spraying many usernames. A successful login clears both.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

#: Bucket used when the caller could not resolve an address at all.
UNKNOWN_CLIENT = "unknown"
_DEFAULT_MAX_KEYS = 4096
#: A single IP may fail this many times more than one identifier before the
#: per-IP rule blocks it, so shared NAT is not blocked by one user's typos.
_IP_ATTEMPT_MULTIPLIER = 6


@dataclass
class _Bucket:
    failures: int
    last_seen: float
    blocked_until: float = 0.0


class LdapBindThrottle:
    """Sliding-window failure counter with a fixed block once the limit is hit."""

    def __init__(
        self,
        *,
        max_attempts: int,
        window_seconds: int,
        block_seconds: int,
        max_keys: int = _DEFAULT_MAX_KEYS,
    ) -> None:
        self._max_attempts = max(1, max_attempts)
        self._window = max(1, window_seconds)
        self._block = max(1, block_seconds)
        self._max_keys = max(16, max_keys)
        self._buckets: dict[tuple[str, ...], _Bucket] = {}

    def retry_after(self, identifier: str, client_ip: str) -> int:
        """Seconds the caller must wait; 0 means the attempt may proceed."""
        now = time.monotonic()
        return max(
            self._retry_after_key(self._id_key(identifier, client_ip), now),
            self._retry_after_key(self._ip_key(client_ip), now),
        )

    def record_failure(self, identifier: str, client_ip: str) -> int:
        """Count a failed bind; returns seconds to wait when now blocked."""
        now = time.monotonic()
        self._bump(self._id_key(identifier, client_ip), now, self._max_attempts)
        self._bump(self._ip_key(client_ip), now, self._max_attempts * _IP_ATTEMPT_MULTIPLIER)
        return self.retry_after(identifier, client_ip)

    def clear(self, identifier: str, client_ip: str) -> None:
        """Forget this identifier's counter after a success.

        The per-IP spray counter is deliberately left alone: one valid credential
        must not wipe the budget an attacker burning through other usernames from
        the same address has already spent.
        """
        self._buckets.pop(self._id_key(identifier, client_ip), None)

    @staticmethod
    def _normalize(identifier: str) -> str:
        return (identifier or "").strip().lower()

    def _id_key(self, identifier: str, client_ip: str) -> tuple[str, ...]:
        """Keyed on the account *and* its client address.

        Including the address keeps one source from locking an account out for
        everybody else. It is safe to do so because the caller passes a resolved
        address (see ``octop.api.common.client_ip``), not a raw
        ``X-Forwarded-For`` the caller could vary to reset this budget.
        """
        return ("id", self._normalize(identifier), client_ip or UNKNOWN_CLIENT)

    @staticmethod
    def _ip_key(client_ip: str) -> tuple[str, ...]:
        """Spray guard: one source may only fail so many identifiers."""
        return ("ip", client_ip or UNKNOWN_CLIENT)

    def _retry_after_key(self, key: tuple[str, ...], now: float) -> int:
        bucket = self._buckets.get(key)
        if bucket is None:
            return 0
        if bucket.blocked_until > now:
            return int(bucket.blocked_until - now) + 1
        return 0

    def _bump(self, key: tuple[str, ...], now: float, limit: int) -> None:
        bucket = self._buckets.get(key)
        if bucket is None or now - bucket.last_seen > self._window:
            bucket = _Bucket(failures=0, last_seen=now)
            self._buckets[key] = bucket
        bucket.failures += 1
        bucket.last_seen = now
        if bucket.failures >= limit:
            bucket.blocked_until = now + self._block
            bucket.failures = 0
        self._evict_if_needed(now)

    def _evict_if_needed(self, now: float) -> None:
        if len(self._buckets) <= self._max_keys:
            return
        for key, bucket in sorted(self._buckets.items(), key=lambda item: item[1].last_seen)[
            : len(self._buckets) - self._max_keys
        ]:
            if bucket.blocked_until <= now:  # keep active blocks
                self._buckets.pop(key, None)
