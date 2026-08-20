"""Context window usage — thin adapter over harness-agent snapshots.

Prefers ``HarnessAgent.aget_context_usage`` when present. Stock occupancy is
stored on ``AIMessage.additional_kwargs['context_usage']``; older stamps may
omit ``source``, which must not be treated as empty. If the live getter
drops those stamps, this module re-reads the same kwargs from history.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# Prefer harness SoT when present (PyPI may lag local editable installs).
_FALLBACK_SEGMENT_KEYS: tuple[str, ...] = (
    "system_prompt",
    "tool_definitions",
    "rules",
    "skills",
    "mcp",
    "subagent_definitions",
    "conversation",
)

try:
    from harness_agent.context_usage import SEGMENT_KEYS as SEGMENT_KEYS
except ImportError:  # pragma: no cover - older orcakit-harness-agent wheels
    SEGMENT_KEYS = _FALLBACK_SEGMENT_KEYS

__all__ = [
    "SEGMENT_KEYS",
    "ContextBreakdownResult",
    "compute_context_breakdown",
    "usage_dict_from_message",
]


@dataclass(frozen=True)
class ContextBreakdownResult:
    max_tokens: int
    used_tokens: int
    segments: dict[str, int]


def _empty_breakdown(*, max_tokens: int) -> ContextBreakdownResult:
    cap = max_tokens if max_tokens > 0 else 128_000
    return ContextBreakdownResult(
        max_tokens=cap,
        used_tokens=0,
        segments=dict.fromkeys(SEGMENT_KEYS, 0),
    )


def _usage_to_breakdown(usage: Any, *, max_tokens: int) -> ContextBreakdownResult:
    with_max = getattr(usage, "with_max_tokens", None)
    if callable(with_max):
        usage = with_max(max_tokens)
    raw_segments = getattr(usage, "segments", None) or {}
    segments = {key: int(raw_segments.get(key, 0) or 0) for key in SEGMENT_KEYS}
    used = int(getattr(usage, "used_tokens", 0) or 0)
    cap = int(getattr(usage, "max_tokens", max_tokens) or max_tokens)
    if max_tokens > 0:
        cap = max_tokens
    return ContextBreakdownResult(max_tokens=cap, used_tokens=used, segments=segments)


def _from_stream_input_tokens(input_tokens: int, *, max_tokens: int) -> ContextBreakdownResult:
    """Minimal fallback when harness has no persisted breakdown yet."""
    cap = max_tokens if max_tokens > 0 else 128_000
    used = min(max(0, input_tokens), cap)
    segments = dict.fromkeys(SEGMENT_KEYS, 0)
    segments["conversation"] = used
    return ContextBreakdownResult(max_tokens=cap, used_tokens=used, segments=segments)


def _usage_has_segments(usage: Any) -> bool:
    if usage is None:
        return False
    used = int(getattr(usage, "used_tokens", 0) or 0)
    inp = int(getattr(usage, "input_tokens", 0) or 0)
    raw = getattr(usage, "segments", None) or {}
    return used > 0 or inp > 0 or any(int(raw.get(k, 0) or 0) > 0 for k in SEGMENT_KEYS)


def _token_int(value: Any) -> int:
    if isinstance(value, bool) or value is None:
        return 0
    try:
        n = int(value)
    except (TypeError, ValueError):
        return 0
    return n if n > 0 else 0


def _as_mapping(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        out = dump()
        return out if isinstance(out, dict) else None
    if value is not None and hasattr(value, "items"):
        try:
            return dict(value)
        except Exception:
            return None
    return None


def _io_from_mapping(data: dict[str, Any] | None) -> tuple[int, int]:
    if not data:
        return 0, 0
    nested = _as_mapping(data.get("token_usage") or data.get("usage"))
    src = nested or data
    inp = (
        _token_int(src.get("input_tokens"))
        or _token_int(src.get("prompt_tokens"))
        or _token_int(src.get("used_tokens"))
    )
    out = _token_int(src.get("output_tokens")) or _token_int(src.get("completion_tokens"))
    return inp, out


def _additional_kwargs(msg: Any) -> dict[str, Any] | None:
    kwargs = getattr(msg, "additional_kwargs", None)
    if kwargs is None and isinstance(msg, dict):
        kwargs = msg.get("additional_kwargs") or msg.get("kwargs")
    return _as_mapping(kwargs)


def _breakdown_from_context_stamp(
    payload: Any, *, max_tokens: int
) -> ContextBreakdownResult | None:
    """Rebuild the ring from ``additional_kwargs['context_usage']`` (stock snapshots)."""
    mapped = _as_mapping(payload)
    if not mapped:
        return None
    segs_raw = _as_mapping(mapped.get("segments")) or {}
    segments = {key: _token_int(segs_raw.get(key)) for key in SEGMENT_KEYS}
    used = (
        _token_int(mapped.get("used_tokens"))
        or _token_int(mapped.get("input_tokens"))
        or sum(segments.values())
    )
    if used <= 0:
        return None
    cap = max_tokens if max_tokens > 0 else 128_000
    if not any(segments.values()):
        segments = dict.fromkeys(SEGMENT_KEYS, 0)
        segments["conversation"] = min(used, cap)
    return ContextBreakdownResult(
        max_tokens=cap,
        used_tokens=min(used, cap),
        segments=segments,
    )


def usage_dict_from_message(msg: Any) -> dict[str, Any] | None:
    """Normalize LangChain token counts for history + the context ring.

    Stock occupancy lives on ``additional_kwargs['context_usage']``. Billing
    counts may also sit on ``usage_metadata`` / ``response_metadata``.
    """
    if isinstance(msg, dict) and "kwargs" in msg and "lc" in msg:
        msg = msg.get("kwargs") or msg

    kwargs = _additional_kwargs(msg)
    stamped = kwargs.get("context_usage") if kwargs else None
    inp, out = _io_from_mapping(_as_mapping(stamped))

    usage = getattr(msg, "usage_metadata", None)
    if usage is None and isinstance(msg, dict):
        usage = msg.get("usage_metadata")
    if inp == 0 and out == 0:
        inp, out = _io_from_mapping(_as_mapping(usage))

    if inp == 0 and out == 0:
        rm = getattr(msg, "response_metadata", None)
        if rm is None and isinstance(msg, dict):
            rm = msg.get("response_metadata")
        inp, out = _io_from_mapping(_as_mapping(rm))

    if inp == 0 and out == 0:
        return None
    payload: dict[str, Any] = {
        "input_tokens": inp,
        "output_tokens": out,
        "total_tokens": inp + out,
    }
    mapped = _as_mapping(usage)
    if mapped:
        details = mapped.get("input_token_details")
        if details is not None:
            payload["input_token_details"] = details
        out_details = mapped.get("output_token_details")
        if out_details is not None:
            payload["output_token_details"] = out_details
    return payload


def _message_input_tokens(msg: Any) -> int:
    usage = usage_dict_from_message(msg)
    return int(usage["input_tokens"]) if usage else 0


async def _load_checkpoint_messages(harness: Any, thread_id: str) -> list[Any]:
    getter = getattr(harness, "aget_history", None)
    if getter is None:
        return []
    try:
        return list(await getter(thread_id, limit=40))
    except Exception:
        logger.debug(
            "aget_history failed while recovering context usage thread=%s",
            thread_id,
            exc_info=True,
        )
        return []


def _stamp_breakdown_from_messages(
    messages: list[Any], *, max_tokens: int
) -> ContextBreakdownResult | None:
    for msg in reversed(messages):
        kwargs = _additional_kwargs(msg)
        if not kwargs:
            continue
        bd = _breakdown_from_context_stamp(kwargs.get("context_usage"), max_tokens=max_tokens)
        if bd is not None:
            return bd
    return None


async def compute_context_breakdown(
    registry: Any,
    *,
    agent_id: str,
    thread_id: str,
    max_tokens: int,
    input_tokens: int | None = None,
    mcp_servers: list[str] | None = None,
    skills: list[str] | None = None,
    usage_repo: Any | None = None,
) -> ContextBreakdownResult:
    """Return harness context usage, or a stream-token fallback.

    ``mcp_servers`` / ``skills`` are accepted for dashboard query compatibility
    but unused — the harness snapshot already reflects the filtered request.
    """
    del mcp_servers, skills
    row = registry.get_row(agent_id)
    if row is None:
        raise ValueError(f"agent {agent_id!r} not found")

    harness: Any = None
    try:
        harness = registry.get_agent(agent_id)
    except Exception:
        logger.debug("no live harness for context usage agent=%s", agent_id, exc_info=True)

    usage: Any = None
    getter = getattr(harness, "aget_context_usage", None) if harness is not None else None
    if getter is not None:
        try:
            usage = await getter(thread_id, max_tokens=max_tokens)
        except Exception:
            logger.debug(
                "harness aget_context_usage failed for thread=%s",
                thread_id,
                exc_info=True,
            )
            usage = None

    if _usage_has_segments(usage):
        return _usage_to_breakdown(usage, max_tokens=max_tokens)

    messages: list[Any] = []
    if harness is not None:
        messages = await _load_checkpoint_messages(harness, thread_id)
        stamped = _stamp_breakdown_from_messages(messages, max_tokens=max_tokens)
        if stamped is not None:
            return stamped

    recovered = 0
    for msg in reversed(messages):
        recovered = _message_input_tokens(msg)
        if recovered:
            break
    logged = 0
    if usage_repo is not None:
        last_fn = getattr(usage_repo, "last_thread_input_tokens", None)
        if callable(last_fn):
            try:
                logged = _token_int(last_fn(agent_id=agent_id, thread_id=thread_id))
            except Exception:
                logger.debug(
                    "usage_log fallback failed for thread=%s",
                    thread_id,
                    exc_info=True,
                )
    fallback = recovered or logged or _token_int(input_tokens)
    if fallback:
        return _from_stream_input_tokens(fallback, max_tokens=max_tokens)

    return _empty_breakdown(max_tokens=max_tokens)
