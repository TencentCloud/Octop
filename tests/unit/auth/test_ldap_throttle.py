"""LdapBindThrottle behaviour.

The module guards the one credential path that has no database row to lock:
a directory identifier that has never signed in. Its whole point is that the
budget survives a caller varying anything it controls.
"""

from __future__ import annotations

import pytest

from octop.infra.auth.ldap.throttle import LdapBindThrottle


def _throttle(*, max_attempts: int = 3, block_seconds: int = 60) -> LdapBindThrottle:
    return LdapBindThrottle(
        max_attempts=max_attempts, window_seconds=60, block_seconds=block_seconds
    )


def test_fresh_identifier_may_attempt():
    assert _throttle().retry_after("alice", "10.0.0.1") == 0


def test_block_engages_at_the_limit_and_reports_a_wait():
    throttle = _throttle(max_attempts=3)
    assert throttle.record_failure("alice", "10.0.0.1") == 0
    assert throttle.record_failure("alice", "10.0.0.1") == 0
    retry_after = throttle.record_failure("alice", "10.0.0.1")
    assert retry_after > 0
    assert throttle.retry_after("alice", "10.0.0.1") > 0


def test_blocking_one_identifier_leaves_other_accounts_alone():
    throttle = _throttle(max_attempts=2)
    throttle.record_failure("alice", "10.0.0.1")
    throttle.record_failure("alice", "10.0.0.1")
    assert throttle.retry_after("alice", "10.0.0.1") > 0
    # A different account is unaffected…
    assert throttle.retry_after("bob", "10.0.0.1") == 0
    # …and a *different source* is not collateral damage: the account bucket is
    # per (account, address) so one source cannot lock an account for everyone.
    # Spoofing the address is prevented upstream, by resolve_client_ip.
    assert throttle.retry_after("alice", "10.0.0.2") == 0


def test_one_source_cannot_lock_an_account_for_everyone_else():
    """Per-(account, address) keying bounds the blast radius of a lockout."""
    throttle = _throttle(max_attempts=2)
    throttle.record_failure("alice", "10.0.0.1")
    throttle.record_failure("alice", "10.0.0.1")
    assert throttle.retry_after("alice", "10.0.0.1") > 0
    # Another office/网络 keeps working while the abusive source is blocked.
    assert throttle.retry_after("alice", "10.0.0.9") == 0


def test_success_clears_that_identifier():
    throttle = _throttle(max_attempts=2)
    throttle.record_failure("alice", "10.0.0.1")
    throttle.record_failure("alice", "10.0.0.1")
    assert throttle.retry_after("alice", "10.0.0.1") > 0
    throttle.clear("alice", "10.0.0.1")
    assert throttle.retry_after("alice", "10.0.0.1") == 0


def test_success_does_not_wipe_the_shared_spray_counter():
    """One valid credential must not clear an attacker's other-usernames budget."""
    throttle = _throttle(max_attempts=2)
    # Burn the per-IP allowance (limit * multiplier = 12) with distinct names.
    for index in range(12):
        throttle.record_failure(f"user{index}", "10.0.0.1")
    throttle.clear("user0", "10.0.0.1")
    # A brand-new identifier from the same address is still blocked by the IP rule.
    assert throttle.retry_after("fresh-name", "10.0.0.1") > 0


def test_identifier_matching_is_case_and_space_insensitive():
    throttle = _throttle(max_attempts=2)
    throttle.record_failure(" Alice ", "10.0.0.1")
    throttle.record_failure("alice", "10.0.0.1")
    assert throttle.retry_after("ALICE", "10.0.0.1") > 0


def test_counters_expire_after_the_window(monkeypatch: pytest.MonkeyPatch):
    """A stale failure must not accumulate across an idle period."""
    clock = {"now": 1000.0}
    monkeypatch.setattr("octop.infra.auth.ldap.throttle.time.monotonic", lambda: clock["now"])
    throttle = _throttle(max_attempts=2)
    throttle.record_failure("alice", "10.0.0.1")
    clock["now"] += 3600  # well beyond the 60s window
    throttle.record_failure("alice", "10.0.0.1")  # starts a fresh window
    assert throttle.retry_after("alice", "10.0.0.1") == 0


def test_eviction_keeps_the_map_bounded(monkeypatch: pytest.MonkeyPatch):
    clock = {"now": 1000.0}
    monkeypatch.setattr("octop.infra.auth.ldap.throttle.time.monotonic", lambda: clock["now"])
    throttle = LdapBindThrottle(max_attempts=5, window_seconds=60, block_seconds=60, max_keys=16)
    for index in range(200):
        clock["now"] += 1  # each entry ages, so eviction can drop them
        throttle.record_failure(f"user{index}", f"10.0.1.{index % 250}")
    assert len(throttle._buckets) <= 32, "the failure map must not grow without bound"
