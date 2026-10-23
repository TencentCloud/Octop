"""Close async iterators that an ``async for`` would otherwise abandon."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from typing import cast


async def aclose[T](iterator: AsyncIterator[T]) -> None:
    """Await ``aclose()`` when *iterator* provides one.

    ``async for`` does not close its source on ``return``, ``break``, or an
    outer ``aclose()``. Generators left open are finalized later in a new task,
    which cannot reset a ContextVar token created by the consumer.
    """
    close = getattr(iterator, "aclose", None)
    if not callable(close):
        return
    result = cast("Callable[[], Awaitable[object]]", close)()
    await result
