"""Typed failures raised while resolving a history page cursor."""

from __future__ import annotations


class InvalidHistoryCursorError(ValueError):
    """The caller's ``cursor`` cannot be resolved against this thread's history.

    Subclasses :class:`ValueError` so generic handlers keep their behaviour, while
    letting HTTP adapters map *cursor* problems alone to a client error and leave
    genuine archive failures as server errors.
    """
