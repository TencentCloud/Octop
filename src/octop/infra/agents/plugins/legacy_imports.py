"""Alias the pre-rename plugin SDK import ``harness_agent`` to ``octop_harness``.

Marketplace plugins written before the package rename still do
``from harness_agent.plugins import PluginContext``. The installed
distribution only provides ``octop_harness``, so loading those plugins
raises ``ModuleNotFoundError: No module named 'harness_agent'``.
"""

from __future__ import annotations

import importlib
import importlib.abc
import importlib.machinery
import importlib.util
import sys
import threading
from collections.abc import Sequence
from types import ModuleType

_PREFIX = "harness_agent"
_TARGET = "octop_harness"
_lock = threading.Lock()
_installed = False


class _LegacyAliasLoader(importlib.abc.Loader):
    """Return the already-imported ``octop_harness`` module for an alias name."""

    def __init__(self, real_name: str) -> None:
        self._real_name = real_name

    def create_module(self, spec: importlib.machinery.ModuleSpec) -> ModuleType:
        del spec
        return importlib.import_module(self._real_name)

    def exec_module(self, module: ModuleType) -> None:
        del module


class _LegacyHarnessAgentFinder:
    def find_spec(
        self,
        fullname: str,
        path: Sequence[str] | None,
        target: ModuleType | None = None,
    ) -> importlib.machinery.ModuleSpec | None:
        del path, target
        if fullname != _PREFIX and not fullname.startswith(_PREFIX + "."):
            return None
        real_name = _TARGET + fullname[len(_PREFIX) :]
        try:
            real_spec = importlib.util.find_spec(real_name)
        except (ImportError, ValueError):
            return None
        if real_spec is None:
            return None
        locations = real_spec.submodule_search_locations
        is_package = locations is not None
        spec = importlib.machinery.ModuleSpec(
            fullname,
            _LegacyAliasLoader(real_name),
            origin=real_spec.origin,
            is_package=is_package,
        )
        if locations is not None:
            spec.submodule_search_locations = list(locations)
        return spec


def ensure_legacy_harness_agent_alias() -> None:
    """Map ``import harness_agent`` onto the installed ``octop_harness`` package.

    A real ``harness_agent`` distribution, when present, is left untouched.
    """
    global _installed
    if _installed:
        return
    with _lock:
        if _installed:
            return
        try:
            existing = importlib.util.find_spec(_PREFIX)
        except (ImportError, ValueError):
            existing = None
        if existing is None:
            sys.meta_path.insert(0, _LegacyHarnessAgentFinder())
        _installed = True
