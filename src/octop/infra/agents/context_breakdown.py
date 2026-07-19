"""Context window usage — thin adapter over harness-agent snapshots.

Prefers ``HarnessAgent.aget_context_usage`` when the installed harness-agent
exposes it. Older releases (no ``context_usage`` module / no getter) fall back
to stream ``input_tokens`` as a single ``conversation`` segment so the
dashboard ring stays populated without a second estimation algorithm here.

Note: threads whose checkpoints predate ContextUsageMiddleware have no stamped
breakdown until the next model turn writes ``additional_kwargs["context_usage"]``.
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
    if getattr(usage, "source", None) == "empty":
        return False
    raw = getattr(usage, "segments", None) or {}
    return any(int(raw.get(k, 0) or 0) > 0 for k in SEGMENT_KEYS)


async def compute_context_breakdown(
    registry: Any,
    *,
    agent_id: str,
    thread_id: str,
    max_tokens: int,
    input_tokens: int | None = None,
    mcp_servers: list[str] | None = None,
    skills: list[str] | None = None,
) -> ContextBreakdownResult:
    """Return harness context usage, or a stream-token fallback.

    ``mcp_servers`` / ``skills`` are accepted for dashboard query compatibility
    but unused — the harness snapshot already reflects the filtered request.
    """
    del mcp_servers, skills
    row = registry.get_row(agent_id)
    if row is None:
        raise ValueError(f"agent {agent_id!r} not found")

    harness = registry.get_agent(agent_id)
    usage: Any = None
    getter = getattr(harness, "aget_context_usage", None)
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

    if input_tokens and input_tokens > 0:
        return _from_stream_input_tokens(input_tokens, max_tokens=max_tokens)

    return _empty_breakdown(max_tokens=max_tokens)
