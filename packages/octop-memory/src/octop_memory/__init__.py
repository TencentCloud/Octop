"""octop-memory: pluggable memory system for LLM agents."""

from __future__ import annotations

from typing import TYPE_CHECKING

from octop_memory.core import Memory
from octop_memory.types import (
    MemoryNode,
    ThreadState,
    ThreadSummary,
)

try:
    from octop_memory._version import __version__  # type: ignore[import-untyped]
except ImportError:
    # No build-time _version module (the version in pyproject.toml is static,
    # so nothing generates one). Installed wheels must report the real version
    # from distribution metadata instead of the "+unknown" placeholder, which
    # previously leaked into `--version`, bridge --probe, and doctor output.
    try:
        from importlib.metadata import PackageNotFoundError, version

        __version__ = version("octop-memory")
    except PackageNotFoundError:
        # Source checkout without an installed distribution.
        __version__ = "0.0.0+unknown"

if TYPE_CHECKING:
    # Type-checker-visible without paying the import at runtime.
    from octop_memory.service import MemoryService


def __getattr__(name: str) -> object:
    """Lazily expose :class:`MemoryService` (PEP 562).

    ``MemoryService`` pulls in the bridge + extraction + CLI stack, so importing
    it eagerly here would (a) make ``import octop_memory`` heavy and (b) create
    a circular import via ``cli`` reading ``__version__`` back from this module.
    Loading it on first attribute access keeps the top-level package light.
    """
    if name == "MemoryService":
        from octop_memory.service import MemoryService

        return MemoryService
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "Memory",
    "MemoryNode",
    "MemoryService",
    "ThreadState",
    "ThreadSummary",
    "__version__",
]
