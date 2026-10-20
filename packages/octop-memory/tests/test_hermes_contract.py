"""Contract-fidelity tests for the Hermes MemoryProvider adapter.

These tests pin the *shape* of the Hermes integration so it cannot drift
silently. The provider is normally exercised against a fallback stub base
class (Hermes is an external agent, not vendored here), so unit tests alone
cannot catch a rename or a dropped hook. This module cross-checks three
sources that must stay in sync:

- ``plugin.yaml`` — the hooks Hermes is told this provider implements
- ``OctopMemoryProvider`` — the methods actually implemented
- the tool schemas advertised to the model vs. what ``handle_tool_call``
  can dispatch

The real-Hermes counterpart lives in ``test_hermes_e2e.py`` (skipped unless
a Hermes source tree is available); this file is the drift guard that always
runs.
"""

from __future__ import annotations

import importlib.util
import inspect
from pathlib import Path
from types import ModuleType

import pytest

_PLUGIN_DIR = Path(__file__).resolve().parents[1] / "plugins" / "hermes" / "octopmemory"


def _load_provider_module() -> ModuleType:
    path = _PLUGIN_DIR / "__init__.py"
    spec = importlib.util.spec_from_file_location("octopmemory_hermes_contract", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _declared_hooks() -> list[str]:
    """Parse the ``hooks:`` list from plugin.yaml without a yaml dependency.

    octop-memory deliberately avoids importing yaml for config (see the
    line-based parser in ``install_lib.py``); mirror that here.
    """
    text = (_PLUGIN_DIR / "plugin.yaml").read_text(encoding="utf-8")
    hooks: list[str] = []
    in_hooks = False
    for raw in text.splitlines():
        if raw.strip() == "hooks:":
            in_hooks = True
            continue
        if in_hooks:
            stripped = raw.strip()
            if stripped.startswith("- "):
                hooks.append(stripped[2:].strip().strip("\"'"))
            elif raw and not raw.startswith((" ", "\t", "-")):
                break  # next top-level key ends the block
    return hooks


_mod = _load_provider_module()
OctopMemoryProvider = _mod.OctopMemoryProvider


def test_declared_hooks_are_all_implemented() -> None:
    """Every hook named in plugin.yaml must exist as a callable method."""
    declared = _declared_hooks()
    assert declared, "plugin.yaml declares no hooks; parser or manifest drifted"
    missing = [name for name in declared if not callable(getattr(OctopMemoryProvider, name, None))]
    assert not missing, f"plugin.yaml declares hooks with no implementation: {missing}"


def test_required_hermes_method_surface_exists() -> None:
    """Hermes discovers the provider through this method surface.

    These are called by Hermes outside the declared hook list (registration,
    lifecycle, tool exposure, config setup). Dropping one breaks integration
    even though unit tests against the stub base class would still pass.
    """
    required = [
        "is_available",
        "initialize",
        "get_tool_schemas",
        "handle_tool_call",
        "get_config_schema",
        "save_config",
        "system_prompt_block",
        "prefetch",
        "sync_turn",
        "shutdown",
    ]
    missing = [name for name in required if not callable(getattr(OctopMemoryProvider, name, None))]
    assert not missing, f"provider is missing required Hermes methods: {missing}"

    # ``name`` is a property, not a plain method.
    assert isinstance(inspect.getattr_static(OctopMemoryProvider, "name"), property)


def test_register_entrypoint_is_present() -> None:
    assert callable(getattr(_mod, "register", None)), "plugin module must expose register(ctx)"


def test_key_hook_signatures_accept_expected_kwargs() -> None:
    """Guard the exact kwargs Hermes passes into hot-path hooks."""
    init_sig = inspect.signature(OctopMemoryProvider.initialize)
    assert "session_id" in init_sig.parameters
    # Hermes passes hermes_home (and other context) as kwargs.
    accepts_hermes_home = "hermes_home" in init_sig.parameters or any(
        p.kind is inspect.Parameter.VAR_KEYWORD for p in init_sig.parameters.values()
    )
    assert accepts_hermes_home, "initialize must accept hermes_home (explicitly or via **kwargs)"

    for method in ("prefetch", "queue_prefetch", "sync_turn"):
        sig = inspect.signature(getattr(OctopMemoryProvider, method))
        accepts_session = "session_id" in sig.parameters or any(
            p.kind is inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
        )
        assert accepts_session, f"{method} must accept session_id (explicitly or via **kwargs)"


def test_tool_schemas_are_well_formed() -> None:
    provider = OctopMemoryProvider()
    schemas = provider.get_tool_schemas()
    assert schemas, "provider advertises no tools"
    for schema in schemas:
        assert isinstance(schema.get("name"), str) and schema["name"]
        assert isinstance(schema.get("description"), str) and schema["description"]
        params = schema.get("parameters")
        assert isinstance(params, dict) and params.get("type") == "object"
        assert isinstance(params.get("properties"), dict) and params["properties"]
        assert isinstance(params.get("required"), list)
        # Every required key must be declared as a property.
        assert set(params["required"]).issubset(params["properties"])


def test_advertised_tools_are_all_dispatchable(tmp_path: Path) -> None:
    """Each advertised tool name must be handled; unknown names must reject.

    This ties get_tool_schemas() to handle_tool_call() so renaming a tool in
    one place without the other is caught.
    """
    provider = OctopMemoryProvider()
    provider.initialize("sess_contract", hermes_home=str(tmp_path), platform="cli")
    try:
        tool_names = [schema["name"] for schema in provider.get_tool_schemas()]
        for name in tool_names:
            # A minimal valid arg per known tool; dispatch must not raise
            # "Unknown tool". Bridge-level validation errors are returned as
            # JSON, not raised, so any return value proves the branch exists.
            args = {"query": "contract probe"} if name == "memory_search" else {"path": "raw/unknown.md"}
            provider.handle_tool_call(name, args)

        with pytest.raises(ValueError):
            provider.handle_tool_call("definitely_not_a_tool", {})
    finally:
        provider.shutdown()
