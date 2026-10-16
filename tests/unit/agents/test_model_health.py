from __future__ import annotations

from octop.infra.agents.providers.health import (
    FailureScope,
    ModelHealthRegistry,
    classify_model_failure,
)


def test_failed_model_is_skipped_until_cooldown_expires() -> None:
    now = 100.0
    health = ModelHealthRegistry(clock=lambda: now)

    health.record_failure("p/a", kind="provider_unavailable", scope=FailureScope.MODEL)

    assert not health.is_routable("p/a")
    assert health.is_routable("p/b")
    now = 161.0
    assert health.is_routable("p/a")


def test_provider_failure_blocks_sibling_models() -> None:
    health = ModelHealthRegistry(clock=lambda: 100.0)

    health.record_failure("p/a", kind="auth", scope=FailureScope.PROVIDER)

    assert not health.is_routable("p/a")
    assert not health.is_routable("p/b")
    assert health.is_routable("other/a")


def test_success_clears_model_cooldown() -> None:
    health = ModelHealthRegistry(clock=lambda: 100.0)
    health.record_failure("p/a", kind="timeout", scope=FailureScope.MODEL)

    health.record_success("p/a")

    assert health.is_routable("p/a")


def test_success_clears_provider_cooldown() -> None:
    health = ModelHealthRegistry(clock=lambda: 100.0)
    health.record_failure("p/a", kind="auth", scope=FailureScope.PROVIDER)

    health.record_success("p/a")

    assert health.is_routable("p/b")


def test_context_length_failure_allows_failover_without_quarantine() -> None:
    decision = classify_model_failure(RuntimeError("context_length_exceeded"))

    assert decision.failover
    assert decision.scope is FailureScope.NONE
    assert decision.kind == "context_length"


def test_non_health_failure_releases_half_open_probe() -> None:
    now = 100.0
    health = ModelHealthRegistry(clock=lambda: now)
    health.record_failure("p/a", kind="timeout", scope=FailureScope.MODEL)
    now = 161.0

    assert health.begin_attempt("p/a")
    health.record_failure("p/a", kind="context_length", scope=FailureScope.NONE)

    assert health.begin_attempt("p/a")


def test_model_failure_after_provider_probe_releases_provider_circuit() -> None:
    now = 100.0
    health = ModelHealthRegistry(clock=lambda: now)
    health.record_failure("p/a", kind="auth", scope=FailureScope.PROVIDER)
    now = 161.0

    assert health.begin_attempt("p/a")
    health.record_failure("p/a", kind="timeout", scope=FailureScope.MODEL)

    assert health.begin_attempt("p/b")


def test_invalid_request_does_not_trigger_cross_model_failover() -> None:
    decision = classify_model_failure(RuntimeError("HTTP 400 invalid tool schema"))

    assert not decision.failover
    assert decision.scope is FailureScope.NONE
