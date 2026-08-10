"""``stream_errors.*`` — user-facing guidance for chat / IM model failures."""

from __future__ import annotations

from octop.i18n.loader import lookup, tr
from octop.infra.utils.locale import Locale

_PREFIX = "octop:"

STREAM_STALL = f"{_PREFIX}stream_errors.stream_stall"
RATE_LIMIT = f"{_PREFIX}stream_errors.rate_limit"
AUTH = f"{_PREFIX}stream_errors.auth"
CONTEXT_LENGTH = f"{_PREFIX}stream_errors.context_length"
RECURSION_LIMIT = f"{_PREFIX}stream_errors.recursion_limit"
TIMEOUT_NETWORK = f"{_PREFIX}stream_errors.timeout_network"
PROVIDER_UNAVAILABLE = f"{_PREFIX}stream_errors.provider_unavailable"
MODEL_CALL_FAILED = f"{_PREFIX}stream_errors.model_call_failed"

__all__ = [
    "AUTH",
    "CONTEXT_LENGTH",
    "MODEL_CALL_FAILED",
    "PROVIDER_UNAVAILABLE",
    "RATE_LIMIT",
    "RECURSION_LIMIT",
    "STREAM_STALL",
    "TIMEOUT_NETWORK",
    "classify_stream_error_message",
    "format_stream_error",
    "stream_error_message",
]

_STRIP_PREFIXES = (
    "agent error:",
    "error:",
)


def _normalize_message(message: str) -> str:
    msg = message.strip()
    lower = msg.lower()
    for prefix in _STRIP_PREFIXES:
        if lower.startswith(prefix):
            msg = msg[len(prefix) :].strip()
            lower = msg.lower()
            break
    return msg


def classify_stream_error_message(message: str) -> str | None:
    """Return a stable ``octop:stream_errors.*`` key for known model failures."""
    msg = _normalize_message(message)
    if not msg:
        return None
    lower = msg.lower()
    compact = lower.replace("_", "").replace(" ", "")

    if (
        "streamchunktimeouterror" in compact
        or "no streaming chunk received" in lower
        or "stream_chunk_timeout" in lower
    ):
        return STREAM_STALL

    if (
        "error code: 429" in lower
        or "rate_limit" in lower
        or "ratelimiterror" in compact
        or "too many requests" in lower
    ):
        return RATE_LIMIT

    if (
        "error code: 401" in lower
        or "invalid_api_key" in lower
        or "incorrect api key" in lower
        or "authenticationerror" in compact
        or ("unauthorized" in lower and ("api" in lower or "key" in lower))
    ):
        return AUTH

    if (
        "context_length_exceeded" in lower
        or "maximum context length" in lower
        or "prompt is too long" in lower
        or "input tokens exceed" in lower
        or "openaicontextoverflowerror" in compact
    ):
        return CONTEXT_LENGTH

    if (
        "graph_recursion_limit" in lower
        or "graphrecursionerror" in compact
        or "recursion limit of" in lower
        or (
            "recursion_limit" in lower and ("reached" in lower or "without hitting a stop" in lower)
        )
    ):
        return RECURSION_LIMIT

    if (
        "internalservererror" in compact
        or "bad gateway" in lower
        or "service unavailable" in lower
        or "error code: 500" in lower
        or "error code: 502" in lower
        or "error code: 503" in lower
    ):
        return PROVIDER_UNAVAILABLE

    if (
        "request timed out" in lower
        or "timed out or interrupted" in lower
        or "connection error" in lower
        or "apitimeouterror" in compact
        or "apiconnectionerror" in compact
    ):
        return TIMEOUT_NETWORK

    if "model call failed after" in lower:
        return MODEL_CALL_FAILED

    return None


def stream_error_message(error: str | None, locale: str | Locale = "en") -> str:
    """Localized stream / model error for user-facing chat and IM output."""
    if not error:
        return ""
    if error.startswith(_PREFIX):
        key = error.removeprefix(_PREFIX)
        if lookup(key, locale) is not None:
            return tr(key, locale)
    classified = classify_stream_error_message(error)
    if classified is not None:
        return tr(classified.removeprefix(_PREFIX), locale)
    return error


def format_stream_error(exc: BaseException | str, locale: str | Locale = "en") -> str:
    """Classify an exception or raw message; fall back to a short raw string."""
    message = str(exc) if isinstance(exc, BaseException) else exc
    classified = classify_stream_error_message(message)
    if classified is not None:
        return tr(classified.removeprefix(_PREFIX), locale)
    return message[:500]
