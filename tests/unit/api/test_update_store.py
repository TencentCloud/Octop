"""Unit tests for /api/update in-memory status cache."""

from __future__ import annotations

from octop.api.routers import update_store


def setup_function() -> None:
    update_store.clear_cached_status()


def teardown_function() -> None:
    update_store.clear_cached_status()


def test_get_cached_status_miss_when_empty() -> None:
    assert update_store.get_cached_status() is None


def test_get_cached_status_hit_within_ttl() -> None:
    payload = {"current_version": "1.0.0", "has_update": False}
    update_store.cache_status(payload, cached_at=1_000.0)
    assert update_store.get_cached_status(now=1_000.0 + 60) == payload


def test_get_cached_status_expires_after_ttl() -> None:
    payload = {"current_version": "1.0.0", "has_update": False}
    update_store.cache_status(payload, cached_at=1_000.0)
    expired_at = 1_000.0 + update_store.STATUS_CACHE_TTL_SECONDS + 1
    assert update_store.get_cached_status(now=expired_at) is None
