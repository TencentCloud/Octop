"""Shared turn model-ref resolution for router, profile, and compaction."""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from octop_harness.backends.utils import DEFENSIVE_OP_ERRORS

logger = logging.getLogger(__name__)

_NON_TEXT_BLOCK_TYPES: frozenset[str] = frozenset(
    {
        "image",
        "image_url",
        "input_image",
        "audio",
        "input_audio",
        "video",
        "file",
        "input_file",
        "document",
    },
)


def content_has_non_text(content: Any) -> bool:
    if isinstance(content, str):
        return False
    if isinstance(content, list):
        return any(isinstance(block, dict) and block.get("type") in _NON_TEXT_BLOCK_TYPES for block in content)
    return False


def latest_human_needs_multimodal(messages: Sequence[Any] | None) -> bool:
    if not messages:
        return False
    for msg in reversed(list(messages)):
        msg_type = getattr(msg, "type", None)
        if msg_type is None and isinstance(msg, Mapping):
            msg_type = msg.get("type") or msg.get("role")
        if msg_type not in ("human", "user"):
            continue
        content = getattr(msg, "content", None)
        if content is None and isinstance(msg, Mapping):
            content = msg.get("content")
        return content_has_non_text(content)
    return False


def resolve_turn_model_ref(
    *,
    pick_default_ref: Callable[[], str],
    configurable: Mapping[str, Any] | None = None,
    messages: Sequence[Any] | None = None,
    user_selector: Callable[[Any, dict[str, Any]], str | None] | None = None,
    state: Any = None,
    runtime_config: Mapping[str, Any] | None = None,
    pick_multimodal_ref: Callable[[], str | None] | None = None,
) -> str:
    """Resolve the model ref for this turn (same priority as ModelRouter)."""
    cfg = configurable or {}
    explicit = cfg.get("model")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()

    if user_selector is not None:
        try:
            picked = user_selector(state or {}, dict(runtime_config or {"configurable": dict(cfg)}))
        except DEFENSIVE_OP_ERRORS:
            logger.exception("model_selector raised; falling back to default")
            picked = None
        if isinstance(picked, str) and picked.strip():
            return picked.strip()

    if pick_multimodal_ref is not None and latest_human_needs_multimodal(messages):
        mm = pick_multimodal_ref()
        if mm:
            return mm

    return pick_default_ref()


def max_input_tokens_from_model(model: Any, *, fallback: int = 0) -> int:
    """Read ``profile["max_input_tokens"]`` from a chat model instance."""
    profile = getattr(model, "profile", None)
    if isinstance(profile, Mapping):
        raw = profile.get("max_input_tokens")
        if isinstance(raw, int) and raw > 0:
            return raw
        # TurnAwareProfile may need .get to resolve dynamically
        getter = getattr(profile, "get", None)
        if callable(getter):
            raw = getter("max_input_tokens")
            if isinstance(raw, int) and raw > 0:
                return raw
    return fallback if fallback > 0 else 0


__all__ = [
    "content_has_non_text",
    "latest_human_needs_multimodal",
    "max_input_tokens_from_model",
    "resolve_turn_model_ref",
]
