"""In-process model health and failover classification for AUTO routing."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from octop.i18n.domains.stream import (
    AUTH,
    CONTEXT_LENGTH,
    INSUFFICIENT_BALANCE,
    MODEL_CALL_FAILED,
    PROVIDER_UNAVAILABLE,
    RATE_LIMIT,
    STREAM_STALL,
    TIMEOUT_NETWORK,
    classify_stream_error_message,
    exception_display_message,
)


class FailureScope(StrEnum):
    NONE = "none"
    MODEL = "model"
    PROVIDER = "provider"


@dataclass(frozen=True)
class FailureDecision:
    failover: bool
    kind: str
    scope: FailureScope


@dataclass
class _OpenCircuit:
    failures: int
    open_until: float
    half_open_in_flight: bool = False


_PROVIDER_FAILURES = {AUTH, INSUFFICIENT_BALANCE, RATE_LIMIT}
_MODEL_FAILURES = {
    MODEL_CALL_FAILED,
    PROVIDER_UNAVAILABLE,
    STREAM_STALL,
    TIMEOUT_NETWORK,
}
_MODEL_NOT_FOUND_MARKERS = (
    "model not found",
    "model_not_found",
    "unknown model",
    "does not exist",
    "no such model",
)


def classify_model_failure(exc: Exception) -> FailureDecision:
    """Decide whether AUTO routing may try another model after *exc*."""
    detail = exception_display_message(exc)
    lower = detail.lower()
    if any(marker in lower for marker in _MODEL_NOT_FOUND_MARKERS):
        return FailureDecision(True, "model_not_found", FailureScope.MODEL)

    classified = classify_stream_error_message(detail)
    if classified == CONTEXT_LENGTH:
        return FailureDecision(True, "context_length", FailureScope.NONE)
    if classified in _PROVIDER_FAILURES:
        return FailureDecision(
            True,
            classified.rsplit(".", 1)[-1],
            FailureScope.PROVIDER,
        )
    if classified in _MODEL_FAILURES:
        return FailureDecision(
            True,
            classified.rsplit(".", 1)[-1],
            FailureScope.MODEL,
        )
    if isinstance(exc, TimeoutError | ConnectionError):
        return FailureDecision(True, type(exc).__name__.lower(), FailureScope.MODEL)
    return FailureDecision(False, "request_error", FailureScope.NONE)


class ModelHealthRegistry:
    """Process-local circuit state for AUTO model routing.

    Configuration stays in ``models_json``. Runtime health does not mutate it.
    A process restart clears all circuits and gives every configured model a
    fresh chance.
    """

    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.monotonic,
        base_cooldown_s: float = 60.0,
        max_cooldown_s: float = 900.0,
    ) -> None:
        self._clock = clock
        self._base_cooldown_s = base_cooldown_s
        self._max_cooldown_s = max_cooldown_s
        self._models: dict[str, _OpenCircuit] = {}
        self._providers: dict[str, _OpenCircuit] = {}

    @staticmethod
    def _provider(ref: str) -> str:
        return ref.partition("/")[0]

    def _active(self, circuits: dict[str, _OpenCircuit], key: str) -> _OpenCircuit | None:
        circuit = circuits.get(key)
        if circuit is None:
            return None
        if self._clock() < circuit.open_until:
            return circuit
        return None

    def is_routable(self, ref: str) -> bool:
        """Return whether AUTO routing may consider *ref* now."""
        provider = self._provider(ref)
        return (
            self._active(self._providers, provider) is None
            and self._active(self._models, ref) is None
        )

    def begin_attempt(self, ref: str) -> bool:
        """Reserve a healthy or half-open model for one attempt."""
        provider = self._provider(ref)
        if self._active(self._providers, provider) is not None:
            return False
        provider_circuit = self._providers.get(provider)
        if provider_circuit is not None and provider_circuit.half_open_in_flight:
            return False

        circuit = self._models.get(ref)
        if self._active(self._models, ref) is not None:
            return False
        if circuit is not None:
            if circuit.half_open_in_flight:
                return False
            circuit.half_open_in_flight = True
        if provider_circuit is not None:
            provider_circuit.half_open_in_flight = True
        return True

    def _cooldown(self, failures: int) -> float:
        if failures <= 1:
            return self._base_cooldown_s
        if failures == 2:
            return min(self._base_cooldown_s * 5, self._max_cooldown_s)
        return self._max_cooldown_s

    def record_failure(self, ref: str, *, kind: str, scope: FailureScope) -> None:
        """Open the model or provider circuit after exhausted retries."""
        del kind
        provider = self._provider(ref)
        if scope is FailureScope.NONE:
            # A policy/input error still proves that the endpoint answered.
            # Release any expired half-open reservation without quarantining it.
            self.record_success(ref)
            return
        if scope is FailureScope.MODEL:
            provider_circuit = self._providers.get(provider)
            if provider_circuit is not None and self._clock() >= provider_circuit.open_until:
                self._providers.pop(provider, None)
        else:
            model_circuit = self._models.get(ref)
            if model_circuit is not None:
                model_circuit.half_open_in_flight = False
        circuits = self._providers if scope is FailureScope.PROVIDER else self._models
        key = provider if scope is FailureScope.PROVIDER else ref
        previous = circuits.get(key)
        failures = (previous.failures if previous is not None else 0) + 1
        circuits[key] = _OpenCircuit(
            failures=failures,
            open_until=self._clock() + self._cooldown(failures),
        )

    def record_success(self, ref: str) -> None:
        """Close model health state after a successful real call."""
        self._models.pop(ref, None)
        provider = self._provider(ref)
        self._providers.pop(provider, None)

    def snapshot(self, ref: str) -> dict[str, object]:
        """Return a small UI/log-safe health snapshot."""
        provider = self._provider(ref)
        circuit = self._active(self._providers, provider) or self._active(self._models, ref)
        if circuit is None:
            return {"state": "healthy", "cooldown_until": None}
        return {
            "state": "open",
            "cooldown_until": circuit.open_until,
            "failures": circuit.failures,
        }


__all__ = [
    "FailureDecision",
    "FailureScope",
    "ModelHealthRegistry",
    "classify_model_failure",
]
