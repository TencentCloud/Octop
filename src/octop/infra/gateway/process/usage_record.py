"""Collect per-call harness usage and append cache-aware turn totals."""

from __future__ import annotations

import contextlib
import json
from dataclasses import dataclass, field
from typing import Any

_USER_ROLES = frozenset({"human", "user"})
_AI_ROLES = frozenset({"ai", "assistant"})
_USAGE_FIELDS = (
    "input_tokens",
    "uncached_input_tokens",
    "cache_read_tokens",
    "cache_write_tokens",
    "output_tokens",
    "reasoning_tokens",
    "total_tokens",
)


def _token_int(value: Any) -> int:
    """Parse a token count; malformed values must not raise."""
    if isinstance(value, bool) or value is None:
        return 0
    try:
        count = int(value)
    except (TypeError, ValueError):
        return 0
    return count if count > 0 else 0


def _detail_count(details: Any, *names: str) -> int:
    if not isinstance(details, dict):
        return 0
    direct = sum(_token_int(details.get(name)) for name in names)
    prefixed = sum(
        _token_int(value)
        for key, value in details.items()
        if isinstance(key, str) and any(key.endswith(f"_{name}") for name in names)
    )
    return direct + prefixed


def normalize_usage(usage: dict[str, Any]) -> dict[str, Any]:
    """Normalize provider usage into disjoint cache-aware input buckets."""
    input_details = usage.get("input_token_details") or usage.get("prompt_tokens_details")
    output_details = usage.get("output_token_details") or usage.get("completion_tokens_details")
    cache_read = _token_int(usage.get("cache_read_tokens")) or _detail_count(
        input_details, "cache_read", "cached_tokens"
    )
    cache_read = cache_read or _token_int(usage.get("prompt_cache_hit_tokens"))
    cache_write = _token_int(usage.get("cache_write_tokens")) or _detail_count(
        input_details, "cache_creation", "cache_write"
    )
    input_tokens = _token_int(usage.get("input_tokens")) or _token_int(usage.get("prompt_tokens"))
    uncached_raw = usage.get("uncached_input_tokens")
    uncached = (
        _token_int(uncached_raw)
        if uncached_raw is not None
        else max(0, input_tokens - cache_read - cache_write)
    )
    if input_tokens == 0:
        input_tokens = uncached + cache_read + cache_write
    output_tokens = _token_int(usage.get("output_tokens")) or _token_int(
        usage.get("completion_tokens")
    )
    reasoning = _token_int(usage.get("reasoning_tokens")) or _detail_count(
        output_details, "reasoning", "reasoning_tokens"
    )
    return {
        "input_tokens": input_tokens,
        "uncached_input_tokens": uncached,
        "cache_read_tokens": cache_read,
        "cache_write_tokens": cache_write,
        "output_tokens": output_tokens,
        "reasoning_tokens": reasoning,
        "total_tokens": input_tokens + output_tokens,
        "model": str(usage.get("model") or ""),
    }


def _msg_role(msg: Any) -> str:
    if isinstance(msg, dict):
        return str(msg.get("role") or msg.get("type") or "").lower()
    raw = getattr(msg, "type", None)
    if raw:
        return str(raw).lower()
    name = type(msg).__name__.lower()
    if "human" in name:
        return "human"
    if "ai" in name:
        return "ai"
    return ""


def _is_user(msg: Any) -> bool:
    return _msg_role(msg) in _USER_ROLES


def _is_ai(msg: Any) -> bool:
    return _msg_role(msg) in _AI_ROLES


def _msg_value(msg: Any, key: str) -> Any:
    if isinstance(msg, dict):
        return msg.get(key)
    return getattr(msg, key, None)


def _message_usage(msg: Any) -> tuple[str, dict[str, Any]] | None:
    usage_metadata = _msg_value(msg, "usage_metadata")
    response_metadata = _msg_value(msg, "response_metadata")
    model = ""
    wire_usage: dict[str, Any] = {}
    if isinstance(response_metadata, dict):
        model = str(response_metadata.get("model_name") or response_metadata.get("model") or "")
        candidate = response_metadata.get("token_usage") or response_metadata.get("usage")
        if isinstance(candidate, dict):
            wire_usage = candidate
    source = {
        **wire_usage,
        **(usage_metadata if isinstance(usage_metadata, dict) else {}),
    }
    if not source:
        return None
    normalized = normalize_usage({**source, "model": model})
    return str(_msg_value(msg, "id") or ""), normalized


def _chunk_messages(chunk: dict[str, Any]) -> list[Any]:
    data = chunk.get("data")
    if isinstance(data, dict):
        raw = data.get("messages")
        return list(raw) if isinstance(raw, list) else []
    if isinstance(data, list):
        return data
    return []


