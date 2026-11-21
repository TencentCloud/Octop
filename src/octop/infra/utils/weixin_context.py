"""Durable WeChat send token stored on a session.

``context_token`` itself is ephemeral: a proactive push strips it. These two
keys are the copy cron still needs after a restart. They match
``octop_gateway.push_routing``, and live here so Octop does not import names
from a gateway build that does not export them yet.
"""

from __future__ import annotations

from typing import Any

WEIXIN_CONTEXT_TOKEN_KEY = "weixin_context_token"
WEIXIN_CONTEXT_TOKEN_MS_KEY = "weixin_context_token_ms"


def weixin_token_ms(meta: dict[str, Any] | None) -> int:
    """Epoch milliseconds of the stored token, or ``0`` when absent or invalid."""
    if not meta:
        return 0
    try:
        return int(meta.get(WEIXIN_CONTEXT_TOKEN_MS_KEY) or 0)
    except (TypeError, ValueError):
        return 0


def with_weixin_send_token(meta: dict[str, Any], token: str, token_ms: int) -> dict[str, Any]:
    """Return a copy of *meta* carrying this send token."""
    updated = dict(meta)
    updated[WEIXIN_CONTEXT_TOKEN_KEY] = token
    updated[WEIXIN_CONTEXT_TOKEN_MS_KEY] = token_ms
    return updated


def merge_weixin_context_token(
    existing: dict[str, Any] | None,
    new: dict[str, Any] | None,
) -> dict[str, Any]:
    """Return *new* metadata, keeping a newer send token already on the session.

    An empty token in *new*, or one older than *existing*, does not clear the
    stored token. Every other key still comes from *new*.
    """
    merged = dict(new or {})
    old = existing or {}
    old_token = str(old.get(WEIXIN_CONTEXT_TOKEN_KEY) or "").strip()
    new_token = str(merged.get(WEIXIN_CONTEXT_TOKEN_KEY) or "").strip()
    old_ms = weixin_token_ms(old)
    new_ms = weixin_token_ms(merged)
    if old_token and (not new_token or old_ms > new_ms):
        merged[WEIXIN_CONTEXT_TOKEN_KEY] = old_token
        merged[WEIXIN_CONTEXT_TOKEN_MS_KEY] = old_ms
    return merged


def selected_weixin_token(meta: dict[str, Any], token: str, token_ms: int) -> bool:
    """True when *meta* kept *token* at *token_ms* after a merge."""
    return (
        str(meta.get(WEIXIN_CONTEXT_TOKEN_KEY) or "") == token and weixin_token_ms(meta) == token_ms
    )
