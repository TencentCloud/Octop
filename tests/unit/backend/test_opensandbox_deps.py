"""Tests for on-demand OpenSandbox SDK install."""

from __future__ import annotations

from octop.infra.backend import opensandbox_deps


def test_ensure_opensandbox_deps_ready_when_importable(monkeypatch) -> None:
    monkeypatch.setattr(opensandbox_deps, "opensandbox_sdk_available", lambda: True)
    assert opensandbox_deps.ensure_opensandbox_deps() == "ready"


def test_ensure_opensandbox_deps_installs(monkeypatch) -> None:
    state = {"ok": False}

    def _available() -> bool:
        return state["ok"]

    def _install(*_a, **_k) -> str:
        state["ok"] = True
        return "installed"

    monkeypatch.setattr(opensandbox_deps, "opensandbox_sdk_available", _available)
    monkeypatch.setattr(opensandbox_deps, "install_packages", _install)
    assert opensandbox_deps.ensure_opensandbox_deps(allow_install=True) == "installed"
