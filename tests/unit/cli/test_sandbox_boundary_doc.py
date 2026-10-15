"""The configuration docs must state the sandbox network boundary (#1932)."""

from __future__ import annotations

from pathlib import Path


def test_configuration_doc_states_network_boundary():
    doc = Path(__file__).resolve().parents[3] / "docs" / "configuration.md"
    text = doc.read_text(encoding="utf-8")
    assert "does not isolate the network" in text
    assert "convenience boundary, not a security boundary" in text
    assert "127.0.0.1" in text  # concrete host-local risk example
    assert "Docker sandbox" in text  # mitigation pointer
