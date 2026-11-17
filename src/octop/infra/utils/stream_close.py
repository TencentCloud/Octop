"""Use Gateway's public helper for deterministic nested event-stream cleanup."""

from __future__ import annotations

from octop_gateway.utils import close_event_stream

__all__ = ["close_event_stream"]
