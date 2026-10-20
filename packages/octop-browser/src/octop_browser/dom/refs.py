"""Ref-to-node_id cache for the DOM builder."""

from __future__ import annotations


class RefCache:
    """Maps short ref strings (e.g. 'btn_1') to CDP node IDs.

    The cache is invalidated after any cross-document navigation.
    """

    def __init__(self) -> None:
        self._refs: dict[str, int] = {}

    def store(self, ref: str, node_id: int) -> None:
        """Register a ref → node_id mapping."""
        self._refs[ref] = node_id

    def lookup(self, ref: str) -> int | None:
        """Return the node_id for a ref, or None if not found."""
        return self._refs.get(ref)

    def invalidate(self) -> None:
        """Clear all refs (called after navigation)."""
        self._refs.clear()

    def all_refs(self) -> dict[str, int]:
        """Return a copy of all current mappings."""
        return dict(self._refs)
