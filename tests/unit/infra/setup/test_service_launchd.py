"""Cross-platform tests for mocked launchd service orchestration."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from octop.infra.setup import service as service_mod
from octop.infra.setup.service import ServiceRuntime, restart_service


def test_restart_waits_for_launchd_label_release_before_bootstrap(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    runtime = ServiceRuntime(
        mode="launchd",
        host="127.0.0.1",
        port=8088,
        home=tmp_path,
        octop_bin=tmp_path / "bin" / "octop",
        run_as_user="tester",
        scope="user",
    )
    calls: list[str] = []
    print_attempts = 0

    def _fake_launchctl_run(scope: str, *args: str) -> object:
        nonlocal print_attempts
        command = args[0]
        calls.append(command)
        if command == "print":
            print_attempts += 1
        released = command == "print" and print_attempts >= 3
        return SimpleNamespace(
            returncode=1 if released else 0,
            stdout="",
            stderr="Could not find service" if released else "",
        )

    monkeypatch.setattr(service_mod, "is_service_installed", lambda *_a, **_k: True)
    monkeypatch.setattr(service_mod, "install_service", lambda rt, force=False: False)
    monkeypatch.setattr(service_mod, "_launchctl_run", _fake_launchctl_run)
    monkeypatch.setattr(service_mod, "unit_path", lambda *_a, **_k: tmp_path / "octop.plist")
    monkeypatch.setattr(service_mod, "_wait_for_stop", lambda _rt: None)
    monkeypatch.setattr(service_mod, "_wait_for_startup", lambda: None)
    monkeypatch.setattr(service_mod.time, "sleep", lambda _seconds: None)

    restart_service(runtime)

    assert calls == ["bootout", "print", "print", "print", "bootstrap"]
