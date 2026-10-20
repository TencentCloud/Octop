"""Backward-compat re-export — prefer ``from octop_harness.slash import ...``."""

from octop_harness.slash.core import (
    RuntimeSlashDispatcher,
    build_runtime_dispatcher,
)

__all__ = ["RuntimeSlashDispatcher", "build_runtime_dispatcher"]
