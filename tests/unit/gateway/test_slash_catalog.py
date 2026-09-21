"""tests/unit/test_slash_catalog.py"""

from __future__ import annotations

from octop.infra.gateway.slash.catalog import list_specs, spec_for
from octop.infra.gateway.slash.dispatcher import build_default_dispatcher


def test_catalog_lists_primary_names():
    names = {s.name for s in list_specs(origin="ui")}
    assert "help" in names
    assert "compact" in names
    assert "token" in names
    assert "stop" in names
    assert "exit" not in names


def test_alias_resolves_to_primary_spec():
    assert spec_for("clear") is not None
    assert spec_for("clear").name == "new"  # type: ignore[union-attr]
    assert spec_for("topics") is not None
    assert spec_for("topics").name == "list"  # type: ignore[union-attr]
    assert spec_for("ask") is not None
    assert spec_for("ask").name == "mode"  # type: ignore[union-attr]
    assert spec_for("plan").name == "mode"  # type: ignore[union-attr]
    assert spec_for("craft").name == "mode"  # type: ignore[union-attr]


def test_dispatcher_registers_all_catalog_commands():
    d = build_default_dispatcher()
    known = {name for name, _ in d.known()}
    for spec in list_specs(origin="all"):
        assert spec.name in known
