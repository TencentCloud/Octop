"""Hook system for BrowserSession event callbacks."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

HookFn = TypeVar("HookFn", bound=Callable[..., Coroutine[Any, Any, None]])

_VALID_EVENTS = frozenset(
    ["before_action", "after_action", "action_error", "page_navigated"]
)


class HooksMixin:
    """Mixin that adds event hook registration and firing to a class."""

    def __init__(self) -> None:
        self._hooks: dict[str, list[Callable[..., Any]]] = {
            event: [] for event in _VALID_EVENTS
        }

    def on(self, event: str) -> Callable[[HookFn], HookFn]:
        """Decorator to register an async callback for an event.

        Valid events: ``before_action``, ``after_action``,
        ``action_error``, ``page_navigated``.

        Note: ``page_navigated`` is reserved — it is accepted here for
        forward/backward compatibility but no code path emits it yet.
        """
        if event not in _VALID_EVENTS:
            raise ValueError(f"Unknown event {event!r}. Valid: {sorted(_VALID_EVENTS)}")

        def decorator(fn: HookFn) -> HookFn:
            self._hooks[event].append(fn)
            return fn

        return decorator

    async def _fire(self, event: str, payload: Any) -> None:
        """Fire all registered callbacks for an event."""
        for callback in self._hooks.get(event, []):
            try:
                result = callback(payload)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:  # noqa: BLE001  # pylint: disable=broad-except
                logger.exception("Hook callback raised for event %r", event)
