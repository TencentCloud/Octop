"""Real-Hermes end-to-end contract test (opt-in).

Skipped unless ``HERMES_SOURCE`` points at a real ``NousResearch/hermes-agent``
checkout (one containing ``agent/memory_provider.py``). When present, this is
the "real base class" counterpart to ``test_hermes_contract.py``: it proves
``OctopMemoryProvider`` subclasses the *actual* Hermes MemoryProvider and
that the runtime flow works against it, not just the in-repo stub.

Run it directly:

    HERMES_SOURCE=/path/to/hermes-agent uv run pytest tests/test_hermes_e2e.py -q

The heavier shell variant (install + doctor + flow) lives in
``scripts/e2e_hermes_test.sh``.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

_HERMES_SOURCE = os.environ.get("HERMES_SOURCE", "")
_HAS_REAL_HERMES = bool(_HERMES_SOURCE) and (Path(_HERMES_SOURCE) / "agent" / "memory_provider.py").is_file()

pytestmark = pytest.mark.skipif(
    not _HAS_REAL_HERMES,
    reason="set HERMES_SOURCE to a hermes-agent checkout (with agent/memory_provider.py) to run",
)

# Put the real Hermes source on sys.path at import time so `agent.memory_provider`
# resolves before any test body runs.
if _HAS_REAL_HERMES and _HERMES_SOURCE not in sys.path:
    sys.path.insert(0, _HERMES_SOURCE)

_PLUGIN_INIT = Path(__file__).resolve().parents[1] / "plugins" / "hermes" / "octopmemory" / "__init__.py"


def _load_provider_against_real_hermes():
    """Load the plugin so it binds the REAL agent.memory_provider.MemoryProvider."""
    spec = importlib.util.spec_from_file_location("octopmemory_hermes_e2e", _PLUGIN_INIT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_provider_subclasses_real_memory_provider() -> None:
    from agent.memory_provider import MemoryProvider as RealBase

    module = _load_provider_against_real_hermes()
    assert issubclass(module.OctopMemoryProvider, RealBase)

    # Every abstract method the real base declares must be overridden.
    abstract = getattr(RealBase, "__abstractmethods__", frozenset())
    unimplemented = [name for name in abstract if getattr(module.OctopMemoryProvider, name, None) is None]
    assert not unimplemented, f"provider leaves real abstract methods unimplemented: {unimplemented}"


def test_runtime_flow_against_real_base(tmp_path: Path) -> None:
    module = _load_provider_against_real_hermes()
    hermes_home = tmp_path / "home"
    (hermes_home / "memories" / "topics").mkdir(parents=True)
    (hermes_home / "memories" / "USER.md").write_text("User prefers concise updates.", encoding="utf-8")
    (hermes_home / "memories" / "topics" / "billing.md").write_text(
        "Billing topic keeps the renewal policy notes.", encoding="utf-8"
    )

    provider = module.OctopMemoryProvider()
    provider.initialize("e2e_sess", hermes_home=str(hermes_home), platform="cli")
    try:
        # host_files scanned synchronously at initialize — check before shutdown.
        host = json.loads(provider.handle_tool_call("memory_search", {"query": "renewal policy", "maxResults": 5}))
        assert any(h.get("path") == "topics/billing.md" for h in host.get("hits", []))

        provider.sync_turn(
            "Remember the release window is Tuesday 14:00 for the Hermes rollout.",
            "Confirmed: release window Tuesday 14:00.",
            session_id="e2e_sess",
        )
        for thread in list(provider._threads):
            thread.join(timeout=5.0)

        search = json.loads(
            provider.handle_tool_call("memory_search", {"query": "release window Tuesday", "maxResults": 5})
        )
        assert search.get("hits")
        got = json.loads(provider.handle_tool_call("memory_get", {"path": search["hits"][0]["path"]}))
        assert "release window" in got.get("excerpt", "").lower()

        block = provider.prefetch("What is the release window?", session_id="e2e_sess")
        assert "OctopMemory Recall" in block
    finally:
        provider.shutdown()
