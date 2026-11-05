"""Upstream compatibility patches for langchain-anthropic / anthropic SDK.

Fixes an AttributeError crash in ``langchain_anthropic.chat_models`` during streaming:
when Anthropic returns a ``message_delta`` event carrying ``context_management``
(an unannounced or newly introduced field on the raw API response), the anthropic
SDK stores it in ``__pydantic_extra__`` as a plain ``dict`` rather than a pydantic
model because the non-beta ``RawMessageDeltaEvent`` type does not declare the field.

``ChatAnthropic._make_message_chunk_from_anthropic_event`` then unconditionally calls
``context_management.model_dump()``, raising:
    AttributeError: 'dict' object has no attribute 'model_dump'

This patch wraps ``_make_message_chunk_from_anthropic_event`` (or normalizes the
field on the event) so dicts pass through safely while pydantic models continue to
call ``model_dump()``.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_PATCHED_ATTR = "_octop_anthropic_compat_applied"


def _dump_or_dict(value: Any) -> Any:
    """Return dict representation whether *value* is a pydantic model or already a dict."""
    if value is None:
        return None
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        try:
            return dump()
        except TypeError:
            return dump(mode="json")
    if isinstance(value, dict):
        return dict(value)
    return value


def patch_langchain_anthropic_context_management() -> bool:
    """Monkey-patch ChatAnthropic._make_message_chunk_from_anthropic_event if present."""
    try:
        import langchain_anthropic.chat_models as mod
    except ImportError:
        return False

    chat_cls = getattr(mod, "ChatAnthropic", None)
    if chat_cls is None:
        return False

    if getattr(chat_cls, _PATCHED_ATTR, False):
        return True

    original_make = getattr(chat_cls, "_make_message_chunk_from_anthropic_event", None)
    if not callable(original_make):
        return False

    def _safe_make_message_chunk_from_anthropic_event(
        self: Any,
        event: Any,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        # If the event carries a dict-shaped context_management, adapt it so
        # .model_dump() won't crash if called, OR let original run if it's already a model.
        cm = getattr(event, "context_management", None)
        if isinstance(cm, dict) and not hasattr(cm, "model_dump"):
            # Provide a dummy model_dump method on the dict, or swap to an object
            # that implements model_dump. Subclassing dict is cleanest.
            class _DictWithModelDump(dict):
                def model_dump(self, *a: Any, **kw: Any) -> dict[str, Any]:
                    return dict(self)

            try:
                object.__setattr__(event, "context_management", _DictWithModelDump(cm))
            except (AttributeError, TypeError):
                # Event might be frozen; fall through to wrapped call
                pass

        try:
            return original_make(self, event, *args, **kwargs)
        except AttributeError as exc:
            if "model_dump" not in str(exc):
                raise
            # Fallback path if the attribute could not be replaced on event:
            # temporarily suppress the failure by creating a proxy or catching it.
            # Usually the above object.__setattr__ succeeds because BaseModel allows
            # mutating __dict__/__pydantic_extra__.
            logger.warning(
                "ChatAnthropic._make_message_chunk_from_anthropic_event hit model_dump error, adapting: %s",
                exc,
            )
            # Re-read context_management and replace it in event.__dict__ or __pydantic_extra__
            extra = getattr(event, "__pydantic_extra__", None)
            if isinstance(extra, dict) and "context_management" in extra:
                val = extra["context_management"]
                if isinstance(val, dict):
                    class _D(dict):
                        def model_dump(self, *a: Any, **kw: Any) -> dict[str, Any]:
                            return dict(self)
                    extra["context_management"] = _D(val)
                    return original_make(self, event, *args, **kwargs)
            raise

    setattr(chat_cls, "_make_message_chunk_from_anthropic_event", _safe_make_message_chunk_from_anthropic_event)
    setattr(chat_cls, _PATCHED_ATTR, True)
    logger.debug("Applied ChatAnthropic context_management stream patch")
    return True


__all__ = ["patch_langchain_anthropic_context_management"]