def _turn_samples_from_messages(messages: list[Any]) -> dict[str, dict[str, Any]]:
    last_user = -1
    for index, msg in enumerate(messages):
        if _is_user(msg):
            last_user = index

    samples: dict[str, dict[str, Any]] = {}
    for index, msg in enumerate(messages[last_user + 1 :], start=last_user + 1):
        if not _is_ai(msg):
            continue
        sample = _message_usage(msg)
        if sample is None:
            continue
        key, usage = sample
        if not any(_token_int(usage.get(name)) for name in ("input_tokens", "output_tokens")):
            continue
        if not key:
            key = f"legacy:{index}:" + json.dumps(usage, sort_keys=True, separators=(",", ":"))
        samples[key] = usage
    return samples


def _aggregate_samples(
    samples: dict[str, dict[str, Any]], *, last_key: str | None = None
) -> dict[str, Any] | None:
    if not samples:
        return None
    totals = dict.fromkeys(_USAGE_FIELDS, 0)
    for sample in samples.values():
        for field_name in _USAGE_FIELDS:
            totals[field_name] += _token_int(sample.get(field_name))
    resolved_last_key = last_key if last_key in samples else next(reversed(samples))
    last = samples[resolved_last_key]
    return {
        **totals,
        "model": str(last.get("model") or ""),
        "model_calls": len(samples),
        "last_input_tokens": _token_int(last.get("input_tokens")),
    }


def turn_usage_from_messages(messages: list[Any]) -> dict[str, Any] | None:
    """Sum every AI model call after the last user message."""
    return _aggregate_samples(_turn_samples_from_messages(messages))


def _usage_samples_from_chunk(
    chunk: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    direct = chunk.get("usage")
    if isinstance(direct, dict):
        usage = normalize_usage({**direct, "model": chunk.get("model") or direct.get("model")})
        call_id = str(chunk.get("call_id") or "")
        if not call_id:
            call_id = "direct:" + json.dumps(usage, sort_keys=True, separators=(",", ":"))
        return {call_id: usage}
    if chunk.get("type") not in ("state_snapshot", "state_update"):
        return {}
    return _turn_samples_from_messages(_chunk_messages(chunk))


def extract_usage_from_chunk(chunk: dict[str, Any]) -> dict[str, Any] | None:
    """Best-effort cache-aware usage extraction for router compatibility."""
    if not isinstance(chunk, dict):
        return None
    return _aggregate_samples(_usage_samples_from_chunk(chunk))


@dataclass
class UsageTracker:
    """Accumulate model calls while replacing stream replays by stable call id."""

    _samples: dict[str, dict[str, Any]] = field(default_factory=dict, init=False)
    _last_key: str | None = field(default=None, init=False)
    _has_explicit_usage: bool = field(default=False, init=False)
    _seen_snapshot: bool = field(default=False, init=False)

    def observe(self, chunk: dict[str, Any]) -> None:
        if not isinstance(chunk, dict):
            return
        is_explicit = isinstance(chunk.get("usage"), dict)
        if self._has_explicit_usage and not is_explicit:
            return
        if is_explicit and not self._has_explicit_usage:
            self._samples.clear()
            self._last_key = None
            self._has_explicit_usage = True

        samples = _usage_samples_from_chunk(chunk)
        if not samples:
            return
        if is_explicit:
            self._samples.update(samples)
        elif chunk.get("type") == "state_snapshot":
            self._samples = samples
            self._seen_snapshot = True
        elif self._seen_snapshot:
            return
        elif any(_is_user(msg) for msg in _chunk_messages(chunk)):
            self._samples = samples
        else:
            self._samples.update(samples)
        self._last_key = next(reversed(samples))

    @property
    def usage(self) -> dict[str, Any] | None:
        return _aggregate_samples(self._samples, last_key=self._last_key)


def record_turn_usage(
    usage_repo: Any,
    *,
    agent_id: str,
    user_id: int,
    thread_id: str,
    usage: dict[str, Any],
    source: str = "chat",
) -> None:
    """Append one cache-aware turn row without allowing bad data to break chat."""
    normalized = normalize_usage(usage)
    with contextlib.suppress(Exception):
        usage_repo.record(
            agent_id=agent_id,
            user_id=user_id,
            thread_id=thread_id,
            model=str(usage.get("model") or normalized.get("model") or ""),
            input_tokens=normalized["input_tokens"],
            uncached_input_tokens=normalized["uncached_input_tokens"],
            cache_read_tokens=normalized["cache_read_tokens"],
            cache_write_tokens=normalized["cache_write_tokens"],
            output_tokens=normalized["output_tokens"],
            reasoning_tokens=normalized["reasoning_tokens"],
            model_calls=max(1, _token_int(usage.get("model_calls"))),
            source=source,
        )
